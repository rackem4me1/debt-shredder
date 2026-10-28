from datetime import date
from decimal import Decimal as D
import pytest
from SCHEMA import (SegmentType, CompoundingMethod, DeferredInterestCalculationMethod as Method,
                    RoundingMode, ProvenanceSource as P, assumed_default)
from engine.promotions import assess_promo_exit, PromoExitTerms, PromoExitReason
from engine.interest import DailyBalance
from engine.common import MissingTerms, reconstruct
from test_SCHEMA import _segment


def segment(deferred=True, method=Method.AVERAGE_DAILY_BALANCE_SIMPLE):
    fields=dict(segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST if deferred else SegmentType.PROMOTIONAL_TRUE_ZERO,
        balance='100',apr=assumed_default(D(0)),promo_expiration_date=date(2026,1,3),
        post_promo_apr=assumed_default(D('.365')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))
    if deferred:fields.update(deferred_interest_apr=assumed_default(D('3.65')),
        deferred_interest_calculation_method=assumed_default(method),deferred_interest_to_date=D('5'),
        projected_deferred_interest_at_expiration=D('5'),deferred_interest_as_of_date=date(2025,12,31))
    return _segment(**fields)


def history(last='100'):
    return tuple(DailyBalance(day=date(2026,1,i),balance=last if i==3 else '100') for i in (1,2,3))


def terms(**kwargs):
    return PromoExitTerms(cutoff=date(2026,1,3),rounding_mode=assumed_default(RoundingMode.HALF_UP),**kwargs)


def assess(s=None,h=None,t=None):
    return assess_promo_exit(s or segment(),h or history(),t or terms(),history_provenance=P.ASSUMED_DEFAULT)


def test_expiration_assesses_historical_plus_daily_exposure_once():
    s=segment();before=s.model_dump_json();r=assess(s)
    assert r.deferred_exposure==8 and r.assessed_deferred_interest==8
    assert r.balance_after_assessment==108 and r.waived_deferred_interest==0
    assert r.replacement_apr.value==D('.365') # distinct from retroactive 3.65
    assert r.reversion_starts==date(2026,1,4)
    assert s.model_dump_json()==before
    assert r.label=='estimate'


def test_cutoff_payoff_waives_exposure():
    r=assess(h=history('0'))
    assert r.paid_by_cutoff and r.assessed_deferred_interest==0
    assert r.waived_deferred_interest==7 and r.balance_after_assessment==0


def test_one_cent_unpaid_triggers_full_exposure_with_posting_rounding():
    r=assess(h=history('.01'))
    assert r.deferred_exposure==D('7.0001')
    assert r.assessed_deferred_interest==7
    assert r.balance_after_assessment==D('7.01')


def test_daily_compounding_keeps_full_precision_until_assessment():
    r=assess(s=segment(method=Method.DAILY_COMPOUNDING))
    assert r.deferred_exposure==D('8.181605') # (100+5)*1.01**3 - 100
    assert r.assessed_deferred_interest==D('8.18')


def test_true_zero_never_gets_retroactive_charge():
    r=assess(s=segment(False))
    assert r.balance_after_assessment==100 and r.deferred_exposure==0
    assert r.replacement_apr.value==D('.365')


@pytest.mark.parametrize('assessment',[True,False])
def test_disqualification_uses_explicit_terms(assessment):
    t=terms(reason=PromoExitReason.DISQUALIFICATION,disqualified_apr=assumed_default(D('.8')),
        disqualified_compounding=assumed_default(CompoundingMethod.DAILY_COMPOUNDING),
        assess_deferred_on_disqualification=assumed_default(assessment))
    r=assess(t=t)
    assert r.assessed_deferred_interest==(8 if assessment else 0)
    assert r.replacement_apr.value==D('.8')
    assert r.replacement_compounding.value==CompoundingMethod.DAILY_COMPOUNDING


def test_missing_disqualification_terms_rejected():
    with pytest.raises(ValueError):terms(reason=PromoExitReason.DISQUALIFICATION)


def test_missing_opening_exposure_date_rejected():
    with pytest.raises(MissingTerms,match='dated immediately'):
        assess(s=reconstruct(segment(),deferred_interest_as_of_date=None))


def test_missing_days_and_wrong_cutoff_rejected():
    with pytest.raises(ValueError,match='consecutive'):assess(h=(history()[0],history()[2]))
    with pytest.raises(MissingTerms,match='through the cutoff'):assess(h=history()[:2])


def test_purchase_level_method_still_requires_purchase_history():
    with pytest.raises(MissingTerms,match='purchase-level'):assess(s=segment(method=Method.RETROACTIVE_PURCHASE_SUM))


def test_unassessed_disqualification_exposure_is_not_assumed_waived():
    t=terms(reason=PromoExitReason.DISQUALIFICATION,disqualified_apr=assumed_default(D('.8')),
        disqualified_compounding=assumed_default(CompoundingMethod.SIMPLE_DAILY),
        assess_deferred_on_disqualification=assumed_default(False))
    r=assess(t=t)
    assert r.waived_deferred_interest==0 and r.unassessed_deferred_exposure==8


def test_full_promo_horizon_is_not_truncated_at_ninety_days():
    from datetime import timedelta
    cutoff=date(2026,4,10)
    s=reconstruct(segment(),promo_expiration_date=cutoff)
    h=tuple(DailyBalance(day=date(2026,1,1)+timedelta(days=i),balance='100') for i in range(100))
    r=assess(s=s,h=h,t=reconstruct(terms(),cutoff=cutoff))
    assert r.deferred_exposure==105


def test_result_roundtrips_and_repeat_assessment_is_deterministic():
    r=assess()
    assert type(r).model_validate_json(r.model_dump_json())==r==assess()
