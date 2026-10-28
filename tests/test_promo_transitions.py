from datetime import date
from decimal import Decimal as D
import pytest
from SCHEMA import GracePeriodState as G, CompoundingMethod, assumed_default, SegmentType, BillingCycle
from engine.common import ZERO, reconstruct, MissingTerms
from engine.promotions import PromoTransition, PromoExitReason, assess_promo_exit
from engine.simulation import simulate_revolving
from engine.allocation import allocate_payment
from engine.interest import DailyBalance
from test_promotions import segment, terms
from test_SCHEMA import _account, _segment
from test_search_simulation import cycles as base_cycles, minimum

def cycles():
    return (BillingCycle(cycle_id="2025-11",account_id="a1",start_date=date(2025,11,1),end_date=date(2025,11,30),statement_date=date(2025,11,30),due_date=date(2025,12,20)),)+base_cycles()


def run(seg=None,dates=(),amount='0',end=date(2026,1,31),transition=None):
    seg=seg or segment()
    t=transition or PromoTransition(segment_id=seg.segment_id,terms=terms(),post_exit_grace_eligible=assumed_default(False))
    a=_account(segments=(seg,),current_grace_state=G.LOST_GRACE,minimum_payment_floor=assumed_default(ZERO))
    return simulate_revolving(a,date(2026,1,1),end,cycles(),minimum(),dates,lambda *args:D(amount),promo_transitions=(t,))


def test_expiration_assessment_and_new_rate_post_exactly_once():
    s=segment();r=run(s)
    assert r.promo_exits[0].assessed_deferred_interest==8
    assert r.account.total_balance()==D('111.02') # 108 + round(108*.001*28)
    assert r.minimum_remaining==D('13.24') # 8 assessed + 3.02 billed + 2% * 111.02
    assert [(a.on,a.amount) for a in r.audit if a.kind=='promo_exit']==[(date(2026,1,3),D(8))]
    assert len(r.daily_histories[0].balances)==31
    # The frozen source APR remains zero; runtime terms carry reversion.
    assert r.account.segments[0].apr.value==0
    assert r.promo_exits[0].replacement_apr.value==D('.365')
    assert s.balance==100 and s.deferred_interest_to_date==5


def test_cutoff_payment_waives_and_prevents_future_accrual():
    r=run(dates=(date(2026,1,3),),amount='100')
    assert r.account.total_balance()==0
    assert r.promo_exits[0].waived_deferred_interest==7
    assert not any(a.kind=='interest_posting' for a in r.audit)


def test_next_day_payoff_includes_assessed_charge():
    r=run(dates=(date(2026,1,4),),amount='108')
    assert r.account.total_balance()==0
    assert r.payments[0].amount==108
    assert r.promo_exits[0].assessed_deferred_interest==8


def test_true_zero_reversion_has_no_retroactive_charge():
    r=run(segment(False))
    assert r.account.total_balance()==D('102.80')
    assert r.promo_exits[0].assessed_deferred_interest==0


def test_daily_compounding_after_exit():
    s=reconstruct(segment(False),post_promo_compounding_method=assumed_default(CompoundingMethod.DAILY_COMPOUNDING))
    r=run(s,end=date(2026,1,5))
    assert r.account.segments[0].accrued_unposted_interest==D('.2001')


def test_disqualification_changes_rate_and_excess_priority():
    s=reconstruct(segment(False),promo_expiration_date=date(2026,4,15))
    t=terms(reason=PromoExitReason.DISQUALIFICATION,disqualified_apr=assumed_default(D('.8')),
        disqualified_compounding=assumed_default(CompoundingMethod.SIMPLE_DAILY),assess_deferred_on_disqualification=assumed_default(False))
    transition=PromoTransition(segment_id=s.segment_id,terms=t,post_exit_grace_eligible=assumed_default(False))
    a=_account(segments=(s,_segment(segment_id='ordinary',balance='100',apr=assumed_default(D('.5')))),current_grace_state=G.LOST_GRACE)
    r=simulate_revolving(a,date(2026,1,1),date(2026,1,4),cycles(),minimum(),(date(2026,1,4),),lambda *args:D(10),promo_transitions=(transition,))
    assert next(x.balance for x in r.account.segments if x.segment_id==s.segment_id)==90
    assert next(x.balance for x in r.account.segments if x.segment_id=='ordinary')==100


def test_disqualified_segment_loses_upcoming_promo_override():
    s=reconstruct(segment(False),promo_expiration_date=date(2026,4,15))
    t=reconstruct(terms(reason=PromoExitReason.DISQUALIFICATION,disqualified_apr=assumed_default(D('.1')),
        disqualified_compounding=assumed_default(CompoundingMethod.SIMPLE_DAILY),assess_deferred_on_disqualification=assumed_default(False)),cutoff=date(2026,2,1))
    exit_=assess_promo_exit(s,(DailyBalance(day=date(2026,2,1),balance='100'),),t,history_provenance=s.balance_provenance)
    a=_account(segments=(s,_segment(segment_id='ordinary',balance='100',apr=assumed_default(D('.5')))))
    r=allocate_payment(a,D(10),minimum(),date(2026,2,2),cycles(),promo_exits=(exit_,))
    assert r.lines[0].segment_id=='ordinary' and r.lines[0].phase=='excess'


def test_exit_on_statement_close_is_assessed_before_minimum():
    s=reconstruct(segment(),promo_expiration_date=date(2026,1,31))
    transition=PromoTransition(segment_id=s.segment_id,terms=reconstruct(terms(),cutoff=date(2026,1,31)),post_exit_grace_eligible=assumed_default(False))
    r=run(s,transition=transition)
    assert r.account.total_balance()==136
    assert r.minimum_remaining==D('38.72')
    assert not any(a.kind=='interest_posting' for a in r.audit)


def test_unprovided_transition_still_stops():
    a=_account(segments=(segment(),),current_grace_state=G.LOST_GRACE)
    with pytest.raises(MissingTerms,match='explicit transition'):
        simulate_revolving(a,date(2026,1,1),date(2026,1,4),cycles(),minimum(),(),lambda *args:ZERO)


def test_post_exit_debt_conservation_and_serialization():
    r=run(dates=(date(2026,1,4),),amount='50')
    charges=sum((a.amount for a in r.audit if a.kind in ('promo_exit','interest_posting')),ZERO)
    paid=sum((p.amount for p in r.payments),ZERO)
    assert r.account.total_balance()==D(100)+charges-paid
    assert r.account.total_balance()==D('59.62') # 58 principal after payment + 28*.058
    assert type(r).model_validate_json(r.model_dump_json())==r


def test_expired_rate_controls_minimum_allocation_too():
    s=segment(False)
    exit_=assess_promo_exit(s,(DailyBalance(day=date(2026,1,3),balance='100'),),terms(),history_provenance=s.balance_provenance)
    a=_account(segments=(s,_segment(segment_id='ordinary',balance='100',apr=assumed_default(D('.2')))))
    r=allocate_payment(a,D(10),minimum('10'),date(2026,1,4),cycles(),promo_exits=(exit_,))
    assert r.lines[0].segment_id=='ordinary' and r.lines[0].phase=='minimum'


def test_duplicate_transition_is_rejected_before_callback():
    s=segment();t=PromoTransition(segment_id=s.segment_id,terms=terms(),post_exit_grace_eligible=assumed_default(False))
    def callback(*args):raise AssertionError('callback must not run')
    with pytest.raises(ValueError,match='unique'):
        simulate_revolving(_account(segments=(s,)),date(2026,1,1),date(2026,1,31),cycles(),minimum(),
            (date(2026,1,2),),callback,promo_transitions=(t,t))


def test_wrong_deferred_cutoff_rejected_before_callback():
    s=segment();t=PromoTransition(segment_id=s.segment_id,terms=reconstruct(terms(),cutoff=date(2026,1,4)),post_exit_grace_eligible=assumed_default(False))
    def callback(*args):raise AssertionError('callback must not run')
    with pytest.raises(ValueError,match='match segment expiration'):
        simulate_revolving(_account(segments=(s,)),date(2026,1,1),date(2026,1,31),cycles(),minimum(),
            (date(2026,1,2),),callback,promo_transitions=(t,))


def test_reproducible_promo_demo():
    from demo_promotions import run as demo
    r=demo()['outcomes']
    assert r['unpaid']['ending_posted_balance']=='106.77'
    assert r['unpaid']['exit']['assessed_deferred_interest']=='5.30'
    assert r['paid_on_cutoff']['ending_posted_balance']=='0.00'
    assert D(r['paid_on_cutoff']['exit']['waived_deferred_interest'])==D('5.2')


def test_transition_monthly_terms_stop_before_replay():
    from engine.common import UnsupportedTerms
    s=reconstruct(segment(False),post_promo_compounding_method=assumed_default(CompoundingMethod.MONTHLY_COMPOUNDING))
    with pytest.raises(UnsupportedTerms,match='monthly capitalization'):run(s)


def test_opening_deferred_history_gap_stops_before_replay():
    s=reconstruct(segment(),deferred_interest_as_of_date=date(2025,12,30))
    with pytest.raises(MissingTerms,match='precede replay start'):run(s)


def test_allocation_rejects_replacement_terms_on_cutoff_day():
    s=segment(False)
    e=assess_promo_exit(s,(DailyBalance(day=date(2026,1,3),balance='100'),),terms(),history_provenance=s.balance_provenance)
    with pytest.raises(ValueError,match='before reversion'):
        allocate_payment(_account(segments=(s,)),D(1),minimum(),date(2026,1,3),cycles(),promo_exits=(e,))
