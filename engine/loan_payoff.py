"""Bounded simple-interest installment payoff using the existing loan waterfall.

Explicit due dates and payment lifecycles; principal curtailment only. No guessed
rebates, paid-ahead schedules, future fees or loan/card portfolio prioritization.
"""
from datetime import date,datetime,timedelta
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field
from SCHEMA import StrictModel,InstallmentLoan,LoanType,PrepaymentBehavior,ProvenanceSource
from engine.common import ZERO,CENT,Nonnegative,Money,decimal_context,reconstruct,MissingTerms,posting
from engine.loans import accrue_loan,pay_loan
from engine.minimum_forecast import PaymentSlot
from engine.payoff import PaymentFunding,cash_horizon,validate_funding,funding_routes,funding_openings,funding_capacity
from engine.liquidity import CashOpening,CashPlan,CashKind,LiquidityProjection,project_liquidity


class LoanPayoffInputs(StrictModel):
    format: Literal['debt-shredder-loan-payoff']='debt-shredder-loan-payoff'
    version: Literal[1]=1
    start: datetime
    end: datetime
    timezone_name: str
    loan: InstallmentLoan
    due_dates: tuple[date,...]=Field(min_length=1,max_length=121)
    opening: CashOpening
    additional_openings: tuple[CashOpening,...]=Field(default=(),max_length=19)
    payment_sources: tuple[PaymentFunding,...]=Field(default=(),max_length=1)
    cash_plans: tuple[CashPlan,...]=Field(default=(),max_length=2000)
    slots: tuple[PaymentSlot,...]=Field(min_length=1,max_length=120)
    payment_target: Nonnegative


class LoanPayoffPayment(StrictModel):
    slot_id: str
    source_account_id: str
    credited_at: datetime
    initiated_at: datetime
    debited_at: datetime
    settled_at: datetime
    minimum_required: Nonnegative
    minimum_paid: Nonnegative
    total_paid: Nonnegative
    fees_paid: Nonnegative
    interest_paid: Nonnegative
    principal_paid: Nonnegative
    principal_remaining: Nonnegative
    interest_remaining: Nonnegative
    fees_remaining: Nonnegative
    interest_posting_adjustment: Money


class LoanPayoffResult(StrictModel):
    status: Literal['paid_off','horizon_exhausted']
    payoff_date: date|None
    total_paid: Nonnegative
    principal_paid: Nonnegative
    interest_paid: Nonnegative
    fees_paid: Nonnegative
    principal_remaining: Nonnegative
    unposted_interest_remaining: Nonnegative
    fees_remaining: Nonnegative
    interest_posting_adjustment: Money
    missed_due_dates: tuple[date,...]
    all_minimums_met: bool
    payments: tuple[LoanPayoffPayment,...]
    liquidity: LiquidityProjection
    label: str='Estimate: supplied simple-interest note rate and due calendar, principal curtailment, no new fees or rate changes. Not a servicer payoff quote.'


class LoanPaymentDecision(StrictModel):
    slot: PaymentSlot
    payoff_amount: Nonnegative
    minimum_required: Nonnegative


@decimal_context
def plan_loan_payoff(value:LoanPayoffInputs)->LoanPayoffResult:
    return replay_loan_payoff(value,lambda view,plans:min(view.payoff_amount,value.payment_target,
        funding_capacity(value,plans,view.slot)[funding_routes(value,[value.loan.loan_id])[value.loan.loan_id]]))


@decimal_context
def replay_loan_payoff(value:LoanPayoffInputs,choose_payment)->LoanPayoffResult:
    """Replay authoritative loan math with explicit accepted credits.

    Internal portfolio adapter: chooser receives the current quote/minimum and
    prior payment cash plans. The caller owns aggregate budget/cash allocation.
    Credits must be whole cents, nonnegative and no larger than the quote.
    """
    tz=ZoneInfo(value.timezone_name)
    if value.start.utcoffset() is None or value.end.utcoffset() is None or not 0<=(value.end-value.start).total_seconds()<=3660*86400:
        raise ValueError('Supply an aware ordered loan horizon of at most 3660 days')
    start=value.start.astimezone(tz).date();end=value.end.astimezone(tz).date()
    if value.start.astimezone(tz).time()!=datetime.min.time():raise ValueError('Loan opening must be at local midnight')
    loan=value.loan
    if loan.loan_type!=LoanType.SIMPLE_INTEREST or loan.prepayment_behavior.value!=PrepaymentBehavior.PRINCIPAL_ONLY_CURTAILMENT:
        raise MissingTerms('Loan payoff supports simple interest with principal curtailment; paid-ahead and precomputed contracts need their actual schedules')
    if any(amount%CENT for amount in (loan.principal_balance,loan.fees_outstanding,loan.contractual_payment_amount.value,value.payment_target)):
        raise ValueError('Principal, fees, contractual payments and targets must be whole cents')
    if tuple(sorted(set(value.due_dates)))!=value.due_dates or value.due_dates[0]!=loan.next_due_date or value.due_dates[0]<start or value.due_dates[-1]<end:
        raise ValueError('Explicit unique due dates must start at next_due_date, not precede opening, and cover the horizon')
    if len({s.slot_id for s in value.slots})!=len(value.slots) or any(not value.start<=s.initiated_at<=s.settled_at<=value.end for s in value.slots):
        raise ValueError('Unique complete payment lifecycles must lie inside the horizon')
    if any(a.settled_at>b.initiated_at or a.credited_at.astimezone(tz).date()>=b.credited_at.astimezone(tz).date() for a,b in zip(value.slots,value.slots[1:])):
        raise ValueError('Loan payment rounds must have distinct credit days and settle before the next round')
    validate_funding(value,[loan.loan_id]);source=funding_routes(value,[loan.loan_id])[loan.loan_id]
    remaining={d:loan.contractual_payment_amount.value for d in value.due_dates}
    slots={s.credited_at.astimezone(tz).date():s for s in value.slots}
    days=sorted(set(slots)|{d for d in value.due_dates if d<=end})
    current=loan;accrued_through=start;plans=[];rows=[];missed=[]
    payoff=start if loan.principal_balance==loan.accrued_interest==loan.fees_outstanding==0 else None
    for day in days:
        if payoff is not None:break
        slot=slots.get(day)
        if slot is not None:
            accrued=accrue_loan(current,accrued_through,day);accrued_through=day
            current=reconstruct(current,accrued_interest=accrued,balances_provenance=ProvenanceSource.ASSUMED_DEFAULT,balances_as_of_date=day)
            quote=current.principal_balance+current.fees_outstanding+posting(current.accrued_interest,current.rounding_mode.value)
            if quote==0 and current.accrued_interest>0:raise MissingTerms('A sub-cent opening interest balance requires servicer posting confirmation')
            active=[d for i,d in enumerate(value.due_dates) if i==0 or value.due_dates[i-1]<day]
            minimum=min(quote,sum((remaining[d] for d in active),ZERO))
            amount=choose_payment(LoanPaymentDecision(slot=slot,payoff_amount=quote,minimum_required=minimum),tuple(plans))
            if not isinstance(amount,type(ZERO)) or not amount.is_finite() or amount<0 or amount>quote or amount%CENT:
                raise ValueError('Accepted loan credit must be a nonnegative whole-cent Decimal within the payoff quote')
            fees=interest=principal=adjustment=ZERO
            if amount:
                paid=pay_loan(current,amount)
                if paid.unapplied:raise ArithmeticError('Loan payment exceeded the payoff amount')
                fees,interest,principal,adjustment=paid.fees_paid,paid.interest_paid,paid.principal_paid,paid.interest_posting_adjustment
                current=reconstruct(current,principal_balance=paid.principal_remaining,accrued_interest=paid.interest_remaining,fees_outstanding=paid.fees_remaining)
                applied=min(amount,minimum)
                for due in active:
                    take=min(applied,remaining[due]);remaining[due]-=take;applied-=take
                plans.append(CashPlan(plan_id='payoff:loan:'+slot.slot_id,kind=CashKind.PAYMENT,amount=amount,
                    source_account_id=source,initiated_at=slot.initiated_at,credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at))
            rows.append(LoanPayoffPayment(slot_id=slot.slot_id,source_account_id=source,initiated_at=slot.initiated_at,
                credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at,minimum_required=minimum,
                minimum_paid=min(amount,minimum),total_paid=amount,fees_paid=fees,interest_paid=interest,principal_paid=principal,
                principal_remaining=current.principal_balance,interest_remaining=current.accrued_interest,fees_remaining=current.fees_outstanding,
                interest_posting_adjustment=adjustment))
            if current.principal_balance==current.accrued_interest==current.fees_outstanding==0:payoff=day
        if day in remaining and payoff is None and remaining[day]>0:missed.append(day)
    accrued=current.accrued_interest if payoff is not None else accrue_loan(current,accrued_through,end+timedelta(days=1))
    cash=project_liquidity(funding_openings(value),value.cash_plans+tuple(plans),value.start,end_at=cash_horizon(value))
    principal=sum((p.principal_paid for p in rows),ZERO);interest=sum((p.interest_paid for p in rows),ZERO);fees=sum((p.fees_paid for p in rows),ZERO)
    paid=sum((p.total_paid for p in rows),ZERO)
    if paid!=principal+interest+fees or principal+current.principal_balance!=loan.principal_balance or fees+current.fees_outstanding!=loan.fees_outstanding:
        raise ArithmeticError('Loan payment/principal/fee totals do not reconcile')
    return LoanPayoffResult(status='paid_off' if payoff is not None else 'horizon_exhausted',payoff_date=payoff,
        total_paid=paid,principal_paid=principal,interest_paid=interest,fees_paid=fees,principal_remaining=current.principal_balance,
        unposted_interest_remaining=accrued,fees_remaining=current.fees_outstanding,
        interest_posting_adjustment=sum((p.interest_posting_adjustment for p in rows),ZERO),missed_due_dates=tuple(missed),
        all_minimums_met=not missed,payments=tuple(rows),liquidity=cash)
