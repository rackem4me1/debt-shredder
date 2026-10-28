from datetime import date
from decimal import Decimal as D
from SCHEMA import GracePeriodState as G, assumed_default
from engine.common import reconstruct, ZERO
from engine.promotions import PromoTransition
from engine.simulation import plan_promo
from engine.liquidity import CashOpening
from test_promotions import segment,terms
from test_SCHEMA import _account
from test_search_simulation import cycles,minimum


def plan(cash):
    s=reconstruct(segment(),balance=D('.02'),deferred_interest_to_date=D('0'),
        projected_deferred_interest_at_expiration=D('0'),promo_expiration_date=date(2026,4,15))
    a=_account(segments=(s,),current_grace_state=G.LOST_GRACE)
    t=PromoTransition(segment_id=s.segment_id,terms=reconstruct(terms(),cutoff=s.promo_expiration_date),
        post_exit_grace_eligible=assumed_default(False))
    return plan_promo(a,s.segment_id,date(2026,1,1),date(2026,1,21),cycles(),minimum(),(date(2026,1,20),),
        (CashOpening(account_id='checking',cleared=cash,floor='0',primary=True),),(),exposure_transitions=(t,))


def test_infeasible_plan_reports_full_horizon_without_inventing_payments():
    r=plan('.01')
    assert not r.search.feasible
    extra=r.no_additional_payments_projection
    assert extra.payments==r.projection.payments
    assert extra.daily_histories[0].balances[-1].day==date(2026,4,15)
    # 19 days at .02, followed by 86 days at .01, each at 1% daily.
    assert extra.promo_exits[0].deferred_exposure==D('.0124')
    assert extra.promo_exits[0].assessed_deferred_interest==D('.01')
    assert extra.account.total_balance()==D('.02')
    assert len(extra.daily_histories[0].balances)==105


def test_successful_plan_reports_waiver_and_same_fixed_payments():
    r=plan('.02')
    assert r.search.feasible
    extra=r.no_additional_payments_projection
    assert extra.payments==r.projection.payments
    assert extra.promo_exits[0].assessed_deferred_interest==0
    assert extra.promo_exits[0].waived_deferred_interest==D('.0038')
    assert extra.account.total_balance()==0


def test_target_disqualification_is_not_an_active_promo_payoff_plan():
    import pytest
    from engine.common import MissingTerms
    from engine.promotions import PromoExitReason
    from SCHEMA import CompoundingMethod
    s=reconstruct(segment(),promo_expiration_date=date(2026,4,15))
    t=PromoTransition(segment_id=s.segment_id,post_exit_grace_eligible=assumed_default(False),
        terms=reconstruct(terms(),reason=PromoExitReason.DISQUALIFICATION,cutoff=date(2026,1,3),
            disqualified_apr=assumed_default(D('.5')),
            disqualified_compounding=assumed_default(CompoundingMethod.SIMPLE_DAILY),
            assess_deferred_on_disqualification=assumed_default(True)))
    with pytest.raises(MissingTerms,match='target exits'):
        plan_promo(_account(segments=(s,)),s.segment_id,date(2026,1,1),date(2026,1,21),cycles(),minimum(),(),
            (CashOpening(account_id='checking',cleared='100',floor='0',primary=True),),(),promo_transitions=(t,))


def test_exposure_resume_matches_independent_full_replay():
    from engine.simulation import simulate_revolving
    r=plan('.01');cp=r.projection.checkpoint
    fixed={p.on:p.amount for p in r.projection.payments}
    expected=simulate_revolving(cp.source_account,cp.start,date(2026,4,15),cp.cycles,cp.initial_minimum,
        tuple(fixed),lambda day,*args:fixed[day],grace_terms=cp.grace_terms,promo_transitions=cp.promo_transitions)
    assert r.no_additional_payments_projection==expected
    # The planning checkpoint carries the pending future exit, not a premature assessment.
    assert cp.promo_transitions and not cp.promo_exits
