"""Headless, bounded payoff planning over explicit revolving terms and cash events.

No inferred contracts, income, transfers, billing dates or payoff quotes. Reuses
statement/daily-interest replay and physical cash protection from the engine.
"""
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field
from SCHEMA import StrictModel, SegmentType, GracePeriodState, CompoundingMethod, CashFlowStatus
from engine.common import ZERO, CENT, Nonnegative, decimal_context, MissingTerms
from engine.portfolio import PortfolioDebt
from engine.minimum_forecast import PaymentSlot
from engine.simulation import simulate_revolving, DebtCreditEvent, DebtProjection
from engine.liquidity import CashOpening, CashPlan, CashKind, project_liquidity, LiquidityProjection


class PaymentFunding(StrictModel):
    debt_account_id: str
    cash_account_id: str


class PayoffInputs(StrictModel):
    version: Literal[1] = 1
    start: datetime
    end: datetime
    debts: tuple[PortfolioDebt, ...] = Field(min_length=1, max_length=10)
    opening: CashOpening
    additional_openings: tuple[CashOpening,...]=Field(default=(),max_length=19)
    payment_sources: tuple[PaymentFunding,...]=Field(default=(),max_length=10)
    cash_plans: tuple[CashPlan, ...] = Field(default=(), max_length=2000)
    slots: tuple[PaymentSlot, ...] = Field(min_length=1, max_length=120)
    payment_target: Nonnegative


class ScheduledPayment(StrictModel):
    slot_id: str
    account_id: str
    source_account_id: str|None=None
    initiated_at: datetime
    credited_at: datetime
    debited_at: datetime
    settled_at: datetime
    minimum_required: Nonnegative
    minimum_paid: Nonnegative
    extra_paid: Nonnegative
    total_paid: Nonnegative


class PayoffResult(StrictModel):
    strategy: Literal['highest_interest_first', 'smallest_balance_first']
    primary_cash_account_id: str|None=None
    status: Literal['paid_off', 'horizon_exhausted']
    payoff_date: date | None
    total_paid: Nonnegative
    posted_interest: Nonnegative
    remaining_posted: Nonnegative
    remaining_unposted_interest: Nonnegative
    all_minimums_met: bool
    all_minimum_requests_funded: bool=True
    payments: tuple[ScheduledPayment, ...]
    debts: tuple[DebtProjection, ...]
    liquidity: LiquidityProjection
    transfers: tuple[CashPlan,...]=()
    label: str = 'Estimate using supplied dates, contract terms and cash events; no new borrowing or bank actions'


class PayoffComparison(StrictModel):
    results: tuple[PayoffResult, ...]
    lowest_interest_strategy: str | None
    comparison_note: str


def cash_horizon(value):
    return max(value.end,value.start+timedelta(days=90),*(s.initiated_at+timedelta(days=90) for s in value.slots))


def funding_openings(value):return (value.opening,)+value.additional_openings


def funding_routes(value,account_ids):
    if not value.payment_sources:return {id_:value.opening.account_id for id_ in account_ids}
    routes={r.debt_account_id:r.cash_account_id for r in value.payment_sources}
    if len(routes)!=len(value.payment_sources) or set(routes)!=set(account_ids):
        raise ValueError('Supply exactly one funding route for every debt account')
    if any(id_ not in {o.account_id for o in funding_openings(value)} for id_ in routes.values()):
        raise ValueError('Payment route references an unknown physical cash account')
    return routes


def validate_funding(value,account_ids):
    openings=funding_openings(value)
    if not value.opening.primary or any(o.primary for o in value.additional_openings):
        raise ValueError('The opening funding account must be the sole primary account')
    if len({o.account_id for o in openings})!=len(openings):raise ValueError('Duplicate physical cash account')
    funding_routes(value,account_ids)
    if any(p.kind==CashKind.PAYMENT or p.plan_id.startswith('payoff:') for p in value.cash_plans):
        raise MissingTerms('Supply cash income, bills, reserves and internal transfers, not other debt payments or reserved IDs')
    project_liquidity(openings,value.cash_plans,value.start,end_at=cash_horizon(value))


@decimal_context
def funding_capacity(value,payment_plans,slot):
    cash=project_liquidity(funding_openings(value),value.cash_plans+tuple(payment_plans),value.start,end_at=cash_horizon(value))
    previous=[p for p in cash.points if p.at<=slot.initiated_at][-1]
    window=(previous,)+tuple(p for p in cash.points if p.at>slot.initiated_at)
    return {o.account_id:(max(ZERO,min(next(p.above_floor for p in point.positions if p.account_id==o.account_id) for point in window)).quantize(CENT,rounding=ROUND_DOWN)
        if cash.status==CashFlowStatus.HEALTHY else ZERO) for o in funding_openings(value)}


@decimal_context
def validate_payoff_inputs(value):
    if value.start.utcoffset() is None or value.end.utcoffset() is None or not 0 <= (value.end-value.start).total_seconds() <= 3660*86400:
        raise ValueError('Supply an aware, ordered horizon of at most 3660 days')
    ids=[d.account.account_id for d in value.debts]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate debt account')
    if value.payment_target % CENT:raise ValueError('Payment target must use whole cents')
    if len({s.slot_id for s in value.slots})!=len(value.slots):raise ValueError('Duplicate payment slot')
    if any(not value.start<=s.initiated_at<=s.settled_at<=value.end for s in value.slots):
        raise ValueError('Payment lifecycle must lie within the supplied horizon')
    if any(a.settled_at>b.initiated_at for a,b in zip(value.slots,value.slots[1:])):
        raise ValueError('Payment rounds must settle before the next initiation')
    for debt in value.debts:
        a=debt.account
        if any(c.account_id!=a.account_id for c in debt.cycles):
            raise ValueError('Billing cycle belongs to a different account')
        if value.start.astimezone(ZoneInfo(debt.credit_timezone)).time()!=datetime.min.time():
            raise ValueError('Start must be midnight in each card credit timezone; partial-day openings are unsupported')
        if len(a.segments)!=1 or a.segments[0].segment_type!=SegmentType.STANDARD_PURCHASE or a.current_grace_state!=GracePeriodState.LOST_GRACE or debt.grace_terms or debt.promo_transitions:
            raise MissingTerms('Payoff planner currently requires one ordinary purchase segment per card, lost grace, no promotions')
        if a.segments[0].compounding_method.value!=CompoundingMethod.SIMPLE_DAILY:
            raise MissingTerms('Payoff planner currently requires simple daily interest')
        if any(amount%CENT for amount in (a.total_balance(),debt.initial_minimum.statement_minimum_remaining,a.minimum_payment_floor.value)):
            raise ValueError('Opening balances, minimums and minimum floors must use whole cents')
        days=[s.credited_at.astimezone(ZoneInfo(debt.credit_timezone)).date() for s in value.slots]
        if any(b<=a for a,b in zip(days,days[1:])):
            raise ValueError('Payment rounds must use distinct ordered credit days for every card')
    validate_funding(value,ids)


@decimal_context
def _paid_off_on(debt, projection, start, end):
    """Include residual interest and zero-cent statement rounding in payoff date."""
    posted=debt.account.total_balance()
    accrued=sum((s.accrued_unposted_interest for s in debt.account.segments),ZERO)
    tz=ZoneInfo(debt.credit_timezone)
    closes={c.end_date for c in debt.cycles}
    events={}
    for event in projection.audit:events.setdefault(event.on,[]).append(event)
    day=start.astimezone(tz).date()
    while day<=end.astimezone(tz).date():
        for event in events.get(day,()):
            if event.kind.startswith('payment_'):posted-=event.amount
            elif event.kind=='unposted_interest':accrued+=event.amount
            elif event.kind=='interest_posting':posted+=event.amount
        if day in closes:accrued=ZERO
        if posted==0 and accrued==0:return day
        day+=timedelta(days=1)
    return None


@decimal_context
def plan_payoff(value: PayoffInputs, strategy='highest_interest_first') -> PayoffResult:
    if strategy not in ('highest_interest_first','smallest_balance_first'):
        raise ValueError('Choose highest_interest_first or smallest_balance_first')
    validate_payoff_inputs(value)
    debts=tuple(sorted(value.debts,key=lambda d:d.account.account_id))
    routes=funding_routes(value,[d.account.account_id for d in debts])
    accepted={};events={d.account.account_id:[] for d in debts};plans=[];rows=[]

    def replay(debt, through, capture=None):
        tz=ZoneInfo(debt.credit_timezone)
        def choose(view):
            key=(debt.account.account_id,view.event_id)
            if capture is not None and view.event_id==capture[0]:
                capture[1].append(view)
                return ZERO
            return accepted[key]
        return simulate_revolving(debt.account,value.start.astimezone(tz).date(),through.astimezone(tz).date(),
            debt.cycles,debt.initial_minimum,(),choose_decision=choose,
            credit_events=tuple(events[debt.account.account_id]),credit_timezone=debt.credit_timezone)

    # Full no-payment replay validates all supplied contracts/cycles before choosing anything.
    for debt in debts:replay(debt,value.end)
    for sequence,slot in enumerate(value.slots):
        views={}
        for debt in debts:
            account_id=debt.account.account_id
            events[account_id].append(DebtCreditEvent(event_id=slot.slot_id,credited_at=slot.credited_at,sequence=sequence))
            captured=[];replay(debt,slot.credited_at,(slot.slot_id,captured))
            views[account_id]=captured[0]
        capacity=funding_capacity(value,plans,slot)
        budget=value.payment_target
        balances={k:sum((s.balance for s in v.segments),ZERO) for k,v in views.items()}
        required={k:min(v.effective_minimum,balances[k]) for k,v in views.items()}
        minimum={};extra={k:ZERO for k in views}
        # Minimums come first; account ID breaks shortage ties explicitly and deterministically.
        for k in sorted(views):
            source=routes[k]
            minimum[k]=min(required[k],budget,capacity[source]);budget-=minimum[k];capacity[source]-=minimum[k]
        order=sorted(views,key=lambda k:(-views[k].segments[0].apr.value,k)) if strategy=='highest_interest_first' else sorted(views,key=lambda k:(balances[k],k))
        if all(minimum[k]==required[k] for k in views):
            for k in order:
                source=routes[k]
                extra[k]=min(max(ZERO,balances[k]-minimum[k]),budget,capacity[source]);budget-=extra[k];capacity[source]-=extra[k]
        for k in sorted(views):
            amount=minimum[k]+extra[k];accepted[k,slot.slot_id]=amount
            rows.append(ScheduledPayment(slot_id=slot.slot_id,account_id=k,source_account_id=routes[k],initiated_at=slot.initiated_at,
                credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at,
                minimum_required=required[k],minimum_paid=minimum[k],extra_paid=extra[k],total_paid=amount))
            if amount:plans.append(CashPlan(plan_id='payoff:'+str(sequence)+':'+k,kind=CashKind.PAYMENT,
                amount=amount,source_account_id=routes[k],initiated_at=slot.initiated_at,
                credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at))
    projections=tuple(replay(d,value.end) for d in debts)
    cash=project_liquidity(funding_openings(value),value.cash_plans+tuple(plans),value.start,end_at=cash_horizon(value))
    paid=sum((p.total_paid for p in rows),ZERO)
    if paid!=sum((p.amount for d in projections for p in d.payments),ZERO):
        raise ArithmeticError('Payment schedule and credited debt payments do not reconcile')
    remaining=sum((d.account.total_balance() for d in projections),ZERO)
    accrued=sum((s.accrued_unposted_interest for d in projections for s in d.account.segments),ZERO)
    payoff_dates=tuple(_paid_off_on(d,p,value.start,value.end) for d,p in zip(debts,projections))
    payoff=max(payoff_dates) if all(d is not None for d in payoff_dates) else None
    return PayoffResult(strategy=strategy,primary_cash_account_id=value.opening.account_id,status='paid_off' if payoff is not None else 'horizon_exhausted',
        payoff_date=payoff,total_paid=paid,posted_interest=sum((a.amount for d in projections for a in d.audit if a.kind=='interest_posting'),ZERO),
        remaining_posted=remaining,remaining_unposted_interest=accrued,
        all_minimums_met=not any(d.missed_due_dates for d in projections),
        all_minimum_requests_funded=all(r.minimum_paid==r.minimum_required for r in rows),
        payments=tuple(rows),debts=projections,liquidity=cash,
        transfers=tuple(p for p in value.cash_plans if p.kind in (CashKind.TRANSFER,CashKind.CONTRIBUTION) and value.start<=p.initiated_at<=cash.end))


@decimal_context
def compare_payoff(value: PayoffInputs) -> PayoffComparison:
    results=tuple(plan_payoff(value,strategy) for strategy in ('highest_interest_first','smallest_balance_first'))
    complete=all(r.status=='paid_off' and r.all_minimums_met and r.liquidity.status==CashFlowStatus.HEALTHY for r in results)
    best=min(results,key=lambda r:(r.posted_interest,r.payoff_date,r.strategy)).strategy if complete else None
    return PayoffComparison(results=results,lowest_interest_strategy=best,
        comparison_note='Lowest posted interest among these two fully paid, minimum-compliant plans under the same payment target and cash inputs; not a global optimum.' if complete else 'No winner claimed: at least one plan is unfinished, misses a minimum, or breaches cash protection.')
