"""Saved account wizard -> explicit cash/calendar inputs -> existing payoff engine.

No financial arithmetic is implemented here. Unknown contract/cash inputs block
conversion; generated dates are displayed as assumptions before a signed save.
"""
from datetime import date,datetime,time,timedelta
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from hashlib import sha256
import os,tempfile,re
from pydantic import Field,model_validator
from SCHEMA import (StrictModel,Sourced,ProvenanceSource as P,DayCountConvention,RoundingMode,IncomeCadence,
    SemimonthlyShortMonthRule,BalanceSegment,SegmentType,CompoundingMethod,RevolvingAccount,
    AllocationRule,AllocationRuleType,GracePeriodState,BillingCycle,MinimumPaymentSnapshot,
    InstallmentLoan,LoanType,PrepaymentBehavior,assumed_default)
from engine.common import Nonnegative,CENT,ZERO,decimal_context,reconstruct
from engine.liquidity import CashOpening,CashPlan,CashKind
from engine.minimum_forecast import PaymentSlot
from engine.portfolio import PortfolioDebt
from engine.payoff import PaymentFunding,cash_horizon
from engine.payoff_calendar import _local,monthly_occurrence
from engine.schedules import scheduled_dates
from engine.mixed_payoff import MixedPayoffInputs,PayoffLoan
from dashboard.mixed_payoff_runs import MixedPayoffRun,AccountLabel
from payoff_cli import _parse_json


class Settings(StrictModel):
    balance_date: date|None=None
    end: date|None=None
    timezone: str|None=None
    primary: str|None=None
    target: Nonnegative|None=None
    first_payment: date|None=None
    cadence: Literal['weekly','biweekly','monthly']|None=None
    payment_time: time|None=None
    credit_days: int|None=Field(default=None,ge=0,le=14)
    debit_days: int|None=Field(default=None,ge=0,le=14)
    settlement_days: int|None=Field(default=None,ge=0,le=14)
    short_month: SemimonthlyShortMonthRule|None=None
    reviewed: Literal['yes','no']='no'
    pending: Literal['unknown','none','present']='unknown'

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        if self.timezone:
            try:ZoneInfo(self.timezone)
            except (KeyError,ValueError) as exc:raise ValueError('Choose a valid timezone') from exc
        if self.target is not None and self.target%CENT:raise ValueError('Payment target needs whole cents')
        if self.payment_time is not None and self.payment_time.tzinfo is not None:raise ValueError('Use a local clock')
        if self.balance_date and self.end and not 0<(self.end-self.balance_date).days<=3660:raise ValueError('End must be within ten years after the balance date')
        return self


class Terms(StrictModel):
    account_id: str
    day_count: DayCountConvention|None=None
    rounding: RoundingMode|None=None
    accrued: Nonnegative|None=None
    fees: Nonnegative|None=None
    ordinary: Literal['unknown','yes','no']='unknown'
    previous_start: date|None=None
    previous_close: date|None=None
    next_close: date|None=None
    next_due: date|None=None
    close_day: int|None=Field(default=None,ge=1,le=31)
    due_day: int|None=Field(default=None,ge=1,le=31)
    original_minimum: Nonnegative|None=None
    minimum_floor: Nonnegative|None=None
    minimum_rate: Nonnegative|None=None
    monthly: Literal['unknown','yes','no']='unknown'

    @model_validator(mode='after')
    @decimal_context
    def cents(self):
        if any(v is not None and v%CENT for v in (self.fees,self.original_minimum,self.minimum_floor)):raise ValueError('Fees and minimums need whole cents')
        if self.day_count==DayCountConvention.THIRTY_360:raise ValueError('This planner does not support 30/360 interest')
        return self


class Flow(StrictModel):
    flow_id: str=Field(pattern=r'^[0-9a-f]{32}$')
    kind: Literal['income','expense','transfer','contribution']
    name: str=Field(min_length=1,max_length=100)
    amount: Nonnegative|None=None
    first_date: date|None=None
    cadence: Literal['once','weekly','biweekly','monthly']|None=None
    clock: time|None=None
    until: date|None=None
    source: str|None=None
    destination: str|None=None
    debit_days: int|None=Field(default=None,ge=0,le=14)
    credit_days: int|None=Field(default=None,ge=0,le=14)
    settlement_days: int|None=Field(default=None,ge=0,le=14)
    include: Literal['review','yes','no']='review'
    notes: str=Field(default='',max_length=2000)
    origin_key: str|None=Field(default=None,max_length=100)

    @model_validator(mode='after')
    @decimal_context
    def valid(self):
        if not self.name.strip():raise ValueError('Name the income, bill or transfer')
        if self.amount is not None and self.amount%CENT:raise ValueError('Cash events need whole cents')
        if self.clock is not None and self.clock.tzinfo is not None:raise ValueError('Use a local clock')
        if self.until is not None and self.first_date is not None and self.until<self.first_date:raise ValueError('Stop date precedes first date')
        if self.kind=='income' and self.source is not None or self.kind=='expense' and self.destination is not None:raise ValueError('Cash event has an unexpected account endpoint')
        if self.cadence=='once' and self.until is not None:raise ValueError('One-time events do not have stop dates')
        return self


class Planning(StrictModel):
    format: Literal['debt-shredder-wizard-planning']='debt-shredder-wizard-planning'
    version: Literal[1]=1
    settings: Settings=Field(default_factory=Settings)
    terms: tuple[Terms,...]=Field(default=(),max_length=40)
    flows: tuple[Flow,...]=Field(default=(),max_length=80)

    @model_validator(mode='after')
    def unique(self):
        if len({v.account_id for v in self.terms})!=len(self.terms) or len({v.flow_id for v in self.flows})!=len(self.flows):raise ValueError('Duplicate planning record')
        keys=[f.origin_key for f in self.flows if f.origin_key]
        if len(set(keys))!=len(keys):raise ValueError('Duplicate imported cash event')
        return self


def path(directory,identifier):
    if not re.fullmatch('[0-9a-f]{32}',identifier):raise ValueError('Invalid setup ID')
    return Path(directory)/'account_wizards'/'planning'/(identifier+'.json')


def load(directory,identifier):
    p=path(directory,identifier)
    try:
        with p.open('rb') as stream:raw=stream.read(512*1024+1)
    except FileNotFoundError:return Planning()
    if len(raw)>512*1024:raise ValueError('Planning file too large')
    return Planning.model_validate(_parse_json(raw))


def digest(value):return sha256(value.model_dump_json().encode()).hexdigest()


def context(wizard,planning):
    from dashboard.payoff_setup import fingerprint
    return sha256((fingerprint(wizard)+digest(planning)).encode()).hexdigest()


def save(directory,identifier,value,previous):
    target=path(directory,identifier)
    if digest(load(directory,identifier))!=digest(previous):raise ValueError('Planning inputs changed; reopen before saving')
    raw=value.model_dump_json(indent=2).encode()
    if len(raw)>512*1024:raise ValueError('Planning file too large')
    value=Planning.model_validate(_parse_json(raw));target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        history=target.parent/'history';history.mkdir(exist_ok=True)
        backup=history/(identifier+'-'+digest(previous)+'.json')
        if not backup.exists():
            with backup.open('x') as stream:stream.write(previous.model_dump_json(indent=2))
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.planning-',delete=False) as stream:
            temporary=Path(stream.name);stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,target);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def term_for(planning,account_id):return next((t for t in planning.terms if t.account_id==account_id),Terms(account_id=account_id))


def update_terms(planning,value):
    return reconstruct(planning,terms=tuple(t for t in planning.terms if t.account_id!=value.account_id)+(value,))


def update_flow(planning,value):
    return reconstruct(planning,flows=tuple(f for f in planning.flows if f.flow_id!=value.flow_id)+(value,))


def participating_banks(wizard,p):
    """Only explicitly routed cash participates; other money cannot fund payments."""
    ids={p.settings.primary} if p.settings.primary else set()
    ids.update(a.payment_from for a in wizard.accounts if a.kind in ('card','loan') and a.balance!=0 and a.payment_from)
    for f in p.flows:
        if f.include=='yes' and f.amount!=0:ids.update(k for k in (f.source,f.destination) if k)
    return ids


def balance_accounts(wizard,p):
    """Debts and explicitly used cash only; unused savings stay outside the plan."""
    participating=participating_banks(wizard,p)
    return tuple(a for a in wizard.accounts if a.kind in ('card','loan') or a.account_id in participating)


def balance_fields(account):
    return ('balance','balance_date','floor','reserved') if account.kind in ('checking','savings') else ('balance','balance_date')


def change_balances(wizard,p,values):
    expected={a.account_id+'__'+k for a in balance_accounts(wizard,p) for k in balance_fields(a)}
    if set(values)!=expected:raise ValueError('Use the starting-balance update form')
    accounts=[]
    active={a.account_id for a in balance_accounts(wizard,p)}
    for a in wizard.accounts:
        if a.account_id not in active:accounts.append(a);continue
        updates={k:(None if values[a.account_id+'__'+k]=='' else values[a.account_id+'__'+k]) for k in balance_fields(a)}
        accounts.append(reconstruct(a,**updates))
    return reconstruct(wizard,accounts=tuple(accounts),revision=wizard.revision+1)


def missing(wizard,p):
    """Only fields required by conversion. Credit limits, APY and autopay are optional."""
    result=[];s=p.settings
    def need(condition,label,where):
        if condition:result.append((label,where))
    required=('balance_date','end','timezone','primary','target','first_payment','cadence','payment_time','credit_days','debit_days','settlement_days','short_month')
    need(any(getattr(s,k) is None for k in required),'Finish the forecast dates, shared target and payment timing.','settings')
    need(s.pending!='none','Confirm that pending withdrawals, holds and transfers crossing the opening date are reconciled before projecting.','settings')
    need(s.reviewed!='yes','Review the starting balances, forward living costs and calendar assumptions.','settings')
    if s.balance_date and s.first_payment:
        need(s.first_payment<=s.balance_date,'The first payment must follow the reconciled balance date.','settings')
    if s.first_payment and s.end:
        need(s.first_payment>s.end or (s.settlement_days is not None and (s.end-s.first_payment).days<s.settlement_days),'Allow time for at least one complete payment round before the forecast ends.','settings')
    if all(v is not None for v in (s.credit_days,s.debit_days,s.settlement_days)):
        need(not s.credit_days<=s.debit_days<=s.settlement_days,'Payment timing must put creditor credit before or on bank debit, then settlement. Review the calendar-day delays.','settings')
    banks={a.account_id:a for a in wizard.accounts if a.kind in ('checking','savings')}
    need(s.primary is not None and s.primary not in banks,'Choose a known bank account as the primary account.','settings')
    debts=[a for a in wizard.accounts if a.kind in ('card','loan')]
    need(not banks,'Add a bank account before calculating.','accounts')
    need(not debts or len([a for a in debts if a.balance!=0])>10,'The payoff engine needs 1–10 active debts.','accounts')
    need(bool(debts) and all(a.balance==0 for a in debts),'No positive debt balance remains to project.','accounts')
    participating=participating_banks(wizard,p)
    for index,a in enumerate(wizard.accounts):
        if a.kind in ('checking','savings') and a.account_id not in participating:continue
        where='account/'+str(index)
        need(a.balance is None,a.name+': enter its balance.',where)
        need(a.balance_date is None or (s.balance_date is not None and a.balance_date!=s.balance_date),a.name+': reconcile its balance to the common starting date.',where)
        if a.kind in ('checking','savings'):
            need(a.floor is None or a.reserved is None,a.name+': enter its cash cushion and reserved amount (explicit 0 is allowed).',where)
            continue
        if a.balance==0:continue
        need(a.apr is None or a.minimum is None or a.due_date is None,a.name+': finish its rate, required payment and due date.',where)
        need(a.payment_from not in banks,a.name+': choose which bank account pays it.',where)
        need(a.due_date is not None and s.balance_date is not None and a.due_date<=s.balance_date,a.name+': an overdue opening payment needs reconciliation before projecting.',where)
        if a.kind=='card':need(a.promo!='none',a.name+': promotional or unknown rate terms need a supported review before calculation.',where)
        else:
            need(a.loan_type!='simple' or a.prepayment!='principal' or a.balance_type!='principal',a.name+': this plan requires confirmed simple interest, remaining principal and principal-curtailment payments.',where)
            need(a.note_rate is None,a.name+': enter the contractual note rate.',where)
        t=term_for(p,a.account_id);keys=('day_count','rounding','accrued')
        keys+=('ordinary','previous_start','previous_close','next_close','next_due','close_day','due_day','original_minimum','minimum_floor','minimum_rate') if a.kind=='card' else ('fees','due_day','monthly')
        need(any(getattr(t,k) is None or getattr(t,k)=='unknown' for k in keys),a.name+': finish the calculation terms.','terms/'+a.account_id)
        if a.kind=='card':need(t.ordinary=='no',a.name+': mixed purchase/cash-advance balances are unsupported.','terms/'+a.account_id)
        else:need(t.monthly=='no',a.name+': this entry path currently needs monthly loan installments.','terms/'+a.account_id)
        term_where='terms/'+a.account_id
        if a.kind=='card':
            if all(v is not None for v in (t.previous_start,t.previous_close,t.next_close,t.next_due,s.balance_date,a.due_date)):
                need(not (t.previous_start<t.previous_close<=s.balance_date<t.next_close<t.next_due and a.due_date<t.next_due),a.name+': review the previous and next statement dates and their payment due dates.',term_where)
            if a.minimum is not None and t.original_minimum is not None:
                need(a.minimum>t.original_minimum,a.name+': the unpaid minimum cannot exceed its original statement minimum. Check both figures.',term_where)
            if s.short_month is not None:
                if t.next_close and t.close_day:
                    need(t.next_close!=monthly_occurrence(t.next_close.year,t.next_close.month,t.close_day,s.short_month),a.name+': its next statement close does not match the selected monthly closing day.',term_where)
                if t.next_close and t.next_due and t.due_day and t.next_close.year<9999:
                    expected=monthly_occurrence(t.next_close.year+(t.next_close.month==12),t.next_close.month%12+1,t.due_day,s.short_month)
                    need(t.next_due!=expected,a.name+': the next statement due date must match its following-month due-day rule.',term_where)
        else:
            need(a.minimum is not None and a.minimum<=0,a.name+': a positive loan balance needs a positive required installment.',where)
            if a.due_date and t.due_day and s.short_month is not None:
                occurrences=scheduled_dates(IncomeCadence.MONTHLY,a.due_date,a.due_date,a.due_date,day_of_month=t.due_day,short_month_rule=s.short_month)
                need(not occurrences,a.name+': its next installment does not match the monthly due-day rule.',term_where)
    for f in p.flows:
        where='flow/'+f.flow_id
        need(f.include=='review',f.name+': confirm whether to include this cash event.',where)
        if f.include!='yes':continue
        keys=('amount','first_date','cadence','clock')
        keys+=('destination',) if f.kind=='income' else ('source',) if f.kind=='expense' else ('source','destination','debit_days','credit_days','settlement_days')
        need(any(getattr(f,k) is None for k in keys),f.name+': complete its amount, schedule and account routing.',where)
        need(any(k is not None and k not in banks for k in (f.source,f.destination)),f.name+': choose known bank accounts.',where)
        if f.kind in ('transfer','contribution'):need(f.source is not None and f.source==f.destination,f.name+': transfer endpoints must differ.',where)
        if f.kind in ('transfer','contribution') and all(v is not None for v in (f.debit_days,f.credit_days,f.settlement_days)):
            need(not f.debit_days<=f.credit_days<=f.settlement_days,f.name+': bank debit must come before or on arrival, then settlement. Review the calendar-day delays.',where)
        if s.balance_date is not None:need(f.first_date is not None and f.first_date<=s.balance_date,f.name+': its first date must follow the reconciled starting balances; already-received money is not added again.',where)
    return result


def src(value):return Sourced[type(value)](value=value,provenance=P.USER_PROVIDED_ESTIMATE)


@decimal_context
def build(wizard,p,wizard_id=None):
    errors=missing(wizard,p)
    if errors:raise ValueError('Some required inputs still need review')
    s=p.settings;tz=ZoneInfo(s.timezone);first=s.balance_date+timedelta(days=1)
    start=_local(first,time(),tz);end=_local(s.end+timedelta(days=1),time(),tz)-timedelta(microseconds=1)
    if end<start:raise ValueError('Forecast end precedes the first forecast day')
    if s.first_payment<first:raise ValueError('First payment must follow the reconciled balance date')
    if not s.credit_days<=s.debit_days<=s.settlement_days:raise ValueError('Payment timing needs credit <= debit <= settlement delays')
    slots=[]
    for key,day in scheduled_dates(IncomeCadence(s.cadence),s.first_payment,first,s.end,day_of_month=s.first_payment.day,short_month_rule=s.short_month):
        stamps=tuple(_local(day+timedelta(days=n),s.payment_time,tz) for n in (0,s.credit_days,s.debit_days,s.settlement_days))
        if stamps[-1]>end:continue
        slots.append(PaymentSlot(slot_id='wizard:'+key,**dict(zip(('initiated_at','credited_at','debited_at','settled_at'),stamps))))
    if not 1<=len(slots)<=120:raise ValueError('Choose a horizon with 1–120 complete payment rounds')
    openings=tuple(CashOpening(account_id=a.account_id,cleared=a.balance,floor=a.floor,reserved=a.reserved,primary=a.account_id==s.primary,provenance=P.USER_PROVIDED_ESTIMATE) for a in wizard.accounts if a.kind in ('checking','savings') and a.account_id in participating_banks(wizard,p))
    primary=next(o for o in openings if o.primary);additional=tuple(o for o in openings if not o.primary)
    # Cash horizon is identical to the shared planner, including its 90-day tail.
    horizon=max(end,start+timedelta(days=90),*(v.initiated_at+timedelta(days=90) for v in slots))
    plans=[]
    for f in p.flows:
        if f.include!='yes' or f.amount==0:continue
        cadence=IncomeCadence.IRREGULAR if f.cadence=='once' else IncomeCadence(f.cadence)
        last=min(horizon.astimezone(tz).date(),f.until or horizon.astimezone(tz).date())
        if f.first_date>last:continue
        for key,day in scheduled_dates(cadence,f.first_date,first,last,day_of_month=f.first_date.day,short_month_rule=s.short_month):
            initiated=_local(day,f.clock,tz)
            if not start<=initiated<=horizon:continue
            if f.kind in ('income','expense'):stamps=(initiated,)*4
            else:
                if not f.debit_days<=f.credit_days<=f.settlement_days:raise ValueError(f.name+': transfer timing needs debit <= credit <= settlement')
                stamps=tuple(_local(day+timedelta(days=n),f.clock,tz) for n in (0,f.debit_days,f.credit_days,f.settlement_days))
            plans.append(CashPlan(plan_id='wizard-cash:'+f.flow_id+':'+key,kind=CashKind(f.kind),amount=f.amount,
                source_account_id=f.source if f.kind!='income' else None,destination_account_id=f.destination if f.kind!='expense' else None,
                **dict(zip(('initiated_at','debited_at','credited_at','settled_at'),stamps)),provenance=P.USER_PROVIDED_ESTIMATE))
            if len(plans)>2000:raise ValueError('More than 2000 cash events; shorten the horizon or simplify the declared schedule')
    cards=[];loans=[];routes=[]
    for a in wizard.accounts:
        if a.kind not in ('card','loan') or a.balance==0:continue
        t=term_for(p,a.account_id);key=a.account_id
        if a.due_date<first:raise ValueError(a.name+': an overdue opening minimum needs reconciliation before projection')
        routes.append(PaymentFunding(debt_account_id=key,cash_account_id=a.payment_from))
        if a.kind=='card':
            if not t.previous_start<t.previous_close<first<=t.next_close<t.next_due or not a.due_date<t.next_due:raise ValueError(a.name+': check its previous/next statement dates and due dates')
            if a.minimum>t.original_minimum:raise ValueError(a.name+': unpaid minimum exceeds the original statement minimum')
            if t.next_close!=monthly_occurrence(t.next_close.year,t.next_close.month,t.close_day,s.short_month):raise ValueError(a.name+': next close conflicts with future monthly dates')
            expected_due=monthly_occurrence(t.next_close.year+(t.next_close.month==12),t.next_close.month%12+1,t.due_day,s.short_month)
            if t.next_due!=expected_due:raise ValueError(a.name+': next due date conflicts with its following-month due-day rule')
            segment=BalanceSegment(account_id=key,segment_id='purchases',segment_type=SegmentType.STANDARD_PURCHASE,balance=a.balance,
                balance_provenance=P.USER_PROVIDED_ESTIMATE,balance_as_of_date=s.balance_date,accrued_unposted_interest=t.accrued,
                accrued_interest_provenance=P.USER_PROVIDED_ESTIMATE,accrued_interest_as_of_date=s.balance_date,
                apr=src(a.apr/100),compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY),day_count_convention=src(t.day_count))
            account=RevolvingAccount(account_id=key,issuer=a.name,segments=(segment,),current_grace_state=GracePeriodState.LOST_GRACE,
                statement_close_day=t.close_day,payment_due_day=t.due_day,minimum_payment_floor=src(t.minimum_floor),minimum_payment_rate=src(t.minimum_rate/100),rounding_mode=src(t.rounding),
                allocation_rule=AllocationRule(account_id=key,minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)))
            cycles=[BillingCycle(account_id=key,cycle_id='opening',start_date=t.previous_start,end_date=t.previous_close,statement_date=t.previous_close,due_date=a.due_date),
                BillingCycle(account_id=key,cycle_id='current',start_date=t.previous_close+timedelta(days=1),end_date=t.next_close,statement_date=t.next_close,due_date=t.next_due)]
            while cycles[-1].end_date<s.end:
                begin=cycles[-1].end_date+timedelta(days=1);y,m=begin.year,begin.month
                close=monthly_occurrence(y,m,t.close_day,s.short_month)
                if close<begin:close=monthly_occurrence(y+(m==12),m%12+1,t.close_day,s.short_month)
                due=monthly_occurrence(close.year+(close.month==12),close.month%12+1,t.due_day,s.short_month)
                cycles.append(BillingCycle(account_id=key,cycle_id='generated:'+close.isoformat(),start_date=begin,end_date=close,statement_date=close,due_date=due))
            cards.append(PortfolioDebt(account=account,cycles=tuple(cycles),credit_timezone=s.timezone,initial_minimum=MinimumPaymentSnapshot(account_id=key,billing_cycle_id='opening',statement_minimum_original=t.original_minimum,statement_minimum_remaining=a.minimum,provenance=P.USER_PROVIDED_ESTIMATE,as_of_date=s.balance_date)))
        else:
            if a.minimum<=0:raise ValueError(a.name+': a positive-balance loan needs a positive contractual installment')
            events=scheduled_dates(IncomeCadence.MONTHLY,a.due_date,first,s.end+timedelta(days=62),day_of_month=t.due_day,short_month_rule=s.short_month)
            dates=[]
            for _,d in events:
                dates.append(d)
                if d>=s.end:break
            dates=tuple(dates)
            if not dates or dates[0]!=a.due_date:raise ValueError(a.name+': next installment date conflicts with its monthly due-day rule')
            loan=InstallmentLoan(loan_id=key,servicer=a.name,loan_type=LoanType.SIMPLE_INTEREST,principal_balance=a.balance,accrued_interest=t.accrued,fees_outstanding=t.fees,
                balances_provenance=P.USER_PROVIDED_ESTIMATE,balances_as_of_date=s.balance_date,contract_note_rate=src(a.note_rate/100),disclosed_apr=src(a.apr/100),
                day_count_convention=src(t.day_count),contractual_payment_amount=src(a.minimum),payment_due_day=t.due_day,next_due_date=a.due_date,
                prepayment_behavior=src(PrepaymentBehavior.PRINCIPAL_ONLY_CURTAILMENT),rounding_mode=src(t.rounding))
            loans.append(PayoffLoan(loan=loan,timezone_name=s.timezone,due_dates=dates))
    inputs=MixedPayoffInputs(start=start,end=end,cards=tuple(cards),loans=tuple(loans),opening=primary,additional_openings=additional,payment_sources=tuple(routes),cash_plans=tuple(plans),slots=tuple(slots),payment_target=s.target)
    return MixedPayoffRun(name='My payoff plan' if wizard.origin=='personal' else 'Practice: wizard payoff plan',origin='supplied_estimate' if wizard.origin=='personal' else 'synthetic_demo',inputs=inputs,wizard_id=wizard_id,account_labels=tuple(AccountLabel(account_id=a.account_id,name=a.name) for a in wizard.accounts))


def import_cash(directory,wizard,p):
    """Copy only stored facts; no repayment, recurrence or payment status inferred."""
    if wizard.origin=='practice':raise ValueError('Saved personal cash is not imported into practice setups')
    from uuid import uuid4
    from dashboard import my_money,bills
    flows=list(p.flows);keys={f.origin_key for f in flows if f.origin_key}
    try:snapshot=my_money.load(directory)
    except FileNotFoundError:snapshot=None
    if snapshot and not my_money.needs_next_payday(snapshot):
        key='paycheck:'+snapshot.expected_payday.isoformat()
        if key not in keys:
            flows.append(Flow(flow_id=uuid4().hex,kind='income',name='Saved expected paycheck',amount=snapshot.expected_paycheck,first_date=snapshot.expected_payday,
                origin_key=key,notes='Copied from My Money as an expected amount/date. Confirm its frequency, receiving account and availability time. Already received pay must not be added again.'))
    try:book=bills.load(directory)
    except FileNotFoundError:book=None
    if book:
        for bill in book.bills:
            key='bill:'+bill.bill_id
            if bill.cash_kind=='debt_payment' or key in keys:continue
            flows.append(Flow(flow_id=uuid4().hex,kind='expense',name=bill.name,amount=bill.amount,first_date=bill.due,cadence='once',
                include='no' if bill.status in ('covered','exclude') else 'review',origin_key=key,
                notes=('Copied as ONE dated event; no recurring frequency or autopay clearance inferred. Original funding description: '+bills.ROUTES[bill.route]+'. '+bill.note)[:2000]))
    # Reuse stored spending/transfer AMOUNTS, but never infer their recurrence,
    # payment route, first date or bank settlement time from the old week view.
    keys={f.origin_key for f in flows if f.origin_key}
    from dashboard import payday_cash,paycheck_week
    try:budget=payday_cash.load_budget(directory)
    except FileNotFoundError:budget=None
    if budget:
        for key,name,amount in (('budget:food','Saved food budget',budget.food),('budget:fuel','Saved fuel budget',budget.fuel)):
            if key not in keys:flows.append(Flow(flow_id=uuid4().hex,kind='expense',name=name,amount=amount,origin_key=key,
                notes='Amount copied from the saved spending budget. Confirm its first date, frequency, source account and time; it is not a record of spending already cleared.'))
    try:settings=paycheck_week.load_settings(directory)
    except FileNotFoundError:settings=None
    if settings:
        for key,name,amount in (('standing:bills-box','Saved Bills Box funding',settings.bills_box_transfer),('standing:kc','Saved KC funding',settings.kc_transfer)):
            if key not in keys:flows.append(Flow(flow_id=uuid4().hex,kind='transfer',name=name,amount=amount,origin_key=key,
                notes='Amount copied from saved paycheck-transfer settings. Confirm the next initiation, recurrence, physical accounts and settlement delays. Already-completed transfers are not repeated.'))
    return reconstruct(p,flows=tuple(flows))
