import calendar
from datetime import date, timedelta
from decimal import Decimal
from SCHEMA import (DayCountConvention, CompoundingMethod, DeferredInterestCalculationMethod,
                    ProvenanceSource, StrictModel)
from engine.common import (ZERO, Nonnegative, decimal_context, decimal_input, MissingTerms,
                           UnsupportedTerms, projection_label)


def basis_days(day: date, convention: DayCountConvention) -> int:
    convention = DayCountConvention(convention)
    if convention == DayCountConvention.ACTUAL_365:
        return 365
    if convention == DayCountConvention.ACTUAL_366:
        return 366
    if convention == DayCountConvention.ACTUAL_ACTUAL:
        return 366 if calendar.isleap(day.year) else 365
    raise UnsupportedTerms('30/360 requires contractual period endpoints; daily accrual is not actual/360')


@decimal_context
def daily_rate(rate: Decimal, day: date, convention: DayCountConvention) -> Decimal:
    rate = decimal_input(rate)
    if rate < 0:
        raise ValueError('rate must be nonnegative')
    return rate / Decimal(basis_days(day, convention))


@decimal_context
def accrue_constant(principal: Decimal, rate: Decimal, start: date, end: date,
                    convention: DayCountConvention, method: CompoundingMethod,
                    opening_accrual: Decimal = ZERO) -> Decimal:
    """Return cumulative unposted interest for [start, end), with no quantization.

    SIMPLE_DAILY does not compound accrued interest. DAILY_COMPOUNDING does.
    Monthly capitalization needs explicit posting dates and is rejected here.
    """
    principal, opening_accrual = decimal_input(principal), decimal_input(opening_accrual)
    if principal < 0 or opening_accrual < 0 or end < start:
        raise ValueError('nonnegative principal/accrual and ordered dates required')
    method = CompoundingMethod(method)
    if method == CompoundingMethod.MONTHLY_COMPOUNDING:
        raise MissingTerms('monthly compounding needs explicit capitalization events')
    accrued = opening_accrual
    day = start
    while day < end:
        base = principal + accrued if method == CompoundingMethod.DAILY_COMPOUNDING else principal
        accrued += base * daily_rate(rate, day, convention)
        day += timedelta(days=1)
    return accrued


class DailyBalance(StrictModel):
    day: date
    balance: Nonnegative

class InterestProjection(StrictModel):
    amount: Nonnegative
    label: str
    sources: tuple[ProvenanceSource, ...]


@decimal_context
def deferred_exposure(history: tuple[DailyBalance, ...], rate: Decimal,
                      convention: DayCountConvention, method: DeferredInterestCalculationMethod,
                      sources: tuple[ProvenanceSource, ...], opening: Decimal = ZERO) -> InterestProjection:
    """Unposted liability on supplied consecutive daily balances, not a payoff plan.

    History starts after any period already included in opening. Caller supplies
    every balance day through the contract horizon; no 90-day truncation occurs.
    """
    opening = decimal_input(opening)
    if opening < 0:
        raise ValueError('opening exposure must be nonnegative')
    for previous, current in zip(history, history[1:]):
        if current.day != previous.day + timedelta(days=1):
            raise ValueError('history must contain consecutive, unique daily balances')
    method = DeferredInterestCalculationMethod(method)
    if method == DeferredInterestCalculationMethod.RETROACTIVE_PURCHASE_SUM:
        raise MissingTerms('retroactive purchase sum requires dated purchase-level history and issuer rules')
    accrued = opening
    for row in history:
        base = row.balance + accrued if method == DeferredInterestCalculationMethod.DAILY_COMPOUNDING else row.balance
        accrued += base * daily_rate(rate, row.day, convention)
    return InterestProjection(amount=accrued, label=projection_label(sources), sources=sources)


@decimal_context
def contingent_grace_interest(history: tuple[DailyBalance, ...], rate: Decimal,
                              convention: DayCountConvention,
                              sources: tuple[ProvenanceSource, ...]) -> InterestProjection:
    """The v2.4 contingent purchase delta; primary grace track remains zero."""
    return deferred_exposure(history, rate, convention,
        DeferredInterestCalculationMethod.AVERAGE_DAILY_BALANCE_SIMPLE, sources)
