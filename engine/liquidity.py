from datetime import datetime, timedelta, date, timezone
from enum import Enum
from decimal import Decimal
from itertools import groupby
from pydantic import field_validator, model_validator
from SCHEMA import StrictModel, FinancialSnapshot, CashFlowStatus, ProvenanceSource, TransferTimingPolicy
from engine.common import (ZERO, Money, Nonnegative, Positive, decimal_context, MissingTerms,
                           projection_label)

class CashKind(str,Enum):
    INCOME='income'
    EXPENSE='expense'
    PAYMENT='payment'
    TRANSFER='transfer'
    CONTRIBUTION='contribution'
    RESERVE='reserve'  # increase reserve within the same physical account

class CashOpening(StrictModel):
    account_id:str
    cleared:Money
    reserved:Nonnegative=ZERO
    committed:Nonnegative=ZERO
    held:Nonnegative=ZERO
    floor:Nonnegative
    primary:bool=False
    eligible:bool=False
    provenance:ProvenanceSource=ProvenanceSource.ASSUMED_DEFAULT

class CashPlan(StrictModel):
    plan_id:str
    kind:CashKind
    amount:Positive
    source_account_id:str|None=None
    destination_account_id:str|None=None
    initiated_at:datetime
    credited_at:datetime
    debited_at:datetime
    settled_at:datetime
    provenance:ProvenanceSource=ProvenanceSource.ASSUMED_DEFAULT

    @field_validator('initiated_at','credited_at','debited_at','settled_at')
    @classmethod
    def aware(cls,v):
        if v.utcoffset() is None:raise ValueError('planned timestamps must be timezone aware')
        return v.astimezone(timezone.utc)

    @model_validator(mode='after')
    def validate_plan(self):
        if self.kind in (CashKind.TRANSFER,CashKind.CONTRIBUTION):
            ordered=(self.initiated_at,self.debited_at,self.credited_at,self.settled_at)
            if not self.source_account_id or not self.destination_account_id or self.source_account_id==self.destination_account_id:
                raise ValueError('transfer requires two different physical accounts')
        elif self.kind==CashKind.PAYMENT:
            ordered=(self.initiated_at,self.credited_at,self.debited_at,self.settled_at)
            if not self.source_account_id or self.destination_account_id is not None:
                raise ValueError('payment requires source cash account, not a destination cash account')
        else:
            ordered=(self.initiated_at,self.debited_at,self.credited_at,self.settled_at)
            if len(set(ordered))!=1:raise ValueError('income, expense and reserve events are atomic')
            if self.kind==CashKind.INCOME:
                if self.source_account_id is not None or not self.destination_account_id:
                    raise ValueError('income requires only destination')
            elif not self.source_account_id or self.destination_account_id is not None:
                raise ValueError('expense/reserve requires only source')
        if tuple(sorted(ordered))!=ordered:raise ValueError('invalid transaction lifecycle order')
        return self

class CashPosition(StrictModel):
    account_id:str
    cleared:Money
    committed:Nonnegative
    held:Nonnegative
    reserved:Nonnegative
    unrestricted:Money
    above_floor:Money

class CashPoint(StrictModel):
    at:datetime
    positions:tuple[CashPosition,...]
    in_transit:Nonnegative
    aggregate_cash:Money
    accessible_above_floors:Money
    status:CashFlowStatus
    trigger_ids:tuple[str,...]=()

class CashAudit(StrictModel):
    at:datetime
    plan_id:str
    stage:str
    kind:CashKind
    amount:Positive
    source_account_id:str|None
    destination_account_id:str|None

class LiquidityProjection(StrictModel):
    start:datetime
    end:datetime
    safe_immediate_payment:Nonnegative
    status:CashFlowStatus
    first_breach_at:datetime|None
    peak_shortfall:Nonnegative
    points:tuple[CashPoint,...]
    audit:tuple[CashAudit,...]
    external_income:Nonnegative
    external_outflows:Nonnegative
    label:str


@decimal_context
def openings_from_snapshot(snapshot:FinancialSnapshot)->tuple[CashOpening,...]:
    """Adapter for a reconciled opening snapshot. Unresolved actuals need reconciliation.

    Prospective lifecycle plans are separate from actual Payment/Transfer records.
    Refuse unexplained pending amounts, avoiding both double counting and silent loss.
    """
    if any(a.pending_credits or a.pending_debits for a in snapshot.liquidity_accounts):
        raise MissingTerms('reconcile pending aggregates into an opening ledger before projection')
    if any(p.status.value!='settled' for p in snapshot.payments) or any(t.status.value!='settled' for t in snapshot.transfers):
        raise MissingTerms('in-flight actual transactions need an explicit opening commitment/transit reconciliation')
    floors={f.account_id:f for f in snapshot.liquidity_floors}
    reserves={a.account_id:ZERO for a in snapshot.liquidity_accounts}
    for sf in snapshot.sinking_funds:reserves[sf.account_id]+=sf.reserved_amount
    result=[]
    for account in snapshot.liquidity_accounts:
        if account.account_id not in floors:raise MissingTerms('every cash account needs an explicit floor')
        result.append(CashOpening(account_id=account.account_id,cleared=account.cleared_balance,
            reserved=reserves[account.account_id],floor=floors[account.account_id].minimum_balance,
            primary=account.is_primary,eligible=account.transfer_eligible_to_operational,
            provenance=account.balance_provenance))
    return tuple(result)


def add_business_days(start:datetime,days:int,holidays:tuple[date,...])->datetime:
    if isinstance(days,bool) or not isinstance(days,int) or days<0:raise ValueError('nonnegative integer delay required')
    if start.utcoffset() is None:raise ValueError('timezone-aware start required')
    current=start
    remaining=days
    while remaining:
        current+=timedelta(days=1)
        if current.weekday()<5 and current.date() not in holidays:remaining-=1
    return current


def transfer_plan(policy:TransferTimingPolicy,plan_id:str,amount:Decimal,start:datetime,
                  holidays:tuple[date,...], *, contribution:bool=False)->CashPlan:
    """Explicit forecast: source debits at initiation; destination clears at arrival.

    Holiday calendar is supplied, not obtained from an external service. The
    timestamp's timezone defines its banking calendar before UTC normalization.
    """
    arrival=add_business_days(start,policy.expected_business_days.value,holidays)
    return CashPlan(plan_id=plan_id,kind=CashKind.CONTRIBUTION if contribution else CashKind.TRANSFER,
        amount=amount,source_account_id=policy.source_account_id,destination_account_id=policy.dest_account_id,
        initiated_at=start,debited_at=start,credited_at=arrival,settled_at=arrival,
        provenance=policy.expected_business_days.provenance)


@decimal_context
def project_liquidity(openings:tuple[CashOpening,...],plans:tuple[CashPlan,...],start:datetime,
                      *, horizon_days:int=90,policies:tuple[TransferTimingPolicy,...]=(),
                      initial_transit:Decimal=ZERO,end_at:datetime|None=None)->LiquidityProjection:
    """Event-exact 90-day liquidity projection; amounts are constant between events.

    Future transfers are explicit lifecycle plans. Unscheduled secondary liquidity
    is counted only for a verified zero-business-day route; delayed transfers must
    actually arrive in the plan. No auto-transfer scheduling or income inference.
    """
    if start.utcoffset() is None:raise ValueError('timezone-aware as-of required')
    start=start.astimezone(timezone.utc)
    if isinstance(horizon_days,bool) or not isinstance(horizon_days,int) or horizon_days<0:
        raise ValueError('nonnegative integer horizon required')
    end=start+timedelta(days=horizon_days) if end_at is None else end_at
    if end.utcoffset() is None or end<start:raise ValueError('ordered timezone-aware projection end required')
    end=end.astimezone(timezone.utc)
    from engine.common import decimal_input
    initial_transit=decimal_input(initial_transit)
    if initial_transit<0:raise ValueError('negative opening transit')
    accounts={o.account_id:o for o in openings}
    if len(accounts)!=len(openings) or len([o for o in openings if o.primary])!=1:
        raise ValueError('unique cash accounts and exactly one primary required')
    primary=next(o.account_id for o in openings if o.primary)
    if len({p.plan_id for p in plans})!=len(plans):raise ValueError('plan IDs must be unique')
    routes={(p.source_account_id,p.dest_account_id):p for p in policies}
    if len(routes)!=len(policies):raise ValueError('timing routes must be unique')
    for source,dest in routes:
        if source not in accounts or dest not in accounts:raise ValueError('timing route account missing')
    for plan in plans:
        if any(id_ is not None and id_ not in accounts for id_ in (plan.source_account_id,plan.destination_account_id)):
            raise ValueError('plan references unknown cash account')
    cleared={k:o.cleared for k,o in accounts.items()}
    committed={k:o.committed for k,o in accounts.items()}
    held={k:o.held for k,o in accounts.items()}
    reserved={k:o.reserved for k,o in accounts.items()}
    # Opening is immediately BEFORE start. Derive expected in-flight amounts
    # from the supplied continuing plans; reject an unexplained pending balance.
    expected_committed={k:ZERO for k in accounts}
    expected_held={k:ZERO for k in accounts}
    expected_transit=ZERO
    for p in plans:
        if p.kind in (CashKind.PAYMENT,CashKind.TRANSFER,CashKind.CONTRIBUTION):
            if p.initiated_at<start<=p.debited_at:expected_committed[p.source_account_id]+=p.amount
            if p.kind!=CashKind.PAYMENT:
                if p.debited_at<start<=p.credited_at:expected_transit+=p.amount
                if p.credited_at<start<=p.settled_at:expected_held[p.destination_account_id]+=p.amount
    if committed!=expected_committed or held!=expected_held or initial_transit!=expected_transit:
        raise MissingTerms('opening commitments, holds and transit must reconcile exactly to continuing plans')
    transit=initial_transit
    income=ZERO
    outflows=ZERO
    baseline=sum(cleared.values(),ZERO)+transit
    audit=[]
    points=[]
    severity={CashFlowStatus.HEALTHY:0,CashFlowStatus.BUFFER_BREACH:1,
              CashFlowStatus.OBLIGATION_SHORTFALL:2,CashFlowStatus.NEGATIVE_CASH:3}
    verified={ProvenanceSource.CONTRACTUAL_DISCLOSURE,ProvenanceSource.ACTUAL_STATEMENT,ProvenanceSource.USER_CONFIRMED}
    def point(at,triggers=()):
        rows=[]
        accessible=ZERO
        status=CashFlowStatus.HEALTHY
        for k,o in sorted(accounts.items()):
            unrestricted=cleared[k]-committed[k]-held[k]-reserved[k]
            free=unrestricted-o.floor
            row=CashPosition(account_id=k,cleared=cleared[k],committed=committed[k],held=held[k],
                reserved=reserved[k],unrestricted=unrestricted,above_floor=free)
            rows.append(row)
            route=routes.get((k,primary))
            if k==primary:accessible+=free
            elif o.eligible and route and route.expected_business_days.value==0 and route.expected_business_days.provenance in verified:
                accessible+=max(ZERO,free)
            state=(CashFlowStatus.NEGATIVE_CASH if cleared[k]<0 else
                   CashFlowStatus.OBLIGATION_SHORTFALL if unrestricted<0 else
                   CashFlowStatus.BUFFER_BREACH if free<0 else CashFlowStatus.HEALTHY)
            if severity[state]>severity[status]:status=state
        total=sum(cleared.values(),ZERO)+transit
        if total!=baseline+income-outflows:raise ArithmeticError('cash conservation invariant failed')
        points.append(CashPoint(at=at,positions=tuple(rows),in_transit=transit,aggregate_cash=total,
            accessible_above_floors=accessible,status=status,trigger_ids=tuple(sorted(set(triggers)))))
    events=[]
    for p in plans:
        if p.kind in (CashKind.INCOME,CashKind.EXPENSE,CashKind.RESERVE):
            events.append((p.settled_at,0,p.plan_id,'atomic',p))
        else:
            stages=(('init',p.initiated_at),('debit',p.debited_at),('credit',p.credited_at),('settle',p.settled_at))
            if p.kind==CashKind.PAYMENT:stages=(stages[0],stages[2],stages[1],stages[3])
            for order,(stage,at) in enumerate(stages):events.append((at,order,p.plan_id,stage,p))
    point(start)
    for at,batch in groupby(sorted(events,key=lambda row:row[:3]),key=lambda row:row[0]):
        if at<start:continue
        if at>end:break
        triggers=[]
        for _,_,_,stage,p in batch:
            source,dest=p.source_account_id,p.destination_account_id
            triggers.append(p.plan_id)
            if stage=='atomic':
                if p.kind==CashKind.INCOME:cleared[dest]+=p.amount;income+=p.amount
                elif p.kind==CashKind.EXPENSE:cleared[source]-=p.amount;outflows+=p.amount
                else:reserved[source]+=p.amount
            elif stage=='init':committed[source]+=p.amount
            elif stage=='debit':
                committed[source]-=p.amount
                cleared[source]-=p.amount
                if p.kind==CashKind.PAYMENT:outflows+=p.amount
                else:transit+=p.amount
            elif stage=='credit' and p.kind!=CashKind.PAYMENT:
                transit-=p.amount
                cleared[dest]+=p.amount
                held[dest]+=p.amount
            elif stage=='settle' and p.kind!=CashKind.PAYMENT:
                held[dest]-=p.amount
                if p.kind==CashKind.CONTRIBUTION:reserved[dest]+=p.amount
            audit.append(CashAudit(at=at,plan_id=p.plan_id,stage=stage,kind=p.kind,amount=p.amount,
                source_account_id=source,destination_account_id=dest))
        point(at,triggers)
    if points[-1].at<end:point(end)
    status=max((p.status for p in points),key=lambda s:severity[s])
    minimum=min(p.accessible_above_floors for p in points)
    safe=max(ZERO,minimum) if status==CashFlowStatus.HEALTHY else ZERO
    shortfall=max((max(ZERO,-r.above_floor) for p in points for r in p.positions),default=ZERO)
    sources=tuple(o.provenance for o in openings)+tuple(p.provenance for p in plans)+(ProvenanceSource.ASSUMED_DEFAULT,)
    return LiquidityProjection(start=start,end=end,safe_immediate_payment=safe,status=status,
        first_breach_at=next((p.at for p in points if p.status!=CashFlowStatus.HEALTHY),None),
        peak_shortfall=shortfall,points=tuple(points),audit=tuple(audit),external_income=income,
        external_outflows=outflows,label=projection_label(sources))


class ContributionTriage(StrictModel):
    baseline:LiquidityProjection
    with_contributions_paused:LiquidityProjection
    paused_plan_ids:tuple[str,...]
    peak_shortfall_reduction:Nonnegative


@decimal_context
def contribution_triage(openings,plans,start,*,noncritical_plan_ids:tuple[str,...],policies=())->ContributionTriage:
    allowed={p.plan_id for p in plans if p.kind in (CashKind.CONTRIBUTION,CashKind.RESERVE) and p.initiated_at>=start}
    if not set(noncritical_plan_ids)<=allowed:raise ValueError('only named future contributions/reservations may be paused')
    baseline=project_liquidity(openings,plans,start,policies=policies)
    paused=() if baseline.status==CashFlowStatus.HEALTHY else noncritical_plan_ids
    alternative=project_liquidity(openings,tuple(p for p in plans if p.plan_id not in paused),start,policies=policies)
    return ContributionTriage(baseline=baseline,with_contributions_paused=alternative,paused_plan_ids=paused,
        peak_shortfall_reduction=max(ZERO,baseline.peak_shortfall-alternative.peak_shortfall))


class ReconciledOpening(StrictModel):
    as_of:datetime
    resume_at:datetime
    openings:tuple[CashOpening,...]
    in_transit:Nonnegative
    continuing_plans:tuple[CashPlan,...]
    historical_projection:LiquidityProjection


@decimal_context
def reconcile_at(openings:tuple[CashOpening,...],plans:tuple[CashPlan,...],start:datetime,
                 as_of:datetime,*,policies=(),initial_transit:Decimal=ZERO)->ReconciledOpening:
    """Replay a known journal through as_of, then create a validated continuation.

    Historical event timestamps must be actual/reconciled data supplied by the
    caller. Future timestamps remain forecasts. This does not infer event history
    from ambiguous bank pending aggregates. JSON serialization preserves the
    immutable opening, remaining plans and audit for restart/reproducibility.
    """
    projected=project_liquidity(openings,plans,start,end_at=as_of,policies=policies,initial_transit=initial_transit)
    last=projected.points[-1]
    original={o.account_id:o for o in openings}
    resumed=tuple(CashOpening(account_id=r.account_id,cleared=r.cleared,reserved=r.reserved,
        committed=r.committed,held=r.held,floor=original[r.account_id].floor,
        primary=original[r.account_id].primary,eligible=original[r.account_id].eligible,
        provenance=original[r.account_id].provenance) for r in last.positions)
    return ReconciledOpening(as_of=as_of,resume_at=as_of+timedelta(microseconds=1),openings=resumed,
        in_transit=last.in_transit,continuing_plans=tuple(p for p in plans if p.settled_at>as_of),
        historical_projection=projected)
