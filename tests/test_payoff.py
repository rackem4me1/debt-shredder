"""Independent payoff arithmetic, cash boundaries, residual interest and CLI inputs."""
import calendar
import json
from datetime import timedelta,date
from decimal import Decimal as D,localcontext
from fractions import Fraction as F
import pytest
from SCHEMA import assumed_default,CompoundingMethod
from demo_payoff import example
from engine.common import reconstruct
from engine.payoff import plan_payoff,compare_payoff
from engine.liquidity import CashPlan,CashKind
from payoff_cli import parse_input,run


def zero_rate(value,balance='500'):
    return reconstruct(value,debts=tuple(reconstruct(d,account=reconstruct(d.account,segments=(reconstruct(
        d.account.segments[0],balance=balance,apr=assumed_default(D('0'))),))) for d in value.debts))


def test_hand_calculated_zero_interest_four_payments_no_budget_overspend():
    value=zero_rate(example());result=plan_payoff(value)
    assert result.payoff_date==date(2026,4,20)
    assert result.total_paid==1000 and result.posted_interest==0
    assert result.remaining_posted==result.remaining_unposted_interest==0
    assert result.all_minimums_met
    totals=[sum(p.total_paid for p in result.payments if p.slot_id==s.slot_id) for s in value.slots]
    assert totals==[D('250')]*4+[D('0')]*8
    assert result.liquidity.points[-1].positions[0].cleared==400+15*300-1000


def independent_single_card(value):
    """Fraction-based day ledger, independent of engine replay/allocation helpers."""
    debt=value.debts[0];balance=F(debt.account.segments[0].balance);accrued=F(0)
    rate=F(debt.account.segments[0].apr.value)/365
    payments={s.credited_at.date() for s in value.slots};target=F(value.payment_target)
    paid=F(0);interest=F(0);payoff=None;day=value.start.date()
    while day<=value.end.date():
        if day in payments:
            amount=min(balance,target);balance-=amount;paid+=amount
        accrued+=balance*rate
        if day.day==calendar.monthrange(day.year,day.month)[1]:
            cents=accrued*100
            posted=F((cents.numerator*2//cents.denominator+1)//2,100)
            balance+=posted;interest+=posted;accrued=F(0)
        if not balance and not accrued and payoff is None:payoff=day
        day+=timedelta(days=1)
    return paid,interest,balance,accrued,payoff


def test_independent_fraction_oracle_includes_trailing_interest_and_close_rounding():
    value=example();value=reconstruct(value,debts=(value.debts[0],),payment_target='250')
    result=plan_payoff(value);paid,interest,balance,accrued,payoff=independent_single_card(value)
    assert F(result.total_paid)==paid
    assert F(result.posted_interest)==interest
    assert F(result.remaining_posted)==balance and F(result.remaining_unposted_interest)==accrued
    assert result.payoff_date==payoff
    principal_zero_date=next(p.credited_at.date() for p in reversed(result.payments) if p.total_paid>0)
    assert result.payoff_date>=principal_zero_date
    assert result.total_paid==D('1000')+result.posted_interest


def test_comparison_same_inputs_exact_reconciliation_and_minimums_before_extras():
    value=example();comparison=compare_payoff(value)
    assert comparison.lowest_interest_strategy=='highest_interest_first'
    a,b=comparison.results
    assert a.posted_interest==D('74.18') and b.posted_interest==D('93.43')
    assert a.payoff_date==date(2026,8,31) and b.payoff_date==date(2026,9,30)
    for result in comparison.results:
        assert result.total_paid==1500+result.posted_interest
        assert all(p.minimum_paid==p.minimum_required for p in result.payments)
        assert all(p.above_floor>=0 for point in result.liquidity.points for p in point.positions)
        assert result.liquidity.external_outflows==15*900+result.total_paid
    assert b.payments[0].account_id=='high-rate' and b.payments[0].extra_paid==0
    with localcontext() as context:
        context.prec=6
        assert compare_payoff(value)==comparison
    reversed_input=reconstruct(value,debts=value.debts[::-1])
    assert compare_payoff(reversed_input)==comparison


def test_cash_reserves_future_bill_and_future_income_never_fund_earlier_payment():
    value=example();later=value.slots[0].credited_at+timedelta(days=1)
    income=CashPlan(plan_id='later-pay',kind=CashKind.INCOME,amount='500',destination_account_id='checking',
        initiated_at=later,credited_at=later,debited_at=later,settled_at=later)
    value=reconstruct(value,opening=reconstruct(value.opening,cleared='150'),cash_plans=(income,))
    result=plan_payoff(value)
    assert sum(p.total_paid for p in result.payments if p.slot_id==value.slots[0].slot_id)==0
    assert not result.all_minimums_met
    # A large later bill consumes that income, leaving only $30 above floor/reserve today.
    expense=reconstruct(income,plan_id='later-bill',kind=CashKind.EXPENSE,source_account_id='checking',destination_account_id=None,amount='500',
        initiated_at=value.end,credited_at=value.end,debited_at=value.end,settled_at=value.end)
    limited=reconstruct(value,opening=reconstruct(value.opening,cleared='180'),cash_plans=(income,expense))
    limited_result=plan_payoff(limited)
    assert limited_result.total_paid==30
    assert limited_result.liquidity.points[-1].positions[0].cleared==150
    assert compare_payoff(limited).lowest_interest_strategy is None


def test_horizon_exhaustion_and_unposted_interest_do_not_get_a_payoff_date():
    value=example();end=value.slots[0].credited_at
    value=reconstruct(value,end=end,slots=value.slots[:1],cash_plans=tuple(p for p in value.cash_plans if p.settled_at<=end),payment_target='1500')
    result=plan_payoff(value)
    assert result.status=='horizon_exhausted' and result.payoff_date is None
    assert result.remaining_posted>0
    assert compare_payoff(value).lowest_interest_strategy is None


def test_posted_zero_with_unposted_interest_is_not_paid_off():
    value=example();debt=value.debts[0];end=value.slots[0].credited_at
    value=reconstruct(value,debts=(debt,),opening=reconstruct(value.opening,cleared='5000'),cash_plans=(),
        payment_target='2000',end=end,slots=value.slots[:1])
    result=plan_payoff(value)
    assert result.remaining_posted==0 and result.remaining_unposted_interest>0
    assert result.payoff_date is None and result.status=='horizon_exhausted'


@pytest.mark.parametrize('mode',['duplicate_debt','duplicate_slot','overlap','float','precision','unsupported','transfer','cycles','naive'])
def test_invalid_or_unsupported_input_rejected(mode):
    value=example()
    with pytest.raises((ValueError,ArithmeticError)):
        if mode=='duplicate_debt':value=reconstruct(value,debts=(value.debts[0],)*2)
        if mode=='duplicate_slot':value=reconstruct(value,slots=(value.slots[0],)*2)
        if mode=='overlap':value=reconstruct(value,slots=value.slots[::-1])
        if mode=='float':value=reconstruct(value,payment_target=250.1)
        if mode=='precision':value=reconstruct(value,payment_target='250.001')
        if mode=='unsupported':
            debt=value.debts[0]
            seg=reconstruct(debt.account.segments[0],compounding_method=assumed_default(CompoundingMethod.DAILY_COMPOUNDING))
            value=reconstruct(value,debts=(reconstruct(debt,account=reconstruct(debt.account,segments=(seg,))),))
        if mode=='transfer':
            plan=reconstruct(value.cash_plans[0],kind=CashKind.TRANSFER,source_account_id='checking',destination_account_id='savings')
            value=reconstruct(value,cash_plans=(plan,))
        if mode=='cycles':value=reconstruct(value,debts=(reconstruct(value.debts[0],cycles=value.debts[0].cycles[:2]),))
        if mode=='naive':value=reconstruct(value,start=value.start.replace(tzinfo=None))
        plan_payoff(value)


def test_cli_strict_json_and_export_reproduces_result(tmp_path,capsys):
    value=example();assert parse_input(value.model_dump_json().encode())==value
    for raw in (b'{"version":true}',b'{"version":1,"version":1}',b'{"version":1,"payment_target":250.0}'):
        with pytest.raises(ValueError):parse_input(raw)
    input_file=tmp_path/'input.json';output=tmp_path/'result'
    run(['--demo','--example-input',str(input_file),'--output-dir',str(output)])
    saved=json.loads((output/'summary.json').read_text())
    run(['--input',str(input_file)])
    printed=capsys.readouterr().out
    assert saved==json.loads(printed[printed.index('{'):])
    assert 'minimum_required' in (output/'highest_interest_first.csv').read_text()
    with pytest.raises(SystemExit) as exc:run(['--demo','--output-dir',str(output)])
    assert exc.value.code==2


def test_shortage_funds_all_minimums_before_any_extra_with_stable_tie_rule():
    value=example();value=reconstruct(value,opening=reconstruct(value.opening,cleared='190'),cash_plans=())
    result=plan_payoff(value,'smallest_balance_first')
    first=result.payments[:2]
    assert [(r.account_id,r.minimum_paid,r.extra_paid) for r in first]==[('high-rate',D('25'),D('0')),('small-balance',D('15'),D('0'))]
    assert not result.all_minimums_met
    assert result.total_paid==40


def test_cash_bill_after_debt_horizon_still_protected_for_ninety_days():
    value=example();end=value.slots[0].credited_at
    bill_date=end+timedelta(days=60)
    bill=CashPlan(plan_id='future-bill',kind=CashKind.EXPENSE,amount='200',source_account_id='checking',
        initiated_at=bill_date,credited_at=bill_date,debited_at=bill_date,settled_at=bill_date)
    value=reconstruct(value,end=end,slots=value.slots[:1],cash_plans=(bill,),opening=reconstruct(value.opening,cleared='400'))
    result=plan_payoff(value)
    assert result.liquidity.end==end+timedelta(days=90)
    assert result.total_paid==50
    assert result.liquidity.points[-1].positions[0].cleared==150


def test_payoff_beyond_one_year_without_resetting_interest_or_minimums():
    from SCHEMA import BillingCycle
    from engine.minimum_forecast import PaymentSlot
    value=zero_rate(example(),balance='5000');debt=value.debts[0]
    cycles=list(debt.cycles);slots=list(value.slots)
    for month in range(1,13):
        close=date(2027,month,calendar.monthrange(2027,month)[1])
        cycles.append(BillingCycle(account_id=debt.account.account_id,cycle_id=f'2027-{month:02}',
            start_date=date(2027,month,1),end_date=close,statement_date=close,
            due_date=date(2027+(month==12),month%12+1,20)))
        at=value.slots[0].credited_at.replace(year=2027,month=month)
        slots.append(PaymentSlot(slot_id=f'2027-{month:02}',initiated_at=at,credited_at=at,debited_at=at,settled_at=at))
    value=reconstruct(value,debts=(reconstruct(debt,cycles=tuple(cycles)),),slots=tuple(slots),
        end=value.end.replace(year=2027),cash_plans=(),opening=reconstruct(value.opening,cleared='6000'))
    result=plan_payoff(value)
    assert result.payoff_date==date(2027,8,20)
    assert result.total_paid==5000 and result.posted_interest==0
    assert result.all_minimums_met and result.status=='paid_off'
