"""Bounded one-card minimum-only forecast with caller-supplied payment slots.

Not an optimizer or an actual ledger. No extra payments or issuer dates are inferred.
"""
from datetime import datetime,timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from pydantic import Field,model_validator
from SCHEMA import StrictModel,GracePeriodState,SegmentType,CompoundingMethod,CashFlowStatus
from engine.common import Nonnegative,ZERO,CENT,decimal_context,MissingTerms,reconstruct
from engine.portfolio import PortfolioDebt,PortfolioPaymentRequest,PortfolioPaymentDecision,RequestKind
from engine.liquidity import CashOpening,CashPlan,CashKind,LiquidityProjection,project_liquidity
from engine.simulation import DebtProjection,DebtCreditEvent,simulate_revolving


class MinimumTerms(StrictModel):
    """Required explicit confirmation of the formula used at future closes."""
    floor:Nonnegative
    rate:Nonnegative=Field(le=1)


class PaymentSlot(StrictModel):
    slot_id:str=Field(min_length=1)
    initiated_at:datetime
    credited_at:datetime
    debited_at:datetime
    settled_at:datetime

    @model_validator(mode='after')
    def timing(self):
        dates=(self.initiated_at,self.credited_at,self.debited_at,self.settled_at)
        if any(d.utcoffset() is None for d in dates) or tuple(sorted(dates))!=dates:
            raise ValueError('Explicit aware initiation <= credit <= debit <= settlement required')
        return self


class MinimumForecast(StrictModel):
    requests:tuple[PortfolioPaymentRequest,...]
    decisions:tuple[PortfolioPaymentDecision,...]
    debt:DebtProjection
    liquidity:LiquidityProjection
    label:str='One-card minimum-only estimate; supplied terms and dates, no extra payments'


@decimal_context
def forecast_minimums(debt:PortfolioDebt,opening:CashOpening,cash_plans:tuple[CashPlan,...],
                      slots:tuple[PaymentSlot,...],start:datetime,end:datetime,terms:MinimumTerms)->MinimumForecast:
    horizon=validate_minimum_inputs(debt,cash_plans,slots,start,end,terms)
    account=debt.account
    tz=ZoneInfo(debt.credit_timezone)
    plans=[];requests=[];decisions=[]
    by_id={s.slot_id:s for s in slots}
    def choose(view):
        slot=by_id[view.event_id]
        desired=min(view.effective_minimum,sum((s.balance for s in view.segments),ZERO)).quantize(CENT)
        if not desired:return ZERO
        request=PortfolioPaymentRequest(request_id=slot.slot_id,debt_account_id=account.account_id,
            source_account_id=opening.account_id,amount=desired,kind=RequestKind.MINIMUM,priority=0,
            initiated_at=slot.initiated_at,credited_at=slot.credited_at,debited_at=slot.debited_at,settled_at=slot.settled_at)
        cash=project_liquidity((opening,),cash_plans+tuple(plans),start,end_at=horizon)
        before=[p for p in cash.points if p.at<=slot.initiated_at]
        window=(before[-1],)+tuple(p for p in cash.points if p.at>slot.initiated_at)
        capacity=max(ZERO,min(p.positions[0].above_floor for p in window)) if cash.status==CashFlowStatus.HEALTHY else ZERO
        accepted=min(desired,capacity).quantize(CENT,rounding='ROUND_DOWN')
        requests.append(request)
        decisions.append(PortfolioPaymentDecision(request_id=request.request_id,debt_account_id=account.account_id,
            kind=RequestKind.MINIMUM,requested=desired,accepted=accepted,unmet=desired-accepted,
            reason='fully_funded' if desired==accepted else 'cash_limit'))
        if accepted:plans.append(request.cash_plan(accepted))
        return accepted
    events=tuple(DebtCreditEvent(event_id=s.slot_id,credited_at=s.credited_at,sequence=i) for i,s in enumerate(slots))
    result=simulate_revolving(account,start.astimezone(tz).date(),end.astimezone(tz).date(),debt.cycles,debt.initial_minimum,(),choose_decision=choose,credit_events=events,credit_timezone=debt.credit_timezone)
    cash=project_liquidity((opening,),cash_plans+tuple(plans),start,end_at=horizon)
    if sum((p.amount for p in result.payments),ZERO)!=sum((d.accepted for d in decisions),ZERO):
        raise ArithmeticError('Credited and accepted payments do not reconcile')
    return MinimumForecast(requests=tuple(requests),decisions=tuple(decisions),debt=result,liquidity=cash)


@decimal_context
def validate_minimum_inputs(debt, cash_plans, slots, start, end, terms):
    if start.utcoffset() is None or end.utcoffset() is None or not 0<=(end-start).total_seconds()<=366*86400:
        raise ValueError('An aware, ordered forecast of at most 366 days is required')
    account=debt.account
    if len(account.segments)!=1 or account.segments[0].segment_type!=SegmentType.STANDARD_PURCHASE or account.segments[0].compounding_method.value!=CompoundingMethod.SIMPLE_DAILY or account.current_grace_state!=GracePeriodState.LOST_GRACE or debt.grace_terms or debt.promo_transitions:
        raise MissingTerms('Minimum forecast supports one ordinary simple-daily card with no active grace or promotions')
    if any(v % CENT for v in (terms.floor,account.total_balance(),debt.initial_minimum.statement_minimum_remaining)):
        raise ValueError('Posted balance, minimum and minimum floor must be whole cents')
    if (terms.floor,terms.rate)!=(account.minimum_payment_floor.value,account.minimum_payment_rate.value):
        raise ValueError('Explicit minimum terms must match the sourced account terms')
    if not 1<=len(slots)<=24 or len({s.slot_id for s in slots})!=len(slots):
        raise ValueError('One to 24 uniquely named payment slots required')
    tz=ZoneInfo(debt.credit_timezone)
    if any(not start<=s.initiated_at<=s.credited_at<=end for s in slots):
        raise ValueError('Payment initiation and credit must be within the debt forecast')
    if any(s.settled_at>end+timedelta(days=90) for s in slots):
        raise ValueError('Settlement must be within 90 days after the debt forecast')
    if any(a.settled_at>b.initiated_at or a.credited_at.astimezone(tz).date()>=b.credited_at.astimezone(tz).date() for a,b in zip(slots,slots[1:])):
        raise ValueError('Slots must be ordered on distinct credit days and settle before the next initiation')
    if any(p.kind not in (CashKind.INCOME,CashKind.EXPENSE) or p.plan_id.startswith('portfolio:') for p in cash_plans):
        raise MissingTerms('Supply only ordinary income/bills; no other debt payments, transfers or reserved plan IDs')
    horizon=max(end,start+timedelta(days=90),*(s.initiated_at+timedelta(days=90) for s in slots),*(s.settled_at for s in slots))
    return horizon
