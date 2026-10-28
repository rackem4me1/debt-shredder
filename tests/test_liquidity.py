from datetime import datetime,timedelta,timezone,date
from decimal import Decimal
import pytest
from SCHEMA import CashFlowStatus,TransferTimingPolicy,assumed_default,Sourced,ProvenanceSource
from engine.liquidity import *
from engine.common import MissingTerms
T=datetime(2026,1,2,12,tzinfo=timezone.utc)
D=Decimal


def opening(id='checking',cash='1000',reserve='0',floor='100',primary=True,eligible=False):
    return CashOpening(account_id=id,cleared=cash,reserved=reserve,floor=floor,primary=primary,eligible=eligible)


def atomic(id,kind,amount,day,account='checking'):
    at=T+timedelta(days=day)
    return CashPlan(plan_id=id,kind=kind,amount=amount,source_account_id=None if kind==CashKind.INCOME else account,
        destination_account_id=account if kind==CashKind.INCOME else None,
        initiated_at=at,credited_at=at,debited_at=at,settled_at=at)


def test_future_bills_and_floor_limit_immediate_payment():
    result=project_liquidity((opening(),),(atomic('bill',CashKind.EXPENSE,'600',30),),T)
    assert result.safe_immediate_payment==300
    assert result.status==CashFlowStatus.HEALTHY
    assert result.external_outflows==600 and result.external_income==0


def test_payment_committed_then_bank_debit_without_double_counting():
    p=CashPlan(plan_id='p',kind=CashKind.PAYMENT,amount='200',source_account_id='checking',
        initiated_at=T+timedelta(days=1),credited_at=T+timedelta(days=2),debited_at=T+timedelta(days=3),settled_at=T+timedelta(days=4))
    result=project_liquidity((opening(),),(p,),T)
    at={point.at:point.positions[0] for point in result.points}
    assert at[p.initiated_at].cleared==1000 and at[p.initiated_at].committed==200
    assert at[p.credited_at].cleared==1000
    assert at[p.debited_at].cleared==800 and at[p.debited_at].committed==0
    assert at[p.initiated_at].above_floor==at[p.debited_at].above_floor==700
    assert result.external_outflows==200


def test_transfer_conservation_in_transit_and_holds():
    p=CashPlan(plan_id='t',kind=CashKind.TRANSFER,amount='400',source_account_id='savings',destination_account_id='checking',
        initiated_at=T+timedelta(days=1),debited_at=T+timedelta(days=2),credited_at=T+timedelta(days=3),settled_at=T+timedelta(days=4))
    result=project_liquidity((opening(cash='200'),opening('savings','1000',floor='0',primary=False)),(p,),T)
    assert all(point.aggregate_cash==1200 for point in result.points)
    bytime={point.at:point for point in result.points}
    assert bytime[p.debited_at].in_transit==400
    assert bytime[p.credited_at].in_transit==0
    assert bytime[p.credited_at].positions[0].held==400
    assert bytime[p.settled_at].positions[0].held==0
    assert result.external_income==result.external_outflows==0
    assert result.safe_immediate_payment==100  # savings is not instant cash


def test_reserves_stay_on_physical_account():
    result=project_liquidity((opening(),opening('savings','1500','1200','0',primary=False)),(),T)
    assert result.points[0].positions[0].unrestricted==1000
    assert result.points[0].positions[1].unrestricted==300
    assert result.safe_immediate_payment==900


def test_delayed_transfer_cannot_prevent_bill_before_arrival():
    policy=TransferTimingPolicy(source_account_id='savings',dest_account_id='checking',expected_business_days=assumed_default(3))
    p=transfer_plan(policy,'t',D(500),T,())
    assert p.settled_at==T+timedelta(days=5)  # Friday -> Wednesday
    result=project_liquidity((opening(cash='100',floor='0'),opening('savings','1000',floor='0',primary=False,eligible=True)),
        (p,atomic('early_bill',CashKind.EXPENSE,'200',1)),T,policies=(policy,))
    assert result.safe_immediate_payment==0
    assert result.status==CashFlowStatus.NEGATIVE_CASH
    assert result.first_breach_at==T+timedelta(days=1)


def test_same_day_secondary_requires_verified_route():
    o=(opening(),opening('savings','500',floor='0',primary=False,eligible=True))
    assumed=TransferTimingPolicy(source_account_id='savings',dest_account_id='checking',expected_business_days=assumed_default(0))
    assert project_liquidity(o,(),T,policies=(assumed,)).safe_immediate_payment==900
    verified=TransferTimingPolicy(source_account_id='savings',dest_account_id='checking',expected_business_days=Sourced(value=0,provenance=ProvenanceSource.USER_CONFIRMED,confirmed_date=T.date()))
    assert project_liquidity(o,(),T,policies=(verified,)).safe_immediate_payment==1400


def test_contribution_pause_does_not_unlock_existing_reserve():
    openings=(opening(cash='300',reserve='100',floor='100'),)
    plans=(atomic('future_reserve',CashKind.RESERVE,'150',1),)
    triage=contribution_triage(openings,plans,T,noncritical_plan_ids=('future_reserve',))
    assert triage.baseline.status==CashFlowStatus.BUFFER_BREACH
    assert triage.with_contributions_paused.safe_immediate_payment==100
    assert triage.with_contributions_paused.points[-1].positions[0].reserved==100
    assert triage.peak_shortfall_reduction==50


def test_contribution_transfer_conserves_cash_and_locks_destination():
    policy=TransferTimingPolicy(source_account_id='checking',dest_account_id='savings',expected_business_days=assumed_default(1))
    p=transfer_plan(policy,'fund',D(200),T,(),contribution=True)
    result=project_liquidity((opening(),opening('savings','500','100','0',primary=False)),(p,),T)
    assert all(row.aggregate_cash==1500 for row in result.points)
    assert result.points[-1].positions[1].reserved==300

@pytest.mark.parametrize('cash,reserve,floor,expected',[('100','0','200',CashFlowStatus.BUFFER_BREACH),('100','200','0',CashFlowStatus.OBLIGATION_SHORTFALL),('-1','0','0',CashFlowStatus.NEGATIVE_CASH)])
def test_distinct_statuses(cash,reserve,floor,expected):
    result=project_liquidity((opening(cash=cash,reserve=reserve,floor=floor),),(),T)
    assert result.status==expected and result.safe_immediate_payment==0


def test_events_beyond_horizon_do_not_change_operating_window():
    result=project_liquidity((opening(),),(atomic('later',CashKind.EXPENSE,'2000',91),),T)
    assert result.safe_immediate_payment==900
    assert project_liquidity((opening(),),(atomic('later',CashKind.EXPENSE,'2000',91),),T,horizon_days=180).safe_immediate_payment==0


def test_business_calendar_holidays():
    assert add_business_days(T,1,(date(2026,1,5),)).date()==date(2026,1,6)


def test_duplicate_plan_not_applied_twice():
    p=atomic('same',CashKind.EXPENSE,'100',1)
    with pytest.raises(ValueError,match='unique'):project_liquidity((opening(),),(p,p),T)


@pytest.mark.parametrize('cutoff_day',[1,2,3])
def test_reconcile_and_resume_matches_one_pass_at_every_transfer_stage(cutoff_day):
    from engine.liquidity import reconcile_at,ReconciledOpening
    p=CashPlan(plan_id='t',kind=CashKind.TRANSFER,amount='400',source_account_id='savings',destination_account_id='checking',
        initiated_at=T+timedelta(days=1),debited_at=T+timedelta(days=2),credited_at=T+timedelta(days=3),settled_at=T+timedelta(days=4))
    openings=(opening(cash='200'),opening('savings','1000',floor='0',primary=False))
    complete=project_liquidity(openings,(p,),T,end_at=T+timedelta(days=5))
    checkpoint=reconcile_at(openings,(p,),T,T+timedelta(days=cutoff_day))
    restored=ReconciledOpening.model_validate_json(checkpoint.model_dump_json())
    resumed=project_liquidity(restored.openings,restored.continuing_plans,restored.resume_at,
        initial_transit=restored.in_transit,end_at=T+timedelta(days=5))
    assert resumed.points[-1].positions==complete.points[-1].positions
    assert resumed.points[-1].aggregate_cash==1200
    assert resumed.external_income==resumed.external_outflows==0


@pytest.mark.parametrize('cutoff_day',[1,2,3])
def test_payment_reconciliation_does_not_double_debit(cutoff_day):
    from engine.liquidity import reconcile_at
    p=CashPlan(plan_id='p',kind=CashKind.PAYMENT,amount='200',source_account_id='checking',
        initiated_at=T+timedelta(days=1),credited_at=T+timedelta(days=2),debited_at=T+timedelta(days=3),settled_at=T+timedelta(days=4))
    checkpoint=reconcile_at((opening(),),(p,),T,T+timedelta(days=cutoff_day))
    resumed=project_liquidity(checkpoint.openings,checkpoint.continuing_plans,checkpoint.resume_at,
        initial_transit=checkpoint.in_transit,end_at=T+timedelta(days=5))
    assert resumed.points[-1].positions[0].cleared==800
    assert checkpoint.historical_projection.external_outflows+resumed.external_outflows==200


def test_unexplained_opening_commitment_rejected():
    from engine.common import MissingTerms
    bad=CashOpening(account_id='checking',cleared='1000',floor='100',primary=True,committed='50')
    with pytest.raises(MissingTerms,match='reconcile'):project_liquidity((bad,),(),T)


def test_triage_cannot_cancel_an_already_initiated_contribution():
    from datetime import datetime,timedelta,timezone
    from engine.liquidity import contribution_triage,CashPlan,CashKind,CashOpening
    import pytest
    start=datetime(2026,1,2,tzinfo=timezone.utc)
    p=CashPlan(plan_id='started',kind=CashKind.CONTRIBUTION,amount='10',source_account_id='checking',destination_account_id='savings',
        initiated_at=start-timedelta(days=1),debited_at=start+timedelta(days=1),
        credited_at=start+timedelta(days=2),settled_at=start+timedelta(days=3))
    with pytest.raises(ValueError,match='future contributions'):
        contribution_triage((CashOpening(account_id='checking',cleared='10',committed='10',floor='1',primary=True),
            CashOpening(account_id='savings',cleared='0',floor='0')),(p,),start,noncritical_plan_ids=('started',))
