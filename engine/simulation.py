from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal,ROUND_DOWN,localcontext
from typing import Callable
from zoneinfo import ZoneInfo
from pydantic import Field, model_validator
from SCHEMA import (StrictModel,RevolvingAccount,MinimumPaymentSnapshot,BillingCycle,GracePeriodState,
                    CompoundingMethod,SegmentType,ProvenanceSource,Sourced,DayCountConvention)
from engine.common import CONTEXT,ZERO,CENT,Money,Nonnegative,decimal_context,decimal_input,reconstruct,MissingTerms,UnsupportedTerms,posting
from engine.interest import daily_rate, DailyBalance
from engine.allocation import allocate_payment,projected_minimum
from engine.liquidity import CashOpening,CashPlan,CashKind,project_liquidity
from engine.search import bounded_payment_search,SearchResult
from engine.timing import PaymentTiming,assumed_same_day_timing
from engine.promotions import PromoTransition, PromoExitResult, SegmentDailyHistory, assess_promo_exit, validate_promo_exit_terms
from engine.grace import GraceReplayTerms, GraceStatement, GraceDecision, StatementCredit, resolve_grace

class DebtCreditEvent(StrictModel):
    event_id:str=Field(min_length=1)
    credited_at:datetime
    sequence:int=Field(default=0,ge=0)

    @model_validator(mode='after')
    def aware(self):
        if self.credited_at.utcoffset() is None:raise ValueError('credit timestamp must be timezone aware')
        return self

    def ordering_key(self):
        return (self.credited_at.astimezone(timezone.utc),self.sequence)

class DebtPayment(StrictModel):
    on:date
    amount:Nonnegative
    event_id:str|None=None
    credited_at:datetime|None=None

class DebtAudit(StrictModel):
    on:date
    kind:str
    amount:Money
    detail:str

class CycleMinimumState(StrictModel):
    cycle_id:str
    remaining:Nonnegative

class GraceShadowState(StrictModel):
    segment_id:str
    amount:Nonnegative

class EffectiveSegmentView(StrictModel):
    segment_id:str
    segment_type:SegmentType
    balance:Nonnegative
    accrued_unposted_interest:Nonnegative
    apr:Sourced[Decimal]
    compounding:Sourced[CompoundingMethod]
    day_count:Sourced[DayCountConvention]
    grace_eligible:bool
    promo_exited:bool

class DebtDecisionView(StrictModel):
    event_id:str|None=None
    credited_at:datetime|None=None
    on:date
    account_id:str
    segments:tuple[EffectiveSegmentView,...]
    effective_minimum:Nonnegative
    grace_state:GracePeriodState
    previous_payments:tuple[DebtPayment,...]

class DebtCheckpoint(StrictModel):
    version:int=Field(default=1,ge=1,le=1)
    credit_timezone:str="UTC"
    credit_events:tuple[DebtCreditEvent,...]=()
    start:date
    as_of:date
    source_account:RevolvingAccount
    account:RevolvingAccount
    cycles:tuple[BillingCycle,...]
    initial_minimum:MinimumPaymentSnapshot
    grace_terms:GraceReplayTerms|None=None
    promo_transitions:tuple[PromoTransition,...]=()
    minimums:tuple[CycleMinimumState,...]
    shadow:tuple[GraceShadowState,...]
    active_statement:GraceStatement|None=None
    grace_streak:int=Field(ge=0)
    assessed_since_close:Nonnegative
    contingent:Nonnegative
    payments:tuple[DebtPayment,...]
    audit:tuple[DebtAudit,...]
    missed_due_dates:tuple[date,...]
    promo_exits:tuple[PromoExitResult,...]
    daily_histories:tuple[SegmentDailyHistory,...]
    grace_decisions:tuple[GraceDecision,...]

    @model_validator(mode='after')
    @decimal_context
    def consistent(self):
        if self.as_of<self.start:raise ValueError('checkpoint date precedes start')
        account_id=self.source_account.account_id
        if self.account.account_id!=account_id or self.initial_minimum.account_id!=account_id:
            raise ValueError('checkpoint account mismatch')
        source_ids={s.segment_id for s in self.source_account.segments}
        if source_ids!={s.segment_id for s in self.account.segments}:
            raise ValueError('checkpoint segment identity mismatch')
        def unique(rows,attr,label):
            ids=[getattr(r,attr) for r in rows]
            if len(ids)!=len(set(ids)):raise ValueError('duplicate checkpoint '+label)
            return set(ids)
        cycle_ids=unique(self.cycles,'cycle_id','cycles')
        if any(c.account_id!=account_id for c in self.cycles):raise ValueError('checkpoint cycle ownership mismatch')
        expected_minimums={self.initial_minimum.billing_cycle_id}|{c.cycle_id for c in self.cycles if self.start<=c.end_date<=self.as_of}
        if unique(self.minimums,'cycle_id','minimums')!=expected_minimums:raise ValueError('checkpoint minimum cycle coverage mismatch')
        if self.initial_minimum.billing_cycle_id not in cycle_ids:raise ValueError('checkpoint opening cycle missing')
        if unique(self.daily_histories,'segment_id','histories')!=source_ids:raise ValueError('checkpoint history coverage mismatch')
        expected=(self.as_of-self.start).days+1
        for h in self.daily_histories:
            if len(h.balances)!=expected or any(r.day!=self.start+timedelta(days=i) for i,r in enumerate(h.balances)):
                raise ValueError('checkpoint daily history must cover every elapsed day')
        eligible={s.segment_id for s in self.account.segments if s.segment_type in self.account.grace_applies_to_segment_types}
        if unique(self.shadow,'segment_id','shadow')!=eligible:raise ValueError('checkpoint shadow coverage mismatch')
        transition_ids=unique(self.promo_transitions,'segment_id','transitions')
        if not transition_ids<=source_ids:raise ValueError('checkpoint transition ownership mismatch')
        exited_ids=unique(self.promo_exits,'segment_id','exits')
        due_ids={t.segment_id for t in self.promo_transitions if t.terms.cutoff<=self.as_of}
        if exited_ids!=due_ids:raise ValueError('checkpoint exited-state coverage mismatch')
        for e in self.promo_exits:
            t=next(t for t in self.promo_transitions if t.segment_id==e.segment_id)
            if e.account_id!=account_id or e.cutoff!=t.terms.cutoff or e.reversion_starts!=e.cutoff+timedelta(days=1):
                raise ValueError('checkpoint exit identity/date mismatch')
        if any(p.on<self.start or p.on>self.as_of for p in self.payments):raise ValueError('checkpoint payment outside history')
        tz=ZoneInfo(self.credit_timezone)
        event_ids=unique(self.credit_events,'event_id','credit events')
        event_keys=[e.ordering_key() for e in self.credit_events]
        if event_keys!=sorted(set(event_keys)):raise ValueError('checkpoint credit event order is ambiguous')
        if any(not self.start<=e.credited_at.astimezone(tz).date()<=self.as_of for e in self.credit_events):
            raise ValueError('checkpoint credit event outside history')
        paid_ids=[];legacy_dates=[]
        for payment in self.payments:
            if payment.event_id is None:
                if payment.credited_at is not None:raise ValueError('credit timestamp requires an event ID')
                legacy_dates.append(payment.on)
            else:
                paid_ids.append(payment.event_id)
                if payment.event_id not in event_ids:raise ValueError('payment event missing from checkpoint')
                event=next(e for e in self.credit_events if e.event_id==payment.event_id)
                if payment.credited_at!=event.credited_at or payment.on!=event.credited_at.astimezone(tz).date():
                    raise ValueError('payment credit event mismatch')
        if paid_ids!=[e.event_id for e in self.credit_events if e.event_id in set(paid_ids)]:
            raise ValueError('checkpoint credited payments out of event order')
        if len(paid_ids)!=len(set(paid_ids)) or len(legacy_dates)!=len(set(legacy_dates)):
            raise ValueError('duplicate checkpoint payment identity')
        if [p.on for p in self.payments]!=sorted(p.on for p in self.payments):raise ValueError('checkpoint payments out of order')
        if any(a.on<self.start or a.on>self.as_of for a in self.audit):raise ValueError('checkpoint audit outside history')
        if any(d<self.start or d>self.as_of for d in self.missed_due_dates):raise ValueError('checkpoint missed due date outside history')
        if self.active_statement is not None:
            cycle=self.active_statement.cycle
            if cycle not in self.cycles or not cycle.statement_date<=self.as_of<cycle.due_date:
                raise ValueError('checkpoint active statement must be closed and not yet due')
            if any(c.credited_on>self.as_of for c in self.active_statement.credits):raise ValueError('checkpoint contains future statement credit')
        if self.grace_terms is not None:
            if self.grace_streak!=self.account.consecutive_statements_paid_in_full:
                raise ValueError('checkpoint grace streak mismatch')
            if self.contingent!=sum((r.amount for r in self.shadow),ZERO):raise ValueError('checkpoint contingent total mismatch')
        source_dump=self.source_account.model_dump()
        current_dump=self.account.model_dump()
        for field in ('segments','current_grace_state','projected_grace_state','consecutive_statements_paid_in_full'):
            source_dump.pop(field);current_dump.pop(field)
        if source_dump!=current_dump:raise ValueError('checkpoint source account terms changed')
        original={s.segment_id:s for s in self.source_account.segments}
        mutable=('balance','balance_provenance','balance_as_of_date','accrued_unposted_interest',
                 'accrued_interest_provenance','accrued_interest_as_of_date')
        with localcontext(CONTEXT):
            for seg in self.account.segments:
                old=original[seg.segment_id].model_dump();new=seg.model_dump()
                for field in mutable:old.pop(field);new.pop(field)
                if old!=new:raise ValueError('checkpoint source segment terms changed')
                posted=sum((a.amount for a in self.audit if a.detail==seg.segment_id and a.kind in ('promo_exit','interest_posting')),ZERO)
                paid=sum((a.amount for a in self.audit if a.detail==seg.segment_id and a.kind.startswith('payment_')),ZERO)
                if seg.balance!=original[seg.segment_id].balance+posted-paid:
                    raise ValueError('checkpoint posted balance does not reconcile with audit')
            if sum((p.amount for p in self.payments),ZERO)!=sum((a.amount for a in self.audit if a.kind.startswith('payment_')),ZERO):
                raise ValueError('checkpoint payments do not reconcile with allocation audit')
            last_close=max((c.end_date for c in self.cycles if self.start<=c.end_date<=self.as_of),default=self.start-timedelta(days=1))
            for seg in self.account.segments:
                accrued=(original[seg.segment_id].accrued_unposted_interest if last_close<self.start else ZERO)
                for event in self.audit:
                    if event.detail==seg.segment_id and event.on>last_close and event.kind in ('unposted_interest','grace_loss_unposted'):
                        accrued+=event.amount
                if seg.accrued_unposted_interest!=accrued:
                    raise ValueError('checkpoint unposted accrual does not reconcile with audit')
            assessed=sum((e.assessed_deferred_interest for e in self.promo_exits if e.cutoff>last_close),ZERO)
            if assessed!=self.assessed_since_close:raise ValueError('checkpoint unbilled assessment mismatch')
        return self

class DebtProjection(StrictModel):
    account:RevolvingAccount
    payments:tuple[DebtPayment,...]
    audit:tuple[DebtAudit,...]
    contingent_grace_interest:Nonnegative
    minimum_remaining:Nonnegative
    missed_due_dates:tuple[date,...]
    promo_exits:tuple[PromoExitResult,...]=()
    daily_histories:tuple[SegmentDailyHistory,...]=()
    grace_decisions:tuple[GraceDecision,...]=()
    grace_consecutive_full_statements:int=0
    checkpoint:DebtCheckpoint|None=None
    label:str='estimate'

@decimal_context
def simulate_revolving(account:RevolvingAccount,start:date,end:date,cycles:tuple[BillingCycle,...],
                       initial_minimum:MinimumPaymentSnapshot,payment_dates:tuple[date,...],
                       choose_payment:Callable|None=None, *, choose_decision:Callable[[DebtDecisionView],Decimal]|None=None,
                       grace_terms:GraceReplayTerms|None=None,
                       promo_transitions:tuple[PromoTransition,...]=(),
                       credit_events:tuple[DebtCreditEvent,...]=(),credit_timezone:str="UTC",
                       _checkpoint:DebtCheckpoint|None=None)->DebtProjection:
    """Daily replay through end-of-day: morning credit, accrual, statement posting,
    then due-date checks. Explicit grace terms support consecutive reconciled
    statements with simple-daily purchases and nonoverlapping due windows.

    Source schema terms remain historical. Runtime promo exits control accrual
    and allocation and are returned alongside the account; the account alone is
    not a resumable post-exit snapshot; use the returned checkpoint. Legacy payment callbacks receive source terms
    with updated balances and must not interpret source APR as post-exit APR.
    """
    tz=ZoneInfo(credit_timezone)
    if credit_events and (payment_dates or choose_decision is None):
        raise ValueError('timestamped credits require choose_decision and no legacy payment dates')
    event_keys=[e.ordering_key() for e in credit_events]
    if event_keys!=sorted(set(event_keys)) or len({e.event_id for e in credit_events})!=len(credit_events):
        raise ValueError('credit events require unique IDs and unambiguous chronological order')
    events_by_day={}
    for event in credit_events:
        on=event.credited_at.astimezone(tz).date()
        if not start<=on<=end:raise ValueError('credit event outside horizon')
        events_by_day.setdefault(on,[]).append(event)
    processed_events=[]
    if (choose_payment is None)==(choose_decision is None):raise ValueError('supply exactly one payment decision callback')
    if end<start or tuple(sorted(set(payment_dates)))!=payment_dates:raise ValueError('ordered unique dates required')
    if any(d<start or d>end for d in payment_dates):raise ValueError('payment outside horizon')
    if initial_minimum.account_id!=account.account_id:raise ValueError('initial minimum account mismatch')
    relevant=sorted((c for c in cycles if c.account_id==account.account_id),key=lambda c:c.start_date)
    if not relevant or relevant[0].start_date>start or relevant[-1].end_date<end:raise MissingTerms('cycles must cover horizon')
    if len({c.cycle_id for c in relevant})!=len(relevant):raise ValueError('duplicate cycles')
    if any(b.start_date!=a.end_date+timedelta(days=1) for a,b in zip(relevant,relevant[1:])):raise MissingTerms('cycles must be contiguous')
    if initial_minimum.billing_cycle_id not in {c.cycle_id for c in relevant}:raise MissingTerms('initial minimum cycle missing')
    originals={s.segment_id:s for s in account.segments}
    transitions={t.segment_id:t for t in promo_transitions}
    if len(transitions)!=len(promo_transitions) or not set(transitions)<=set(originals):
        raise ValueError('promo transitions must be unique and reference account segments')
    for t in promo_transitions:
        if t.terms.cutoff<start:raise ValueError('promo cutoff precedes replay start')
        seg=originals[t.segment_id]
        # Validate supplied term completeness and dates before payment callbacks.
        validate_promo_exit_terms(seg,t.terms)
        if seg.segment_type==SegmentType.PROMOTIONAL_DEFERRED_INTEREST:
            if seg.deferred_interest_as_of_date!=start-timedelta(days=1):
                raise MissingTerms('deferred opening exposure must precede replay start')
            if seg.deferred_interest_calculation_method.value.value=='retroactive_purchase_sum':
                raise MissingTerms('retroactive purchase sum requires purchase-level history')
        method=t.terms.disqualified_compounding if t.terms.reason.value=='disqualification' else seg.post_promo_compounding_method
        if method is None or method.value==CompoundingMethod.MONTHLY_COMPOUNDING:
            raise UnsupportedTerms('monthly capitalization after promo exit requires explicit terms')
        if t.post_exit_grace_eligible.value and method.value!=CompoundingMethod.SIMPLE_DAILY:
            raise UnsupportedTerms('post-exit grace integration requires simple-daily terms')
        if t.post_exit_grace_eligible.value and seg.segment_type not in account.grace_applies_to_segment_types:
            raise UnsupportedTerms('new grace eligibility at exit requires separate history')
        if t.post_exit_grace_eligible.value and grace_terms is None and account.current_grace_state!=GracePeriodState.LOST_GRACE:
            raise MissingTerms('post-exit grace eligibility requires explicit grace history')
    for seg in account.segments:
        if seg.is_disqualified or seg.disqualification_events:
            raise MissingTerms('already disqualified opening requires historical exit reconciliation')
        if seg.promo_expiration_date and end>=seg.promo_expiration_date and seg.segment_id not in transitions:
            raise MissingTerms('crossing promo expiration requires an explicit transition')
        if seg.compounding_method.value==CompoundingMethod.MONTHLY_COMPOUNDING:
            raise UnsupportedTerms('monthly capitalization terms not implemented')
        if seg.accrued_unposted_interest<0:raise ValueError('negative opening accrual unsupported')
    exits={}
    histories={s.segment_id:[] for s in account.segments}
    assessed_since_close=ZERO
    initial_cycle=next(c for c in relevant if c.cycle_id==initial_minimum.billing_cycle_id)
    if initial_cycle.statement_date>=start:
        raise MissingTerms('opening billed minimum must precede the replay start')
    minimums={initial_minimum.billing_cycle_id:initial_minimum.statement_minimum_remaining}
    dues={c.cycle_id:c.due_date for c in relevant}
    initial_due=dues[initial_minimum.billing_cycle_id]
    if initial_due<start and initial_minimum.statement_minimum_remaining>0:
        raise MissingTerms('overdue opening minimum requires delinquency/disqualification reconciliation')
    eligible_ids={s.segment_id for s in account.segments if s.segment_type in account.grace_applies_to_segment_types}
    shadow={id_:ZERO for id_ in sorted(eligible_ids)}
    statement_credits=[]
    active_statement=None
    grace_streak=0
    grace_decisions=[]
    if grace_terms is not None:
        term=grace_terms
        if term.statement.cycle != initial_cycle:
            raise ValueError('grace statement must match the opening minimum cycle exactly')
        if initial_cycle.due_date<start:
            raise MissingTerms('grace integration requires an unresolved opening statement')
        forward=[c for c in relevant if c.start_date>=initial_cycle.start_date]
        if any(c.end_date!=c.statement_date for c in forward):
            raise MissingTerms('grace replay requires coincident statement close and issue dates')
        if any(a.due_date>=b.end_date for a,b in zip(forward,forward[1:])):
            raise MissingTerms('overlapping statement due windows require explicit payment attribution')
        if any(initial_cycle.statement_date<c.statement_date<start for c in relevant):
            raise MissingTerms('opening statement must be the latest issued statement')
        if any(c.credited_on>=start for c in term.statement.credits):
            raise ValueError('opening grace credits must precede replay; simulated credits are added once')
        if any(s.compounding_method.value!=CompoundingMethod.SIMPLE_DAILY for s in account.segments if s.segment_id in eligible_ids):
            raise UnsupportedTerms('grace transition integration currently requires simple-daily purchase terms')
        rows={r.segment_id:r for r in term.opening_contingent}
        if len(rows)!=len(term.opening_contingent) or set(rows)!=eligible_ids:
            raise MissingTerms('explicit opening contingent amount required for every eligible segment')
        if any(r.through!=start-timedelta(days=1) for r in rows.values()):
            raise ValueError('opening contingent amounts must end immediately before replay')
        if term.last_resolved_state==GracePeriodState.PENDING:
            raise MissingTerms('last resolved opening state required')
        if account.current_grace_state!=GracePeriodState.PENDING and account.current_grace_state!=term.last_resolved_state:
            raise ValueError('account grace state contradicts supplied last resolved state')
        if term.last_resolved_state==GracePeriodState.LOST_GRACE and any(r.amount for r in rows.values()):
            raise ValueError('lost-grace interest belongs in actual accrual, not contingent opening')
        # Validate the opening restoration streak before the callback can run.
        resolve_grace(account.account_id,term.last_resolved_state,account.restoration_statements_required,(),start,
            opening_consecutive_full=term.consecutive_full_statements,opening_provenance=term.opening_provenance)
        shadow={k:r.amount for k,r in rows.items()}
        statement_credits=list(term.statement.credits)
        active_statement=term.statement
        grace_streak=term.consecutive_full_statements
    elif (account.current_grace_state!=GracePeriodState.LOST_GRACE
        and any(s.apr.value>0 and s.segment_id in eligible_ids for s in account.segments)
        and any(start<=c.due_date<=end for c in relevant)):
        raise MissingTerms('grace resolution across a due date requires the original full statement balance and payment history')
    current=account
    if grace_terms is not None:
        current=reconstruct(current,current_grace_state=grace_terms.last_resolved_state,
            consecutive_statements_paid_in_full=grace_streak)
    audit=[];paid=[];missed=[];contingent=sum(shadow.values(),ZERO);day=start
    if _checkpoint is not None:
        cp=_checkpoint
        if (cp.start!=start or cp.source_account!=account or cp.cycles!=tuple(relevant)
            or cp.initial_minimum!=initial_minimum or cp.grace_terms!=grace_terms or cp.promo_transitions!=promo_transitions):
            raise ValueError('resume inputs must match checkpoint context')
        if credit_timezone!=cp.credit_timezone:raise ValueError("resume creditor timezone must match checkpoint")
        if any(e.event_id in {old.event_id for old in cp.credit_events} for e in credit_events):raise ValueError("credit event ID reused across checkpoint")
        if end<=cp.as_of or any(d<=cp.as_of for d in payment_dates) or any(d<=cp.as_of for d in events_by_day):
            raise ValueError('resume dates must be strictly after checkpoint')
        current=cp.account
        minimums={r.cycle_id:r.remaining for r in cp.minimums}
        shadow={r.segment_id:r.amount for r in cp.shadow}
        active_statement=cp.active_statement
        statement_credits=list(active_statement.credits) if active_statement else []
        grace_streak=cp.grace_streak
        assessed_since_close=cp.assessed_since_close
        contingent=cp.contingent
        processed_events=list(cp.credit_events)
        paid=list(cp.payments);audit=list(cp.audit);missed=list(cp.missed_due_dates)
        grace_decisions=list(cp.grace_decisions)
        exits={e.segment_id:e for e in cp.promo_exits}
        histories={h.segment_id:list(h.balances) for h in cp.daily_histories}
        day=cp.as_of+timedelta(days=1)
    while day<=end:
        for credit_event in (events_by_day.get(day,[]) if credit_events else ([None] if day in payment_dates else [])):
            if credit_event is not None:processed_events.append(credit_event)
            outstanding=sum(minimums.values(),ZERO)
            if choose_decision is not None:
                view=debt_decision_view(day,current,outstanding,tuple(paid),tuple(exits.values()),promo_transitions)
                if credit_event is not None:view=reconstruct(view,event_id=credit_event.event_id,credited_at=credit_event.credited_at)
                desired=decimal_input(choose_decision(view))
            else:desired=decimal_input(choose_payment(day,current,outstanding,tuple(paid)))
            if desired<0:raise ValueError('negative payment')
            desired=desired.quantize(CENT,rounding=ROUND_DOWN)
            if desired:
                aggregate=MinimumPaymentSnapshot(account_id=account.account_id,billing_cycle_id='aggregate',statement_minimum_original=outstanding,statement_minimum_remaining=outstanding)
                result=allocate_payment(current,desired,aggregate,day,tuple(relevant),promo_exits=tuple(exits.values()))
                left={r.segment_id:r.amount for r in result.remaining_balances}
                current=reconstruct(current,segments=tuple(reconstruct(s,balance=left.get(s.segment_id,ZERO),balance_provenance=ProvenanceSource.ASSUMED_DEFAULT,balance_as_of_date=day) for s in current.segments))
                reduction=min(outstanding,result.applied)
                for id_ in sorted(minimums,key=lambda k:(dues[k],k)):
                    take=min(reduction,minimums[id_]);minimums[id_]-=take;reduction-=take
                paid.append(DebtPayment(on=day,amount=result.applied,
                    event_id=credit_event.event_id if credit_event else None,credited_at=credit_event.credited_at if credit_event else None))
                if active_statement is not None and day<=active_statement.cycle.due_date:
                    credit_id=f'replay-event:{credit_event.event_id}' if credit_event else f'replay:{day.isoformat()}'
                    if any(c.credit_id==credit_id for c in statement_credits):raise ValueError('reserved replay credit ID collision')
                    statement_credits.append(StatementCredit(credit_id=credit_id,credited_on=day,amount=result.applied))
                audit.extend(DebtAudit(on=day,kind='payment_'+r.phase,amount=r.amount,detail=r.segment_id) for r in result.lines)
        updated=[]
        for seg in current.segments:
            histories[seg.segment_id].append(DailyBalance(day=day,balance=seg.balance))
            exit_=exits.get(seg.segment_id)
            eligible=(transitions[seg.segment_id].post_exit_grace_eligible.value if exit_ else
                seg.segment_type in current.grace_applies_to_segment_types)
            grace=eligible and current.current_grace_state!=GracePeriodState.LOST_GRACE
            effective_apr=exit_.replacement_apr.value if exit_ else seg.apr.value
            effective_method=exit_.replacement_compounding.value if exit_ else seg.compounding_method.value
            rate=daily_rate(effective_apr,day,seg.day_count_convention.value)
            if grace:
                interest=ZERO
                if grace_terms is not None:
                    shadow[seg.segment_id]+=seg.balance*rate
                elif grace_terms is None and current.current_grace_state==GracePeriodState.PENDING:contingent+=seg.balance*rate
            else:
                base=seg.balance+(seg.accrued_unposted_interest if effective_method==CompoundingMethod.DAILY_COMPOUNDING else ZERO)
                interest=base*rate
            updated.append(reconstruct(seg,accrued_unposted_interest=seg.accrued_unposted_interest+interest,accrued_interest_provenance=ProvenanceSource.ASSUMED_DEFAULT,accrued_interest_as_of_date=day))
            if interest:audit.append(DebtAudit(on=day,kind='unposted_interest',amount=interest,detail=seg.segment_id))
        current=reconstruct(current,segments=tuple(updated))
        if active_statement is not None and day==active_statement.cycle.due_date:
            statement=reconstruct(active_statement,credits=tuple(statement_credits))
            resolution=resolve_grace(account.account_id,current.current_grace_state,account.restoration_statements_required,
                (statement,),day,opening_consecutive_full=grace_streak,
                opening_provenance=grace_terms.opening_provenance)
            if resolution.last_resolved_state==GracePeriodState.LOST_GRACE:
                updated=[]
                for seg in current.segments:
                    charge=shadow.get(seg.segment_id,ZERO)
                    updated.append(reconstruct(seg,accrued_unposted_interest=seg.accrued_unposted_interest+charge))
                    if charge:audit.append(DebtAudit(on=day,kind='grace_loss_unposted',amount=charge,detail=seg.segment_id))
                current=reconstruct(current,segments=tuple(updated))
            shadow={id_:ZERO for id_ in sorted(eligible_ids)}
            grace_streak=resolution.consecutive_full_statements
            grace_decisions.extend(resolution.decisions)
            active_statement=None
            statement_credits=[]
            current=reconstruct(current,current_grace_state=resolution.last_resolved_state,projected_grace_state=resolution.last_resolved_state,
                consecutive_statements_paid_in_full=grace_streak)
            audit.append(DebtAudit(on=day,kind='grace_resolution',amount=ZERO,detail=resolution.last_resolved_state.value))
        for id_,transition in transitions.items():
            if day!=transition.terms.cutoff:continue
            exit_=assess_promo_exit(originals[id_],tuple(histories[id_]),transition.terms,
                history_provenance=ProvenanceSource.ASSUMED_DEFAULT)
            exits[id_]=exit_
            assessed_since_close+=exit_.assessed_deferred_interest
            current=reconstruct(current,segments=tuple(reconstruct(seg,
                balance=seg.balance+exit_.assessed_deferred_interest,
                balance_provenance=ProvenanceSource.ASSUMED_DEFAULT,balance_as_of_date=day)
                if seg.segment_id==id_ else seg for seg in current.segments))
            audit.append(DebtAudit(on=day,kind='promo_exit',amount=exit_.assessed_deferred_interest,detail=id_))
        if grace_terms is not None:contingent=sum(shadow.values(),ZERO)
        for cycle in relevant:
            if cycle.end_date!=day:continue
            segments=[];posted_total=ZERO
            for seg in current.segments:
                posted=posting(seg.accrued_unposted_interest,current.rounding_mode.value);posted_total+=posted
                segments.append(reconstruct(seg,balance=seg.balance+posted,accrued_unposted_interest=ZERO,balance_provenance=ProvenanceSource.ASSUMED_DEFAULT,balance_as_of_date=day))
                if posted:audit.append(DebtAudit(on=day,kind='interest_posting',amount=posted,detail=seg.segment_id))
            current=reconstruct(current,segments=tuple(segments))
            if grace_terms is not None:
                if active_statement is not None:
                    raise MissingTerms('unresolved prior statement at close')
                active_statement=GraceStatement(cycle=cycle,original_statement_balance=current.total_balance())
                statement_credits=[]
                audit.append(DebtAudit(on=day,kind='grace_statement',amount=current.total_balance(),detail=cycle.cycle_id))
            if cycle.cycle_id not in minimums:
                fees=sum((s.balance for s in current.segments if s.segment_type==SegmentType.FEES_AND_PENALTIES),ZERO)
                minimums[cycle.cycle_id]=min(current.total_balance(),posting(projected_minimum(current.total_balance(),current.minimum_payment_floor.value,current.minimum_payment_rate.value,fees,posted_total+assessed_since_close),current.rounding_mode.value))
            assessed_since_close=ZERO
        for id_,amount in minimums.items():
            if dues[id_]==day and min(amount,current.total_balance())>0:missed.append(day)
        day+=timedelta(days=1)
    checkpoint=DebtCheckpoint(start=start,as_of=end,credit_timezone=credit_timezone,credit_events=tuple(processed_events),source_account=account,account=current,cycles=tuple(relevant),
        initial_minimum=initial_minimum,grace_terms=grace_terms,promo_transitions=promo_transitions,
        minimums=tuple(CycleMinimumState(cycle_id=k,remaining=v) for k,v in minimums.items()),
        shadow=tuple(GraceShadowState(segment_id=k,amount=v) for k,v in shadow.items()),
        active_statement=reconstruct(active_statement,credits=tuple(statement_credits)) if active_statement else None,
        grace_streak=grace_streak,assessed_since_close=assessed_since_close,contingent=contingent,
        payments=tuple(paid),audit=tuple(audit),missed_due_dates=tuple(sorted(set(missed))),
        promo_exits=tuple(exits.values()),daily_histories=tuple(SegmentDailyHistory(segment_id=k,balances=tuple(v)) for k,v in histories.items()),
        grace_decisions=tuple(grace_decisions))
    return DebtProjection(account=current,payments=tuple(paid),audit=tuple(audit),contingent_grace_interest=contingent,
        minimum_remaining=min(sum(minimums.values(),ZERO),current.total_balance()),missed_due_dates=tuple(sorted(set(missed))),
        grace_decisions=tuple(grace_decisions),grace_consecutive_full_statements=grace_streak,
        promo_exits=checkpoint.promo_exits,daily_histories=checkpoint.daily_histories,checkpoint=checkpoint)

@decimal_context
def debt_decision_view(on:date,account:RevolvingAccount,minimum:Decimal,previous:tuple[DebtPayment,...],
                       exits:tuple[PromoExitResult,...],transitions:tuple[PromoTransition,...])->DebtDecisionView:
    effective={e.segment_id:e for e in exits}
    supplied={t.segment_id:t for t in transitions}
    rows=[]
    for seg in account.segments:
        e=effective.get(seg.segment_id)
        rows.append(EffectiveSegmentView(segment_id=seg.segment_id,segment_type=seg.segment_type,
            balance=seg.balance,accrued_unposted_interest=seg.accrued_unposted_interest,
            apr=e.replacement_apr if e else seg.apr,
            compounding=e.replacement_compounding if e else seg.compounding_method,
            day_count=seg.day_count_convention,
            grace_eligible=supplied[seg.segment_id].post_exit_grace_eligible.value if e else seg.segment_type in account.grace_applies_to_segment_types,
            promo_exited=e is not None))
    return DebtDecisionView(on=on,account_id=account.account_id,segments=tuple(rows),
        effective_minimum=min(decimal_input(minimum),account.total_balance()),grace_state=account.current_grace_state,
        previous_payments=previous)


def resume_revolving(checkpoint:DebtCheckpoint,end:date,payment_dates:tuple[date,...],choose_payment:Callable|None=None,
                     *,choose_decision:Callable[[DebtDecisionView],Decimal]|None=None,
                     credit_events:tuple[DebtCreditEvent,...]=())->DebtProjection:
    """Continue after an end-of-day checkpoint; callbacks run only on new dates.

    The result contains cumulative history and a new checkpoint, so repeated
    serialization/resumption is equivalent to uninterrupted replay.
    """
    cp=DebtCheckpoint.model_validate(checkpoint.model_dump())
    return simulate_revolving(cp.source_account,cp.start,end,cp.cycles,cp.initial_minimum,payment_dates,choose_payment,
        choose_decision=choose_decision,grace_terms=cp.grace_terms,promo_transitions=cp.promo_transitions,credit_events=credit_events,credit_timezone=cp.credit_timezone,_checkpoint=cp)


class PromoPlanResult(StrictModel):
    search:SearchResult
    projection:DebtProjection
    target_remaining:Nonnegative
    no_additional_payments_projection:DebtProjection|None=None
    label:str='estimate'

@decimal_context
def plan_promo(account,target_segment_id,start,deadline,cycles,initial_minimum,payment_dates,
               openings,cash_plans,*,policies=(),max_evaluations=100000,buffer_days=5,payment_timing:PaymentTiming|None=None,
               grace_terms:GraceReplayTerms|None=None,
               promo_transitions:tuple[PromoTransition,...]=(),
               exposure_transitions:tuple[PromoTransition,...]=())->PromoPlanResult:
    """Candidate-dependent cash clipping with 90-day lookahead at every payment.
    Target-account payment timing comes from explicit sourced business-day delays.
    Explicit grace history is replayed independently for each candidate.
    Optional exposure transitions extend only the final selected schedule through
    their cutoffs, assuming no additional payments; they do not change the search.
    Omission uses a labeled same-day/noon-UTC assumption for backward compatibility.
    All other income/bills/transfers must be supplied through the lookahead horizon.
    """
    target=next((s for s in account.segments if s.segment_id==target_segment_id),None)
    if target is None or target.promo_expiration_date is None:raise ValueError('promotional target required')
    if any(t.segment_id==target_segment_id for t in promo_transitions):
        raise MissingTerms('target exits during planning; use debt-payoff replay instead of an active-promo search')
    if buffer_days<5 or deadline>target.promo_expiration_date-timedelta(days=buffer_days):
        raise ValueError('deadline must respect the explicit promo buffer (at least five days)')
    if any(t.terms.cutoff<=deadline for t in exposure_transitions):
        raise ValueError('exposure transitions must follow the planning deadline')
    if len({t.segment_id for t in promo_transitions+exposure_transitions})!=len(promo_transitions+exposure_transitions):
        raise ValueError('duplicate promo transition across planning and exposure horizons')
    primary=next((o.account_id for o in openings if o.primary),None)
    if primary is None:raise ValueError('primary cash account required')
    timing=payment_timing or assumed_same_day_timing()
    stamp_by_initiation={day:timing.stamps(day) for day in payment_dates}
    if len(stamp_by_initiation)!=len(payment_dates) or tuple(sorted(payment_dates))!=payment_dates:
        raise ValueError('payment initiation dates must be unique and sorted')
    initiation_by_credit={stamps[1].date():day for day,stamps in stamp_by_initiation.items()}
    same_day_events=len(initiation_by_credit)!=len(payment_dates)
    event_initiation={f'promo-credit:{i}':day for i,day in enumerate(payment_dates)}
    planned_events=tuple(sorted((DebtCreditEvent(event_id=id_,credited_at=stamp_by_initiation[day][1],sequence=i)
        for i,(id_,day) in enumerate(event_initiation.items())),key=lambda e:e.ordering_key())) if same_day_events else ()
    credited_dates=tuple(sorted(initiation_by_credit))
    if any(day>deadline for day in credited_dates):raise ValueError('credit date misses buffered deadline')
    def initiated_for(payment):
        return event_initiation[payment.event_id] if payment.event_id is not None else initiation_by_credit[payment.on]
    def at(day):return timing.stamps(day)[0]
    t0=at(start)
    if any(p.plan_id.startswith('promo-simulation:') for p in cash_plans):raise ValueError('reserved plan prefix')
    def cash_state(day,previous):
        history=[]
        for i,p in enumerate(previous):
            if not p.amount:continue
            initiated,credited,debited,settled=stamp_by_initiation[initiated_for(p)]
            history.append(CashPlan(plan_id=f'promo-simulation:{i}',kind=CashKind.PAYMENT,amount=p.amount,
                source_account_id=primary,initiated_at=initiated,credited_at=credited,debited_at=debited,settled_at=settled))
        history=tuple(history)
        cash=project_liquidity(openings,cash_plans+history,t0,horizon_days=(day-start).days+90,policies=())
        return cash
    def feasible(day,previous):
        cash=cash_state(day,previous)
        # Only actual planned transfers fund this integration. Even a zero-day
        # eligible secondary account needs a transfer event before checking pays.
        before=[p for p in cash.points if p.at<=at(day)]
        window=(before[-1],)+tuple(p for p in cash.points if p.at>at(day))
        if any(p.status.value!='healthy' for p in cash.points):return ZERO
        return max(ZERO,min(p.accessible_above_floors for p in window)).quantize(CENT,rounding=ROUND_DOWN)
    high=max((feasible(day,()) for day in payment_dates),default=ZERO)
    def run(candidate):
        if same_day_events:
            def choose_event(view):
                return min(candidate,feasible(event_initiation[view.event_id],view.previous_payments),sum((s.balance for s in view.segments),ZERO))
            return simulate_revolving(account,start,deadline,cycles,initial_minimum,(),
                choose_decision=choose_event,credit_events=planned_events,credit_timezone=timing.timezone_name,
                grace_terms=grace_terms,promo_transitions=promo_transitions+exposure_transitions)
        def choose(day,current,minimum,previous):return min(candidate,feasible(initiation_by_credit[day],previous),current.total_balance())
        return simulate_revolving(account,start,deadline,cycles,initial_minimum,credited_dates,choose,
            grace_terms=grace_terms,promo_transitions=promo_transitions+exposure_transitions)
    def evaluate(candidate):
        projection=run(candidate)
        remaining=next(s.balance for s in projection.account.segments if s.segment_id==target_segment_id)
        final_day=max(payment_dates,default=start)
        cash_ok=all(p.status.value=='healthy' for p in cash_state(final_day,projection.payments).points)
        return max(CENT,remaining) if projection.missed_due_dates or not cash_ok else remaining
    search=bounded_payment_search(evaluate,high,monotone_contract=False,max_evaluations=max_evaluations)
    projection=run(search.candidate)
    exposure_projection=None
    if exposure_transitions:
        exposure_projection=resume_revolving(projection.checkpoint,max(t.terms.cutoff for t in exposure_transitions),
            (),lambda *args:ZERO)
    return PromoPlanResult(search=search,projection=projection,
        target_remaining=next(s.balance for s in projection.account.segments if s.segment_id==target_segment_id),
        no_additional_payments_projection=exposure_projection)
