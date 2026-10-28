"""Cards and principal-curtailment loans sharing one cash ledger and round target.

Explicit contracts/calendars only. Reuses revolving replay, loan waterfall and
physical-account cash protection; never combines independently funded plans.
"""
from datetime import date,datetime
from typing import Literal
from pydantic import Field,field_validator
from SCHEMA import StrictModel,InstallmentLoan,CashFlowStatus
from engine.common import ZERO,Nonnegative,decimal_context,reconstruct
from engine.portfolio import PortfolioDebt
from engine.minimum_forecast import PaymentSlot
from engine.payoff import (PaymentFunding,PayoffInputs,ScheduledPayment,validate_payoff_inputs,
    validate_funding,funding_routes,funding_capacity,funding_openings,cash_horizon,_paid_off_on)
from engine.loan_payoff import LoanPayoffInputs,LoanPayoffResult,replay_loan_payoff
from engine.simulation import simulate_revolving,DebtCreditEvent,DebtProjection
from engine.liquidity import CashOpening,CashPlan,CashKind,LiquidityProjection,project_liquidity
from zoneinfo import ZoneInfo


class PayoffLoan(StrictModel):
    loan: InstallmentLoan
    timezone_name: str
    due_dates: tuple[date,...]=Field(min_length=1,max_length=121)

    @field_validator('timezone_name')
    @classmethod
    def valid_zone(cls,value):
        try:ZoneInfo(value)
        except KeyError as exc:raise ValueError('Supply a valid loan timezone') from exc
        return value


class MixedPayoffInputs(StrictModel):
    format: Literal['debt-shredder-mixed-payoff']='debt-shredder-mixed-payoff'
    version: Literal[1]=1
    start: datetime
    end: datetime
    cards: tuple[PortfolioDebt,...]=Field(default=(),max_length=10)
    loans: tuple[PayoffLoan,...]=Field(default=(),max_length=10)
    opening: CashOpening
    additional_openings: tuple[CashOpening,...]=Field(default=(),max_length=19)
    payment_sources: tuple[PaymentFunding,...]=Field(default=(),max_length=10)
    cash_plans: tuple[CashPlan,...]=Field(default=(),max_length=2000)
    slots: tuple[PaymentSlot,...]=Field(min_length=1,max_length=120)
    payment_target: Nonnegative


class MixedLoanResult(StrictModel):
    account_id: str
    projection: LoanPayoffResult


class MixedPayoffResult(StrictModel):
    strategy: Literal['highest_interest_first','smallest_balance_first']
    status: Literal['paid_off','horizon_exhausted']
    payoff_date: date|None
    primary_cash_account_id: str
    total_paid: Nonnegative
    card_posted_interest: Nonnegative
    loan_interest_paid: Nonnegative
    interest_total: Nonnegative
    loan_fees_paid: Nonnegative
    remaining_posted: Nonnegative
    remaining_unposted_interest: Nonnegative
    all_minimums_met: bool
    all_minimum_requests_funded: bool
    payments: tuple[ScheduledPayment,...]
    cards: tuple[DebtProjection,...]
    loans: tuple[MixedLoanResult,...]
    liquidity: LiquidityProjection
    label: str='Estimate: one shared payment target and physical cash ledger; supplied ordinary card terms and simple-interest principal-curtailment loans only. No bank actions or servicer payoff quotes.'


class MixedPayoffComparison(StrictModel):
    results: tuple[MixedPayoffResult,...]
    lowest_interest_strategy: str|None
    comparison_note: str


def loan_inputs(value,item,routes):
    return LoanPayoffInputs(start=value.start,end=value.end,loan=item.loan,timezone_name=item.timezone_name,
        due_dates=item.due_dates,opening=value.opening,additional_openings=value.additional_openings,
        payment_sources=(PaymentFunding(debt_account_id=item.loan.loan_id,cash_account_id=routes[item.loan.loan_id]),),
        cash_plans=value.cash_plans,slots=value.slots,payment_target=value.payment_target)


@decimal_context
def plan_mixed_payoff(value:MixedPayoffInputs,strategy='highest_interest_first')->MixedPayoffResult:
    if strategy not in ('highest_interest_first','smallest_balance_first'):raise ValueError('Unknown payoff strategy')
    ids=[c.account.account_id for c in value.cards]+[l.loan.loan_id for l in value.loans]
    if not 1<=len(ids)<=10 or len(set(ids))!=len(ids):raise ValueError('Supply 1 to 10 debts with unique IDs across cards and loans')
    validate_funding(value,ids);routes=funding_routes(value,ids)
    cards=tuple(sorted(value.cards,key=lambda c:c.account.account_id))
    loans=tuple(sorted(value.loans,key=lambda l:l.loan.loan_id))
    if cards:
        validate_payoff_inputs(PayoffInputs(start=value.start,end=value.end,debts=cards,opening=value.opening,
            additional_openings=value.additional_openings,payment_sources=tuple(PaymentFunding(debt_account_id=c.account.account_id,
                cash_account_id=routes[c.account.account_id]) for c in cards),cash_plans=value.cash_plans,slots=value.slots,payment_target=value.payment_target))
    accepted={};events={c.account.account_id:[] for c in cards};plans=[];rows=[]
    loan_values={l.loan.loan_id:loan_inputs(value,l,routes) for l in loans}

    def card_replay(card,through,capture=None):
        key=card.account.account_id;tz=ZoneInfo(card.credit_timezone)
        def choose(view):
            if capture is not None and view.event_id==capture[0]:capture[1].append(view);return ZERO
            return accepted[key,view.event_id]
        return simulate_revolving(card.account,value.start.astimezone(tz).date(),through.astimezone(tz).date(),
            card.cycles,card.initial_minimum,(),choose_decision=choose,credit_events=tuple(events[key]),credit_timezone=card.credit_timezone)

    def loan_replay(key,capture=None):
        def choose(view,_plans):
            if capture is not None and view.slot.slot_id==capture[0]:capture[1].append(view);return ZERO
            return accepted.get((key,view.slot.slot_id),ZERO)
        return replay_loan_payoff(loan_values[key],choose)

    # Validate the whole supplied horizon before accepting any payment.
    for c in cards:card_replay(c,value.end)
    for l in loans:loan_replay(l.loan.loan_id)
    for sequence,slot in enumerate(value.slots):
        balances={};required={};rates={}
        for card in cards:
            key=card.account.account_id;captured=[]
            events[key].append(DebtCreditEvent(event_id=slot.slot_id,credited_at=slot.credited_at,sequence=sequence))
            card_replay(card,slot.credited_at,(slot.slot_id,captured));view=captured[0]
            balances[key]=sum((s.balance for s in view.segments),ZERO)
            required[key]=min(balances[key],view.effective_minimum);rates[key]=view.segments[0].apr.value
        for loan in loans:
            key=loan.loan.loan_id;captured=[];loan_replay(key,(slot.slot_id,captured))
            balances[key]=captured[0].payoff_amount if captured else ZERO
            required[key]=captured[0].minimum_required if captured else ZERO
            rates[key]=loan.loan.contract_note_rate.value
        capacity=funding_capacity(value,plans,slot);budget=value.payment_target
        minimum={};extra={k:ZERO for k in ids}
        for key in sorted(ids):
            source=routes[key];minimum[key]=min(required[key],budget,capacity[source])
            budget-=minimum[key];capacity[source]-=minimum[key]
        order=sorted(ids,key=lambda k:(-rates[k],k)) if strategy=='highest_interest_first' else sorted(ids,key=lambda k:(balances[k],k))
        if all(minimum[k]==required[k] for k in ids):
            for key in order:
                source=routes[key];extra[key]=min(balances[key]-minimum[key],budget,capacity[source])
                budget-=extra[key];capacity[source]-=extra[key]
        for key in sorted(ids):
            amount=minimum[key]+extra[key];accepted[key,slot.slot_id]=amount
            rows.append(ScheduledPayment(slot_id=slot.slot_id,account_id=key,source_account_id=routes[key],initiated_at=slot.initiated_at,
                credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at,minimum_required=required[key],
                minimum_paid=minimum[key],extra_paid=extra[key],total_paid=amount))
            if amount:plans.append(CashPlan(plan_id='payoff:mixed:'+str(sequence)+':'+key,kind=CashKind.PAYMENT,amount=amount,
                source_account_id=routes[key],initiated_at=slot.initiated_at,credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at))
    card_results=tuple(card_replay(c,value.end) for c in cards)
    cash=project_liquidity(funding_openings(value),value.cash_plans+tuple(plans),value.start,end_at=cash_horizon(value))
    # Loan results expose the SAME shared cash ledger, not independently funded budgets.
    loan_results=tuple(MixedLoanResult(account_id=l.loan.loan_id,projection=reconstruct(loan_replay(l.loan.loan_id),liquidity=cash)) for l in loans)
    paid=sum((p.total_paid for p in rows),ZERO)
    credits=sum((p.amount for c in card_results for p in c.payments),ZERO)+sum((l.projection.total_paid for l in loan_results),ZERO)
    if paid!=credits or paid!=sum((p.amount for p in plans),ZERO):raise ArithmeticError('Shared cash payments and debt credits do not reconcile')
    dates=tuple(_paid_off_on(c,r,value.start,value.end) for c,r in zip(cards,card_results))+tuple(l.projection.payoff_date for l in loan_results)
    payoff=max(dates) if all(d is not None for d in dates) else None
    card_interest=sum((a.amount for c in card_results for a in c.audit if a.kind=='interest_posting'),ZERO)
    loan_interest=sum((l.projection.interest_paid for l in loan_results),ZERO)
    return MixedPayoffResult(strategy=strategy,status='paid_off' if payoff is not None else 'horizon_exhausted',payoff_date=payoff,
        primary_cash_account_id=value.opening.account_id,total_paid=paid,card_posted_interest=card_interest,loan_interest_paid=loan_interest,
        interest_total=card_interest+loan_interest,loan_fees_paid=sum((l.projection.fees_paid for l in loan_results),ZERO),
        remaining_posted=sum((c.account.total_balance() for c in card_results),ZERO)+sum((l.projection.principal_remaining+l.projection.fees_remaining for l in loan_results),ZERO),
        remaining_unposted_interest=sum((s.accrued_unposted_interest for c in card_results for s in c.account.segments),ZERO)+sum((l.projection.unposted_interest_remaining for l in loan_results),ZERO),
        all_minimums_met=not any(c.missed_due_dates for c in card_results) and all(l.projection.all_minimums_met for l in loan_results),
        all_minimum_requests_funded=all(p.minimum_paid==p.minimum_required for p in rows),payments=tuple(rows),cards=card_results,loans=loan_results,liquidity=cash)


@decimal_context
def compare_mixed_payoff(value:MixedPayoffInputs)->MixedPayoffComparison:
    results=tuple(plan_mixed_payoff(value,s) for s in ('highest_interest_first','smallest_balance_first'))
    complete=all(r.status=='paid_off' and r.all_minimums_met and r.liquidity.status==CashFlowStatus.HEALTHY for r in results)
    best=min(results,key=lambda r:(r.interest_total,r.payoff_date,r.strategy)).strategy if complete else None
    return MixedPayoffComparison(results=results,lowest_interest_strategy=best,comparison_note=
        'Lowest interest among these two fully paid, minimum-compliant plans under one shared target and cash ledger; not a global optimum.' if complete else
        'No winner claimed: at least one plan is unfinished, misses a minimum, or breaches cash protection. Loan interest is paid interest; card interest is posted interest; unpaid accrual is reported separately.')
