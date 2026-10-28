"""Bounded manual adapter; no new financial calculation rules."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import Field, model_validator
from SCHEMA import (StrictModel, Sourced, ProvenanceSource, BalanceSegment, SegmentType,
    CompoundingMethod, DayCountConvention, RevolvingAccount, AllocationRule,
    AllocationRuleType, GracePeriodState, BillingCycle, MinimumPaymentSnapshot, assumed_default)
from engine.common import Nonnegative, decimal_context
from engine.liquidity import CashOpening
from engine.portfolio import PortfolioDebt, PortfolioPaymentRequest, RequestKind
from dashboard.scenarios import Scenario

from dashboard.cash_inputs import CASH_ROWS, CASH_FIELDS, ManualCashEvent, cash_horizon, expand_cash_events


class AdditionalCard(StrictModel):
    card_name: str = Field(default="", max_length=60)
    balance: Nonnegative
    unposted_interest: Nonnegative
    apr_percent: Nonnegative
    day_count: Literal['actual_365_fixed', 'actual_366', 'actual_actual']
    previous_start: date
    previous_close: date
    minimum_due: date
    next_close: date
    next_due: date
    minimum_original: Nonnegative
    minimum_remaining: Nonnegative
    payment_amount: Nonnegative
    payment_kind: Literal['minimum', 'extra']
    initiated: date
    credited: date
    debited: date
    settled: date


CARD_FIELDS = tuple(AdditionalCard.model_fields)
MAX_CARDS = 3


class ManualScenario(StrictModel):
    card_name: str = Field(default="", max_length=60)
    name: str = Field(min_length=1, max_length=120)
    cash: Nonnegative
    floor: Nonnegative
    reserved: Nonnegative
    balance: Nonnegative
    unposted_interest: Nonnegative
    apr_percent: Nonnegative
    day_count: Literal['actual_365_fixed', 'actual_366', 'actual_actual']
    start: date
    end: date
    previous_start: date
    previous_close: date
    minimum_due: date
    next_close: date
    next_due: date
    minimum_original: Nonnegative
    minimum_remaining: Nonnegative
    payment_amount: Nonnegative
    payment_kind: Literal['minimum', 'extra']
    initiated: date
    credited: date
    debited: date
    settled: date
    timezone: str = Field(min_length=1, max_length=80)
    scope: Literal['confirmed']
    additional_cards: tuple[AdditionalCard, ...] = Field(default=(), max_length=MAX_CARDS-1)
    cash_events: tuple[ManualCashEvent, ...] = Field(default=(), max_length=CASH_ROWS)

    @model_validator(mode='before')
    @classmethod
    def form_rows(cls, values):
        if not isinstance(values, dict):
            return values
        values = dict(values)
        card_keys = [f'card_{i}_{field}' for i in range(2,MAX_CARDS+1) for field in CARD_FIELDS]
        if any(key in values for key in card_keys):
            if 'additional_cards' in values:
                raise ValueError('Supply additional cards in one format only')
            cards = []
            blank_seen = False
            for i in range(2,MAX_CARDS+1):
                row = {field:values.pop(f'card_{i}_{field}', '') for field in CARD_FIELDS}
                if any(value != '' for value in row.values()):
                    if blank_seen:
                        raise ValueError('Fill Card 2 before Card 3; do not leave a gap')
                    if any(value == '' for key,value in row.items() if key != 'card_name'):
                        raise ValueError(f'Card {i}: complete all card and payment fields, or clear the entire card')
                    cards.append(row)
                else:
                    blank_seen = True
            values['additional_cards'] = tuple(cards)
        keys = [f'cash_{i}_{field}' for i in range(CASH_ROWS) for field in CASH_FIELDS]
        if any(key in values for key in keys):
            if 'cash_events' in values:
                raise ValueError('Supply income and bills in one format only')
            events = []
            for i in range(CASH_ROWS):
                row = {field: values.pop(f'cash_{i}_{field}', '') for field in CASH_FIELDS}
                row['cadence'] = row['cadence'] or 'once'
                row['until'] = row['until'] or None
                row['short_month_rule'] = row['short_month_rule'] or None
                active = any(row[field] != '' for field in ('kind', 'label', 'amount', 'date'))
                active = active or row['cadence'] != 'once' or row['until'] is not None or row['short_month_rule'] is not None
                if active:
                    if any(row[field] == '' for field in ('kind', 'label', 'amount', 'date')):
                        raise ValueError(f'Income or bill row {i+1}: complete all four fields or leave the entire row blank')
                    events.append(row)
            values['cash_events'] = tuple(events)
        return values

    @model_validator(mode='after')
    @decimal_context
    def supported_window(self):
        if not self.previous_start < self.previous_close < self.start <= self.end < self.next_close < self.next_due:
            raise ValueError('Use an ordered window after the previous statement close and before the next close; next due must follow next close')
        if not self.previous_close < self.minimum_due < self.next_due:
            raise ValueError('Current minimum due must follow the previous close and precede the next due')
        if self.minimum_due < self.start:
            raise ValueError('A minimum already overdue at the opening needs separate reconciliation; begin on or before its due date')
        if self.minimum_remaining > self.minimum_original or self.minimum_remaining > self.balance:
            raise ValueError('Remaining minimum must not exceed the original minimum or opening posted balance')
        if not self.start <= self.initiated <= self.credited <= self.end:
            raise ValueError('Payment initiation and credit must be within the scenario window, in order')
        if not self.credited <= self.debited <= self.settled <= self.end + timedelta(days=90):
            raise ValueError('Bank debit must follow credit; settlement must follow debit and be within 90 days of the window end')
        if (self.end - self.start).days > 62:
            raise ValueError('Manual scenarios support at most 62 days')
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError('Choose a valid time zone, such as America/Chicago') from exc
        for value in (self.cash, self.floor, self.reserved, self.balance, self.minimum_original,
                      self.minimum_remaining, self.payment_amount):
            if value % Decimal('.01'):
                raise ValueError('Cash, posted balances, minimums and payments must use whole cents')
        return self

    @decimal_context
    def scenario(self):
        self = ManualScenario.model_validate(self.model_dump())
        provenance = ProvenanceSource.USER_PROVIDED_ESTIMATE
        def sourced(value):
            return Sourced[type(value)](value=value, provenance=provenance)
        tz = ZoneInfo(self.timezone)
        def at(day):
            return datetime.combine(day, time(), tzinfo=tz)
        segment = BalanceSegment(account_id='card', segment_id='purchase',
            segment_type=SegmentType.STANDARD_PURCHASE, balance=self.balance,
            balance_provenance=provenance, balance_as_of_date=self.start,
            accrued_unposted_interest=self.unposted_interest,
            accrued_interest_provenance=provenance,
            accrued_interest_as_of_date=self.start - timedelta(days=1),
            apr=sourced(self.apr_percent / Decimal(100)),
            compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
            day_count_convention=sourced(DayCountConvention(self.day_count)))
        account = RevolvingAccount(account_id='card', issuer='Manually entered', segments=(segment,),
            allocation_rule=AllocationRule(account_id='card',
                minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
                excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT)),
            current_grace_state=GracePeriodState.LOST_GRACE,
            statement_close_day=self.next_close.day, payment_due_day=self.minimum_due.day)
        cycles = (BillingCycle(account_id='card', cycle_id='previous', start_date=self.previous_start,
                    end_date=self.previous_close, statement_date=self.previous_close, due_date=self.minimum_due),
                  BillingCycle(account_id='card', cycle_id='current', start_date=self.previous_close + timedelta(days=1),
                    end_date=self.next_close, statement_date=self.next_close, due_date=self.next_due))
        debt = PortfolioDebt(account=account, cycles=cycles, credit_timezone=self.timezone,
            initial_minimum=MinimumPaymentSnapshot(account_id='card', billing_cycle_id='previous',
                statement_minimum_original=self.minimum_original, statement_minimum_remaining=self.minimum_remaining,
                provenance=provenance, as_of_date=self.start))
        requests = () if not self.payment_amount else (PortfolioPaymentRequest(request_id='payment',
            debt_account_id='card', source_account_id='checking', amount=self.payment_amount,
            kind=RequestKind(self.payment_kind), priority=0, initiated_at=at(self.initiated),
            credited_at=at(self.credited), debited_at=at(self.debited), settled_at=at(self.settled)),)
        debts = [debt]
        all_requests = list(requests)
        if self.additional_cards:
            from engine.common import reconstruct
            for i, card in enumerate(self.additional_cards, 2):
                child_values = self.model_dump() | card.model_dump() | {'additional_cards':(), 'cash_events':()}
                try:
                    child = ManualScenario.model_validate(child_values).scenario()
                except ValueError as exc:
                    raise ValueError(f'Card {i}: {exc}') from exc
                account_id = f'card-{i}'
                child_debt = child.debts[0].model_dump(mode='json')
                def assign_account(value):
                    if isinstance(value,dict):
                        return {key:account_id if key=='account_id' else assign_account(item) for key,item in value.items()}
                    if isinstance(value,list):return [assign_account(item) for item in value]
                    return value
                debts.append(PortfolioDebt.model_validate(assign_account(child_debt)))
                all_requests.extend(reconstruct(r,request_id=f'payment-{i}',debt_account_id=account_id,
                    priority=(i-1)*2) for r in child.requests)
            # Reserve only the minimum portion before extras; a large request on
            # Card 1 must not take cash needed for Card 2's requested minimum.
            split = []
            by_id = {d.account.account_id:d for d in debts}
            for request in all_requests:
                minimum = by_id[request.debt_account_id].initial_minimum.statement_minimum_remaining
                if request.kind == RequestKind.MINIMUM:
                    covered = min(request.amount, minimum)
                    if covered:
                        split.append(reconstruct(request,amount=covered))
                    if request.amount > covered:
                        split.append(reconstruct(request,request_id=request.request_id+'-excess',
                            amount=request.amount-covered,kind=RequestKind.EXTRA,priority=request.priority+1))
                else:
                    split.append(request)
            all_requests = split
        requests = tuple(all_requests)
        horizon = cash_horizon(at(self.start), at(self.end), requests)
        cash_plans = expand_cash_events(self.cash_events, at(self.start), horizon, self.timezone)
        # Preserve recurring intent separately from its concrete, verified cash events.
        schedules = self.cash_events if any(e.cadence != 'once' for e in self.cash_events) else ()
        names = (self.card_name,) + tuple(card.card_name for card in self.additional_cards)
        result = Scenario(card_names=names if any(names) else (), name=self.name, origin='manual', start=at(self.start), end=at(self.end), debts=tuple(debts),
            openings=(CashOpening(account_id='checking', cleared=self.cash, floor=self.floor,
                reserved=self.reserved, primary=True, provenance=provenance),), cash_plans=cash_plans, requests=requests, manual_cash_schedules=schedules)
        result.project()
        return result


@decimal_context
def editable_inputs(scenario: Scenario) -> dict:
    """Recover supported form inputs only if a complete round trip is lossless."""
    try:
        if not 1 <= len(scenario.debts) <= MAX_CARDS or len(scenario.openings) != 1:
            raise ValueError()
        debt = scenario.debts[0]
        segment, = debt.account.segments
        previous, current = debt.cycles
        cash, = scenario.openings
        tz = ZoneInfo(debt.credit_timezone)
        start = scenario.start.astimezone(tz).date()
        def request_for(account_id):
            records = [r for r in scenario.requests if r.debt_account_id == account_id]
            if not records:return None
            from engine.common import reconstruct
            first = records[0]
            return reconstruct(first, amount=sum((r.amount for r in records),Decimal(0)),
                kind=RequestKind.MINIMUM if any(r.request_id.endswith('-excess') for r in records) else first.kind)
        request = request_for(debt.account.account_id)
        values = dict(card_name=scenario.card_names[0] if scenario.card_names else '', name=scenario.name, cash=cash.cleared, floor=cash.floor, reserved=cash.reserved,
            balance=segment.balance, unposted_interest=segment.accrued_unposted_interest,
            apr_percent=segment.apr.value * Decimal(100), day_count=segment.day_count_convention.value.value,
            start=start, end=scenario.end.astimezone(tz).date(), previous_start=previous.start_date,
            previous_close=previous.end_date, minimum_due=previous.due_date,
            next_close=current.end_date, next_due=current.due_date,
            minimum_original=debt.initial_minimum.statement_minimum_original,
            minimum_remaining=debt.initial_minimum.statement_minimum_remaining,
            payment_amount=request.amount if request else Decimal(0),
            payment_kind=request.kind.value if request else 'minimum', timezone=debt.credit_timezone, scope='confirmed')
        for field, source in [('initiated','initiated_at'),('credited','credited_at'),('debited','debited_at'),('settled','settled_at')]:
            values[field] = getattr(request,source).astimezone(tz).date() if request else start
        extra = []
        for child_index, child in enumerate(scenario.debts[1:],1):
            child_segment, = child.account.segments
            child_previous, child_current = child.cycles
            r = request_for(child.account.account_id)
            row = dict(card_name=scenario.card_names[child_index] if scenario.card_names else '',balance=child_segment.balance,unposted_interest=child_segment.accrued_unposted_interest,
                apr_percent=child_segment.apr.value*Decimal(100),day_count=child_segment.day_count_convention.value.value,
                previous_start=child_previous.start_date,previous_close=child_previous.end_date,
                minimum_due=child_previous.due_date,next_close=child_current.end_date,next_due=child_current.due_date,
                minimum_original=child.initial_minimum.statement_minimum_original,
                minimum_remaining=child.initial_minimum.statement_minimum_remaining,
                payment_amount=r.amount if r else Decimal(0),payment_kind=r.kind.value if r else 'minimum')
            for field,source in [('initiated','initiated_at'),('credited','credited_at'),('debited','debited_at'),('settled','settled_at')]:
                row[field]=getattr(r,source).astimezone(tz).date() if r else start
            extra.append(row)
        values['additional_cards']=tuple(extra)
        values['cash_events'] = scenario.manual_cash_schedules or tuple(dict(kind=plan.kind.value, label=plan.plan_id.split(': ', 1)[1],
            amount=plan.amount, date=plan.initiated_at.astimezone(tz).date()) for plan in scenario.cash_plans)
        model = ManualScenario.model_validate(values)
        from engine.common import reconstruct
        if reconstruct(model.scenario(),origin=scenario.origin) != scenario:
            raise ValueError()
        result = model.model_dump(mode='json')
        for i, card in enumerate(result.pop('additional_cards'),2):
            for field,value in card.items():result[f'card_{i}_{field}']=value
        for i, event in enumerate(result.pop('cash_events')):
            for field, value in event.items():
                result[f'cash_{i}_{field}'] = value if value is not None else ''
        return result
    except (ValueError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('This scenario contains inputs the simple editor cannot preserve. Its saved report remains available.') from exc
