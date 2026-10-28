from decimal import Decimal as D
from datetime import timedelta
import pytest
from dashboard.multimonth import example
from engine.minimum_forecast import forecast_minimums,MinimumTerms,PaymentSlot
from engine.common import reconstruct
from engine.liquidity import CashPlan,CashKind


def run(s=None,slots=None,terms=None):
    s=s or example()
    slots=slots or tuple(PaymentSlot(slot_id=r.request_id,**{k:getattr(r,k) for k in ('initiated_at','credited_at','debited_at','settled_at')}) for r in s.requests)
    return forecast_minimums(s.debts[0],s.openings[0],s.cash_plans,slots,s.start,s.end,terms or MinimumTerms(floor='25',rate='.01'))


def test_generated_minimums_follow_posted_statements_and_conserve_cash():
    # Jan interest 19*1 +12*.975=30.70, balance1005.70 -> min40.76.
    # Feb interest19*1.0057 +9*.96494=27.79276 ->27.79, balance992.73 ->min37.72.
    r=run()
    assert [d.requested for d in r.decisions]==[D('25'),D('40.76'),D('37.72')]
    assert all(d.accepted==d.requested for d in r.decisions)
    assert r.liquidity.points[-1].positions[0].cleared==D('296.52')
    assert not r.debt.missed_due_dates


def test_shortfall_is_visible_and_floor_preserved():
    s=example();s=reconstruct(s,openings=(reconstruct(s.openings[0],cleared='120'),))
    r=run(s)
    assert r.decisions[0].accepted==20 and r.decisions[0].unmet==5
    assert all(d.accepted==0 for d in r.decisions[1:])
    assert r.liquidity.points[-1].positions[0].cleared==100
    assert len(r.debt.missed_due_dates)==3


def test_future_income_does_not_fund_earlier_initiation():
    s=example();at=s.requests[0].initiated_at+timedelta(days=1)
    income=CashPlan(plan_id='payday',kind=CashKind.INCOME,amount='100',destination_account_id='checking',initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    s=reconstruct(s,openings=(reconstruct(s.openings[0],cleared='100'),),cash_plans=(income,))
    r=run(s)
    assert r.decisions[0].accepted==0
    assert r.decisions[1].accepted>0


def test_terms_must_be_explicit_and_match_account():
    with pytest.raises(ValueError):run(terms=MinimumTerms(floor='30',rate='.01'))


def test_slot_order_and_duplicate_identity_rejected():
    s=example();slots=tuple(PaymentSlot(slot_id=r.request_id,**{k:getattr(r,k) for k in ('initiated_at','credited_at','debited_at','settled_at')}) for r in s.requests)
    with pytest.raises(ValueError):run(slots=slots[::-1])
    with pytest.raises(ValueError):run(slots=(slots[0],slots[0]))


def test_residual_interest_can_be_paid_beyond_opening_posted_balance():
    s=example();debt=s.debts[0]
    debt=reconstruct(debt,initial_minimum=reconstruct(debt.initial_minimum,statement_minimum_original='1000',statement_minimum_remaining='1000'))
    s=reconstruct(s,debts=(debt,),openings=(reconstruct(s.openings[0],cleared='5000'),))
    r=run(s)
    assert [d.accepted for d in r.decisions]==[D('1000'),D('19'),D('.36')]
    assert sum(d.accepted for d in r.decisions)==D('1019.36')
    assert r.debt.account.total_balance()==D('.01')


def test_credit_before_bank_debit_still_conserves_cash():
    s=example();slots=tuple(PaymentSlot(slot_id=r.request_id,initiated_at=r.initiated_at-timedelta(days=2),credited_at=r.credited_at,debited_at=r.debited_at+timedelta(days=1),settled_at=r.settled_at+timedelta(days=2)) for r in s.requests)
    r=run(slots=slots)
    assert [d.accepted for d in r.decisions]==[D('25'),D('40.76'),D('37.72')]
    assert r.liquidity.points[-1].positions[0].cleared==D('296.52')


def test_protected_reserved_cash_and_future_bills_reduce_capacity():
    s=example();at=s.start+timedelta(days=70)
    bill=CashPlan(plan_id='bill',kind=CashKind.EXPENSE,amount='250',source_account_id='checking',initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    s=reconstruct(s,openings=(reconstruct(s.openings[0],reserved='30'),),cash_plans=(bill,))
    r=run(s)
    assert r.decisions[0].accepted==20
    assert r.liquidity.points[-1].positions[0].cleared==130


def test_results_independent_of_callers_decimal_precision():
    from decimal import localcontext
    expected=run()
    with localcontext() as c:
        c.prec=6
        assert run()==expected


@pytest.mark.parametrize('mode',['grace','transfer','fractional_floor','fractional_minimum'])
def test_unsupported_inputs_fail_before_generating_payments(mode):
    from SCHEMA import GracePeriodState,assumed_default
    s=example();debt=s.debts[0];terms=MinimumTerms(floor='25',rate='.01')
    if mode=='grace':debt=reconstruct(debt,account=reconstruct(debt.account,current_grace_state=GracePeriodState.FULL_GRACE))
    if mode=='fractional_floor':
        debt=reconstruct(debt,account=reconstruct(debt.account,minimum_payment_floor=assumed_default(D('25.001'))))
        terms=MinimumTerms(floor='25.001',rate='.01')
    if mode=='fractional_minimum':debt=reconstruct(debt,initial_minimum=reconstruct(debt.initial_minimum,statement_minimum_remaining='24.999'))
    s=reconstruct(s,debts=(debt,))
    if mode=='transfer':
        at=s.start
        plan=CashPlan(plan_id='transfer',kind=CashKind.TRANSFER,amount='10',source_account_id='checking',destination_account_id='other',initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
        s=reconstruct(s,cash_plans=(plan,))
    with pytest.raises(ValueError):run(s,terms=terms)
