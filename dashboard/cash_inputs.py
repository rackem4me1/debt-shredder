"""Explicit manual schedules expanded by the existing authoritative calendar helper."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field, model_validator
from SCHEMA import StrictModel, IncomeCadence, SemimonthlyShortMonthRule, ProvenanceSource
from engine.common import Positive, decimal_context
from engine.liquidity import CashPlan, CashKind
from engine.schedules import scheduled_dates

CASH_ROWS = 6
CASH_FIELDS = ('kind', 'label', 'amount', 'date', 'cadence', 'until', 'short_month_rule')
CADENCE_LABELS = {'once': 'Once', 'weekly': 'Every week', 'biweekly': 'Every two weeks', 'monthly': 'Every month'}
SHORT_MONTH_LABELS = {'clamp_to_last_day_of_month': 'Use the last day of the month',
                      'roll_to_next_month_first_day': 'Use the first day of the next month'}


class ManualCashEvent(StrictModel):
    kind: Literal['income', 'expense']
    label: str = Field(min_length=1, max_length=80)
    amount: Positive
    date: date
    cadence: Literal['once', 'weekly', 'biweekly', 'monthly'] = 'once'
    until: date | None = None
    short_month_rule: SemimonthlyShortMonthRule | None = None

    @model_validator(mode='after')
    @decimal_context
    def valid_terms(self):
        if not self.label.strip():
            raise ValueError('Income or bill description cannot be blank')
        if self.amount % Decimal('.01'):
            raise ValueError('Income and bills must use whole cents')
        if self.until is not None and (self.cadence == 'once' or self.until < self.date):
            raise ValueError('A stop date is only for repeating entries and cannot precede the first cash date')
        if (self.cadence == 'monthly') != (self.short_month_rule is not None):
            raise ValueError('Monthly entries require short-month handling; leave it blank for other frequencies')
        return self


def cash_horizon(start, end, requests):
    """Mirror the existing portfolio cash horizon; tests compare it to actual output."""
    return max([end.astimezone(timezone.utc), start.astimezone(timezone.utc)+timedelta(days=90)] +
               [r.initiated_at.astimezone(timezone.utc)+timedelta(days=90) for r in requests] +
               [r.settled_at.astimezone(timezone.utc) for r in requests])


def expand_cash_events(events, start, horizon, timezone_name):
    tz = ZoneInfo(timezone_name)
    first, last = start.astimezone(tz).date(), horizon.astimezone(tz).date()
    plans = []
    for i, event in enumerate(events):
        anchor = datetime.combine(event.date, time(), tzinfo=tz)
        if not start <= anchor <= horizon:
            raise ValueError(f'{event.label}: use a first cash date from {first} through {last}; later events require a separate scenario')
        cadence = IncomeCadence.IRREGULAR if event.cadence == 'once' else IncomeCadence(event.cadence)
        occurrences = scheduled_dates(cadence, event.date, first, min(last, event.until or last),
            day_of_month=event.date.day, short_month_rule=event.short_month_rule)
        for key, day in occurrences:
            when = datetime.combine(day, time(), tzinfo=tz)
            if when > horizon:
                continue  # Fall-back DST can place the last local midnight after the UTC horizon.
            id_ = f'cash-{i+1}: {event.label}' if event.cadence == 'once' else f'cash-{i+1}/{key}: {event.label}'
            plans.append(CashPlan(plan_id=id_,kind=CashKind(event.kind),amount=event.amount,
                source_account_id='checking' if event.kind=='expense' else None,
                destination_account_id='checking' if event.kind=='income' else None,
                initiated_at=when,credited_at=when,debited_at=when,settled_at=when,
                provenance=ProvenanceSource.USER_PROVIDED_ESTIMATE))
    return tuple(plans)
