"""Explicit promo lifecycle assessment without rewriting frozen schema records.

Daily balances are post-credit balances. The supplied cutoff is end-of-day;
reversion starts the following day. Callers must map contract timestamps to this
convention explicitly. This module does not silently inject a fee into replay.
"""
from datetime import date, timedelta
from enum import Enum
from pydantic import model_validator
from SCHEMA import (StrictModel, BalanceSegment, SegmentType, Sourced,
    CompoundingMethod, ProvenanceSource, RoundingMode)
from engine.common import Nonnegative, ZERO, decimal_context, posting, MissingTerms, projection_label
from engine.interest import DailyBalance, deferred_exposure


class PromoExitReason(str, Enum):
    EXPIRATION='expiration'
    DISQUALIFICATION='disqualification'


class PromoExitTerms(StrictModel):
    cutoff: date
    reason: PromoExitReason = PromoExitReason.EXPIRATION
    # Explicit recognition/posting convention supplied by the caller.
    rounding_mode: Sourced[RoundingMode]
    cutoff_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    # Disqualification may use different terms from ordinary expiration.
    disqualified_apr: Sourced[Nonnegative] | None = None
    disqualified_compounding: Sourced[CompoundingMethod] | None = None
    assess_deferred_on_disqualification: Sourced[bool] | None = None

    @model_validator(mode='after')
    def explicit_disqualification(self):
        fields=(self.disqualified_apr,self.disqualified_compounding,self.assess_deferred_on_disqualification)
        if self.reason==PromoExitReason.DISQUALIFICATION and any(v is None for v in fields):
            raise ValueError('disqualification requires explicit replacement rate, compounding and assessment rule')
        if self.reason==PromoExitReason.EXPIRATION and any(v is not None for v in fields):
            raise ValueError('disqualification terms require a disqualification event')
        return self


class PromoExitResult(StrictModel):
    account_id: str
    segment_id: str
    reason: PromoExitReason
    cutoff: date
    reversion_starts: date
    remaining_principal: Nonnegative
    deferred_exposure: Nonnegative
    assessed_deferred_interest: Nonnegative
    waived_deferred_interest: Nonnegative
    unassessed_deferred_exposure: Nonnegative
    balance_after_assessment: Nonnegative
    replacement_apr: Sourced[Nonnegative]
    replacement_compounding: Sourced[CompoundingMethod]
    paid_by_cutoff: bool
    label: str


def validate_promo_exit_terms(segment: BalanceSegment, terms: PromoExitTerms) -> None:
    if segment.promo_expiration_date is None or segment.post_promo_apr is None or segment.post_promo_compounding_method is None:
        raise MissingTerms('explicit promotional expiration and replacement terms required')
    if segment.is_disqualified or segment.disqualification_events:
        raise MissingTerms('already disqualified opening requires historical exit reconciliation')
    if terms.reason==PromoExitReason.EXPIRATION and terms.cutoff!=segment.promo_expiration_date:
        raise ValueError('expiration cutoff must match segment expiration date')
    if terms.reason==PromoExitReason.DISQUALIFICATION and terms.cutoff>segment.promo_expiration_date:
        raise ValueError('disqualification cannot follow expiration')


@decimal_context
def assess_promo_exit(segment:BalanceSegment, history:tuple[DailyBalance,...],
                      terms:PromoExitTerms, *, history_provenance:ProvenanceSource)->PromoExitResult:
    """Assess an explicit end-of-day exit from complete supplied balance history.

    Deferred opening exposure must be dated immediately before history. History
    must be consecutive through cutoff and starts from a reconciled opening.
    Its first balance may differ from segment.balance after a morning credit.
    Caller owns purchase/payment reconciliation; this function calculates only
    the exit, not a payment recommendation or subsequent interest accrual.
    """
    validate_promo_exit_terms(segment,terms)
    if not history or history[-1].day!=terms.cutoff:
        raise MissingTerms('complete daily balance history through the cutoff is required')
    if any(b.day!=a.day+timedelta(days=1) for a,b in zip(history,history[1:])):
        raise ValueError('balance history must be consecutive, unique and ordered')
    remaining=history[-1].balance
    sources=[history_provenance,terms.cutoff_provenance,terms.rounding_mode.provenance]
    exposure=ZERO
    assess=False
    if segment.segment_type==SegmentType.PROMOTIONAL_DEFERRED_INTEREST:
        if segment.deferred_interest_as_of_date!=history[0].day-timedelta(days=1):
            raise MissingTerms('deferred opening exposure must be dated immediately before daily history')
        sources.extend((segment.deferred_interest_provenance,segment.deferred_interest_apr.provenance,
            segment.deferred_interest_calculation_method.provenance,segment.day_count_convention.provenance))
        exposure=deferred_exposure(history,segment.deferred_interest_apr.value,
            segment.day_count_convention.value,segment.deferred_interest_calculation_method.value,
            tuple(sources),opening=segment.deferred_interest_to_date).amount
        assess=remaining>0 if terms.reason==PromoExitReason.EXPIRATION else terms.assess_deferred_on_disqualification.value
    if terms.reason==PromoExitReason.DISQUALIFICATION:
        rate,method=terms.disqualified_apr,terms.disqualified_compounding
        sources.append(terms.assess_deferred_on_disqualification.provenance)
    else:
        rate,method=segment.post_promo_apr,segment.post_promo_compounding_method
    sources.extend((rate.provenance,method.provenance))
    assessed=posting(exposure,terms.rounding_mode.value) if assess else ZERO
    return PromoExitResult(account_id=segment.account_id,segment_id=segment.segment_id,reason=terms.reason,
        cutoff=terms.cutoff,reversion_starts=terms.cutoff+timedelta(days=1),remaining_principal=remaining,
        deferred_exposure=exposure,assessed_deferred_interest=assessed,
        waived_deferred_interest=exposure if not assess and terms.reason==PromoExitReason.EXPIRATION else ZERO,
        unassessed_deferred_exposure=exposure if not assess and terms.reason==PromoExitReason.DISQUALIFICATION else ZERO,
        balance_after_assessment=remaining+assessed,
        replacement_apr=rate,replacement_compounding=method,paid_by_cutoff=remaining==0,
        label=projection_label(tuple(sources)))


class PromoTransition(StrictModel):
    """Supplied event and post-exit grace eligibility; no inferred penalty trigger."""
    segment_id: str
    terms: PromoExitTerms
    post_exit_grace_eligible: Sourced[bool]


class SegmentDailyHistory(StrictModel):
    segment_id: str
    balances: tuple[DailyBalance, ...]
