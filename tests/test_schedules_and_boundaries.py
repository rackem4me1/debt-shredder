from datetime import date,datetime,time,timezone
from decimal import Decimal
import pytest
from SCHEMA import *
from engine.schedules import *
from engine.common import *
from engine.loans import pay_loan,accrue_loan
from engine.liquidity import openings_from_snapshot
from engine.simulation import simulate_revolving
from test_SCHEMA import _loan,_account,_segment,_liquidity_account
from test_search_simulation import cycles,minimum
D=Decimal


def test_semimonthly_spill_preserves_two_same_date_events():
    result=scheduled_dates(IncomeCadence.SEMIMONTHLY,date(2026,1,30),date(2026,3,1),date(2026,3,1),
        semimonthly_days=(30,31),short_month_rule=SemimonthlyShortMonthRule.ROLL_TO_NEXT_MONTH_FIRST_DAY)
    assert len(result)==2
    assert result[0][0]!=result[1][0]
    assert all(day==date(2026,3,1) for key,day in result)


def test_monthly_clamp_does_not_drift_to_28th_permanently():
    result=scheduled_dates(IncomeCadence.MONTHLY,date(2026,1,31),date(2026,1,31),date(2026,3,31),
        day_of_month=31,short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH)
    assert tuple(day for key,day in result)==(date(2026,1,31),date(2026,2,28),date(2026,3,31))


def test_biweekly_not_twice_monthly_and_irregular_not_invented():
    result=scheduled_dates(IncomeCadence.BIWEEKLY,date(2026,1,2),date(2026,1,1),date(2026,1,31),weekday=4)
    assert tuple(day.day for key,day in result)==(2,16,30)
    assert len(scheduled_dates(IncomeCadence.IRREGULAR,date(2026,1,2),date(2026,1,1),date(2026,12,31)))==1


def test_snapshot_external_schedule_and_floors():
    s=FinancialSnapshot(liquidity_accounts=(_liquidity_account(),),liquidity_floors=(AccountLiquidityFloor(account_id='chk1',minimum_balance='100'),),
        income_sources=(IncomeSource(source_id='job',destination_account_id='chk1',cadence='monthly',amount='1000',anchor_date=date(2026,1,1),day_of_month=1),),
        obligations=(ScheduledObligation(obligation_id='rent',source_account_id='chk1',description='rent',amount='500',due_date=date(2026,1,3)),))
    plans=external_cash_schedule(s,date(2026,1,1),date(2026,1,31),timezone_name='America/Chicago',income_time=time(9),obligation_time=time(12),contribution_time=time(12),monthly_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,holidays=())
    assert len(plans)==2 and plans[0].initiated_at.hour==15
    assert openings_from_snapshot(s)[0].floor==100


def test_pending_actuals_not_silently_ignored():
    s=FinancialSnapshot(liquidity_accounts=(_liquidity_account(pending_debits='50'),),)
    with pytest.raises(MissingTerms,match='pending'):openings_from_snapshot(s)


def test_precomputed_requires_actual_rebate_inputs():
    loan=_loan(loan_type=LoanType.PRECOMPUTED,prepayment_behavior=assumed_default(PrepaymentBehavior.PRECOMPUTED_REBATE_REDUCTION),rebate_method=assumed_default(RebateMethod.RULE_OF_78))
    with pytest.raises(MissingTerms):pay_loan(loan,D(500))
    with pytest.raises(MissingTerms):accrue_loan(loan,date(2026,1,1),date(2026,2,1))


def test_loan_rounds_at_credit_posting_not_daily():
    result=pay_loan(_loan(accrued_interest=D('1.005')),D(10))
    assert result.interest_paid==D('1.01') and result.principal_paid==D('8.99')
    assert result.interest_posting_adjustment==D('.005')


def test_full_or_pending_grace_cannot_cross_due_date_without_statement_balance():
    with pytest.raises(MissingTerms,match='grace resolution'):
        simulate_revolving(_account(),date(2026,1,1),date(2026,1,31),cycles(),minimum(),(),lambda *args:ZERO)
