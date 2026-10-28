from datetime import date,datetime,timedelta,timezone
from decimal import Decimal,localcontext
import calendar
import pytest
from SCHEMA import *
from engine.common import *
from engine.search import *
from engine.simulation import *
from engine.liquidity import *
from test_SCHEMA import _account,_segment
D=Decimal


def test_scalar_bisection_clips_each_event_at_its_own_capacity():
    caps=(D(50),D(150))
    def evaluate(candidate):return max(ZERO,D(160)-sum((min(candidate,cap) for cap in caps),ZERO))
    result=bounded_payment_search(evaluate,D(150),monotone_contract=True)
    assert result.candidate==D(110) and result.feasible and result.method=='bounded_bisection'
    assert result.evaluations<30


def test_nonmonotone_island_not_missed_by_dollar_grid():
    def evaluate(candidate):return ZERO if D('.42')<=candidate<=D('.48') else D(1)
    result=bounded_payment_search(evaluate,D(2))
    assert result.candidate==D('.42') and result.minimum_certified
    assert result.method=='bounded_grid_cent_verification'


def test_observed_monotonicity_violation_triggers_fallback():
    def evaluate(candidate):
        return D(2) if candidate<D('.25') else ZERO if candidate<D('.4') else D(3)
    result=bounded_payment_search(evaluate,D(1),monotone_contract=True)
    assert result.candidate==D('.25') and result.method=='bounded_grid_cent_verification'


def test_infeasible_and_zero_and_budget():
    r=bounded_payment_search(lambda p:D(1),D('.03'))
    assert not r.feasible and r.candidate==D('.03')
    assert bounded_payment_search(lambda p:ZERO,D(100)).candidate==0
    with pytest.raises(SearchBudgetExceeded):bounded_payment_search(lambda p:D(1),D(100),max_evaluations=10)
    with pytest.raises(ValueError):bounded_payment_search(lambda p:float(1),D(1))


def cycles():
    result=[]
    for y,m in [(2025,12),(2026,1),(2026,2),(2026,3),(2026,4)]:
        end=date(y,m,calendar.monthrange(y,m)[1])
        due=date(y+(m==12),m%12+1,20)
        result.append(BillingCycle(cycle_id=f'{y}-{m}',account_id='a1',start_date=date(y,m,1),end_date=end,statement_date=end,due_date=due))
    return tuple(result)


def minimum(amount='0'):
    return MinimumPaymentSnapshot(account_id='a1',billing_cycle_id='2025-12',statement_minimum_original=amount,statement_minimum_remaining=amount)


def test_daily_interest_posts_only_at_statement_close():
    a=_account(current_grace_state=GracePeriodState.LOST_GRACE,segments=(_segment(balance='100',apr=assumed_default(D('3.65'))),))
    result=simulate_revolving(a,date(2026,1,1),date(2026,1,31),cycles(),minimum(),(),lambda *args:ZERO)
    assert result.account.total_balance()==131
    assert result.account.segments[0].accrued_unposted_interest==0
    assert result.minimum_remaining==D('33.62')  # 31 billed interest + 2% of 131
    assert len([r for r in result.audit if r.kind=='interest_posting'])==1


def test_morning_credit_reduces_same_day_interest():
    a=_account(current_grace_state=GracePeriodState.LOST_GRACE,segments=(_segment(balance='100',apr=assumed_default(D('3.65'))),))
    r=simulate_revolving(a,date(2026,1,1),date(2026,1,2),cycles(),minimum(),(date(2026,1,1),),lambda *args:D(50))
    assert r.account.total_balance()==50
    assert r.account.segments[0].accrued_unposted_interest==1
    assert len(r.payments)==1


def test_pending_grace_dual_track():
    a=_account(segments=(_segment(balance='100',apr=assumed_default(D('3.65'))),))
    r=simulate_revolving(a,date(2026,1,1),date(2026,1,3),cycles(),minimum(),(),lambda *args:ZERO)
    assert r.account.total_balance()==100 and r.contingent_grace_interest==3
    assert r.account.segments[0].accrued_unposted_interest==0


def test_due_date_failure_is_explicit():
    r=simulate_revolving(_account(current_grace_state=GracePeriodState.LOST_GRACE),date(2026,1,1),date(2026,1,21),cycles(),minimum('25'),(),lambda *args:ZERO)
    assert r.missed_due_dates==(date(2026,1,20),)


def test_integrated_promo_search_uses_cash_from_each_date_once():
    seg=_segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='2',apr=assumed_default(ZERO),
        promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))
    a=_account(segments=(seg,))
    opening=CashOpening(account_id='checking',cleared='1',floor='0',primary=True)
    at=datetime(2026,1,15,12,tzinfo=timezone.utc)
    income=CashPlan(plan_id='payday',kind=CashKind.INCOME,amount='1',destination_account_id='checking',initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    result=plan_promo(a,'promo',date(2026,1,1),date(2026,1,21),cycles(),minimum(),(date(2026,1,10),date(2026,1,20)),(opening,),(income,),max_evaluations=500)
    assert result.search.feasible and result.search.candidate==1
    assert result.target_remaining==0
    assert tuple(p.amount for p in result.projection.payments)==(D(1),D(1))


def test_debt_horizon_beyond_ninety_days_is_not_truncated():
    seg=_segment(balance='10',apr=assumed_default(ZERO))
    result=simulate_revolving(_account(segments=(seg,)),date(2026,1,1),date(2026,4,20),cycles(),minimum(),(date(2026,4,10),),lambda *args:D(10))
    assert result.account.total_balance()==0
    assert result.payments[0].on==date(2026,4,10)


def test_integrated_promo_does_not_assume_unscheduled_secondary_transfer():
    seg=_segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='.02',apr=assumed_default(ZERO),
        promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))
    primary=CashOpening(account_id='checking',cleared='0',floor='0',primary=True)
    savings=CashOpening(account_id='savings',cleared='100',floor='0',eligible=True)
    policy=TransferTimingPolicy(source_account_id='savings',dest_account_id='checking',expected_business_days=Sourced(value=0,provenance=ProvenanceSource.USER_CONFIRMED,confirmed_date=date(2026,1,1)))
    result=plan_promo(_account(segments=(seg,)),'promo',date(2026,1,1),date(2026,1,21),cycles(),minimum(),(date(2026,1,10),),(primary,savings),(),policies=(policy,))
    assert not result.search.feasible and result.target_remaining==D('.02')


def test_large_search_bound_honors_budget_without_building_giant_grid():
    with pytest.raises(SearchBudgetExceeded):bounded_payment_search(lambda p:D(1),D('100000000000000000'),max_evaluations=8)


def test_negative_subcent_candidate_is_not_rounded_to_zero():
    with pytest.raises(ValueError,match='negative'):
        simulate_revolving(_account(),date(2026,1,1),date(2026,1,2),cycles(),minimum(),(date(2026,1,1),),lambda *args:D('-.001'))


def test_promo_credit_delay_changes_debt_date_and_checks_buffer():
    from engine.timing import PaymentTiming
    from datetime import time
    timing=PaymentTiming(credit_business_days=assumed_default(1),debit_business_days=assumed_default(2),settlement_business_days=assumed_default(3),timezone_name='UTC',initiation_time=time(12))
    seg=_segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='.02',apr=assumed_default(ZERO),
        promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))
    result=plan_promo(_account(segments=(seg,)),'promo',date(2026,1,1),date(2026,1,21),cycles(),minimum(),(date(2026,1,2),),
        (CashOpening(account_id='checking',cleared='.02',floor='0',primary=True),),(),payment_timing=timing)
    assert result.projection.payments[0].on==date(2026,1,5)  # Friday initiation, Monday credit
    assert result.target_remaining==0
    with pytest.raises(ValueError,match='credit date'):
        plan_promo(_account(segments=(seg,)),'promo',date(2026,1,1),date(2026,1,4),cycles(),minimum(),(date(2026,1,2),),
            (CashOpening(account_id='checking',cleared='.02',floor='0',primary=True),),(),payment_timing=timing)


def test_overlapping_payment_commitments_cannot_spend_later_income_early():
    from engine.timing import PaymentTiming
    from datetime import time
    timing=PaymentTiming(credit_business_days=assumed_default(1),debit_business_days=assumed_default(3),
        settlement_business_days=assumed_default(4),timezone_name='UTC',initiation_time=time(12))
    seg=_segment(segment_id='promo',segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO,balance='.04',apr=assumed_default(ZERO),
        promo_expiration_date=date(2026,4,15),post_promo_apr=assumed_default(D('.2')),
        post_promo_compounding_method=assumed_default(CompoundingMethod.SIMPLE_DAILY))
    at=datetime(2026,1,6,12,tzinfo=timezone.utc)
    income=CashPlan(plan_id='later',kind=CashKind.INCOME,amount='.02',destination_account_id='checking',
        initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    result=plan_promo(_account(segments=(seg,)),'promo',date(2026,1,1),date(2026,1,21),cycles(),minimum(),
        (date(2026,1,2),date(2026,1,5)),(CashOpening(account_id='checking',cleared='.02',floor='0',primary=True),),
        (income,),payment_timing=timing)
    assert not result.search.feasible
    assert sum((p.amount for p in result.projection.payments),ZERO)==D('.02')
