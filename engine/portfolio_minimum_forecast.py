"""Minimum-only shared-cash forecast; explicit dates and priority, no extras.

Bounded replay deliberately resolves each slot from original debt inputs plus
previous accepted credits. No partial-day checkpoint or future opening-balance
cap is used. Cross-card payment lifecycles may not overlap.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pydantic import Field
from SCHEMA import StrictModel, CashFlowStatus
from engine.common import ZERO, CENT, decimal_context
from engine.minimum_forecast import MinimumTerms, PaymentSlot, validate_minimum_inputs
from engine.portfolio import PortfolioDebt, PortfolioPaymentRequest, PortfolioPaymentDecision, RequestKind
from engine.liquidity import CashOpening, CashPlan, LiquidityProjection, project_liquidity
from engine.simulation import DebtProjection, DebtCreditEvent, simulate_revolving


class CardMinimumSchedule(StrictModel):
    debt: PortfolioDebt
    terms: MinimumTerms
    slots: tuple[PaymentSlot, ...]
    priority: int = Field(ge=0)


class PortfolioMinimumForecast(StrictModel):
    requests: tuple[PortfolioPaymentRequest, ...]
    decisions: tuple[PortfolioPaymentDecision, ...]
    debts: tuple[DebtProjection, ...]
    liquidity: LiquidityProjection
    label: str = 'Minimum-only estimate; explicit dates and priorities, no extra payments'


@decimal_context
def forecast_portfolio_minimums(schedules: tuple[CardMinimumSchedule, ...], opening: CashOpening,
                               cash_plans: tuple[CashPlan, ...], start: datetime,
                               end: datetime) -> PortfolioMinimumForecast:
    if not 1 <= len(schedules) <= 20:
        raise ValueError('One to 20 card schedules required')
    ids = [s.debt.account.account_id for s in schedules]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate debt account')
    horizon = max(validate_minimum_inputs(s.debt, cash_plans, s.slots, start, end, s.terms)
                  for s in schedules)
    ordered = sorted(((s, slot) for s in schedules for slot in s.slots),
                     key=lambda pair: (pair[1].initiated_at.astimezone(timezone.utc), pair[0].priority))
    keys = [(slot.initiated_at.astimezone(timezone.utc), s.priority) for s, slot in ordered]
    if len(set(keys)) != len(keys):
        raise ValueError('Simultaneous slots require distinct explicit priorities')
    if len({slot.slot_id for _, slot in ordered}) != len(ordered):
        raise ValueError('Slot IDs must be unique across cards')
    if any(a.settled_at > b.initiated_at for (_, a), (_, b) in zip(ordered, ordered[1:])):
        raise ValueError('Cross-card slots must settle before the next initiation')
    # Validate the physical cash ledger even when all generated minimums are zero.
    project_liquidity((opening,), cash_plans, start, end_at=horizon)
    plans = []
    requests = []
    decisions = []
    events = {id_: [] for id_ in ids}
    accepted = {}

    def replay(schedule, through, choose):
        debt = schedule.debt
        tz = ZoneInfo(debt.credit_timezone)
        return simulate_revolving(debt.account, start.astimezone(tz).date(),
                                  through.astimezone(tz).date(), debt.cycles,
                                  debt.initial_minimum, (), choose_decision=choose,
                                  credit_events=tuple(events[debt.account.account_id]),
                                  credit_timezone=debt.credit_timezone)

    for sequence, (schedule, slot) in enumerate(ordered):
        account_id = schedule.debt.account.account_id
        events[account_id].append(DebtCreditEvent(event_id=slot.slot_id,
                                                credited_at=slot.credited_at, sequence=sequence))

        def choose(view):
            if view.event_id != slot.slot_id:
                return accepted[view.event_id]
            desired = min(view.effective_minimum, sum((s.balance for s in view.segments), ZERO)).quantize(CENT)
            accepted[slot.slot_id] = ZERO
            if not desired:
                return ZERO
            cash = project_liquidity((opening,), cash_plans + tuple(plans), start, end_at=horizon)
            previous = [p for p in cash.points if p.at <= slot.initiated_at][-1]
            window = (previous,) + tuple(p for p in cash.points if p.at > slot.initiated_at)
            capacity = max(ZERO, min(p.positions[0].above_floor for p in window)) if cash.status == CashFlowStatus.HEALTHY else ZERO
            amount = min(desired, capacity).quantize(CENT, rounding='ROUND_DOWN')
            request = PortfolioPaymentRequest(request_id=slot.slot_id, debt_account_id=account_id,
                source_account_id=opening.account_id, amount=desired, kind=RequestKind.MINIMUM,
                priority=schedule.priority, initiated_at=slot.initiated_at, credited_at=slot.credited_at,
                debited_at=slot.debited_at, settled_at=slot.settled_at)
            requests.append(request)
            decisions.append(PortfolioPaymentDecision(request_id=slot.slot_id, debt_account_id=account_id,
                kind=RequestKind.MINIMUM, requested=desired, accepted=amount, unmet=desired-amount,
                reason='fully_funded' if amount == desired else 'cash_limit'))
            accepted[slot.slot_id] = amount
            if amount:
                plans.append(request.cash_plan(amount))
            return amount

        replay(schedule, slot.credited_at, choose)
    debts = tuple(replay(s, end, lambda view: accepted[view.event_id]) for s in schedules)
    cash = project_liquidity((opening,), cash_plans + tuple(plans), start, end_at=horizon)
    if sum((p.amount for d in debts for p in d.payments), ZERO) != sum((d.accepted for d in decisions), ZERO):
        raise ArithmeticError('Portfolio credited and accepted payments do not reconcile')
    return PortfolioMinimumForecast(requests=tuple(requests), decisions=tuple(decisions), debts=debts, liquidity=cash)
