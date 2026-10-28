from decimal import Decimal as D, localcontext
from datetime import timedelta
import pytest
from dashboard.multimonth import example
from engine.common import reconstruct
from engine.minimum_forecast import MinimumTerms, PaymentSlot, forecast_minimums
from engine.portfolio_minimum_forecast import CardMinimumSchedule, forecast_portfolio_minimums
from engine.liquidity import CashPlan, CashKind


def fixture():
    s = example()
    a = s.debts[0]
    b = reconstruct(a, account=reconstruct(a.account, account_id='card-b',
        segments=tuple(reconstruct(v, account_id='card-b') for v in a.account.segments),
        allocation_rule=reconstruct(a.account.allocation_rule, account_id='card-b')),
        cycles=tuple(reconstruct(c, account_id='card-b') for c in a.cycles),
        initial_minimum=reconstruct(a.initial_minimum, account_id='card-b'))
    schedules = tuple(CardMinimumSchedule(debt=debt, terms=MinimumTerms(floor='25', rate='.01'), priority=i,
        slots=tuple(PaymentSlot(slot_id=f'{i}-{r.request_id}', **{k:getattr(r,k) for k in
        ('initiated_at','credited_at','debited_at','settled_at')}) for r in s.requests)) for i,debt in enumerate((a,b)))
    return s, schedules


def run(s, schedules):
    return forecast_portfolio_minimums(schedules, s.openings[0], s.cash_plans, s.start, s.end)


def test_two_cards_independent_statement_math_shared_cash_once():
    s, schedules = fixture(); r = run(s, schedules)
    assert [d.accepted for d in r.decisions] == list(map(D, ['25','25','40.76','40.76','37.72','37.72']))
    assert [d.account.total_balance() for d in r.debts] == [D('985.33')]*2
    assert r.liquidity.points[-1].positions[0].cleared == D('193.04')
    assert all(not d.missed_due_dates for d in r.debts)
    assert sum(p.amount for d in r.debts for p in d.payments) == D('206.96')


def test_priority_under_shortage_is_explicit_not_input_tuple_order():
    s, schedules = fixture(); s = reconstruct(s, openings=(reconstruct(s.openings[0], cleared='130'),))
    r = run(s, schedules)
    assert [d.accepted for d in r.decisions[:2]] == [D('25'),D('5')]
    assert r.liquidity.points[-1].positions[0].cleared == 100
    assert r.debts[1].missed_due_dates
    reversed_result = run(s, schedules[::-1])
    assert reversed_result.decisions == r.decisions
    assert reversed_result.liquidity == r.liquidity


def test_future_income_cannot_pay_earlier_slots():
    s, schedules = fixture(); at = schedules[0].slots[0].credited_at + timedelta(days=1)
    plan = CashPlan(plan_id='paycheck', kind=CashKind.INCOME, amount='200', destination_account_id='checking',
        initiated_at=at, credited_at=at, debited_at=at, settled_at=at)
    s = reconstruct(s, openings=(reconstruct(s.openings[0], cleared='100'),), cash_plans=(plan,))
    r = run(s, schedules)
    assert [d.accepted for d in r.decisions[:2]] == [0,0]
    assert all(d.accepted > 0 for d in r.decisions[2:])
    assert all(d.missed_due_dates for d in r.debts)


def test_future_bill_and_reserve_are_shared_protections():
    s, schedules = fixture(); at=s.end
    plan=CashPlan(plan_id='bill',kind=CashKind.EXPENSE,amount='250',source_account_id='checking',
        initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    s=reconstruct(s,openings=(reconstruct(s.openings[0],reserved='30'),),cash_plans=(plan,))
    r=run(s,schedules)
    assert [d.accepted for d in r.decisions] == [20,0,0,0,0,0]
    assert r.liquidity.points[-1].positions[0].cleared == 130


def test_one_card_matches_existing_forecast_and_low_precision_is_safe():
    s,schedules=fixture(); a=schedules[0]
    previous=forecast_minimums(a.debt,s.openings[0],s.cash_plans,a.slots,s.start,s.end,a.terms)
    r=run(s,(a,))
    assert r.debts == (previous.debt,)
    assert r.decisions == previous.decisions
    assert r.liquidity == previous.liquidity
    with localcontext() as context:
        context.prec=6
        assert run(s,(a,)) == r


@pytest.mark.parametrize('mode',['duplicate_account','duplicate_slot','priority_tie','overlap','terms','empty'])
def test_ambiguous_or_unsupported_inputs_rejected(mode):
    s,schedules=fixture(); a,b=schedules
    if mode=='duplicate_account': schedules=(a,a)
    if mode=='duplicate_slot': schedules=(a,reconstruct(b,slots=a.slots))
    if mode=='priority_tie': schedules=(a,reconstruct(b,priority=a.priority))
    if mode=='overlap':
        slot=reconstruct(a.slots[0],settled_at=a.slots[0].settled_at+timedelta(days=1))
        schedules=(reconstruct(a,slots=(slot,)+a.slots[1:]),b)
    if mode=='terms': schedules=(reconstruct(a,terms=MinimumTerms(floor='26',rate='.01')),b)
    if mode=='empty': schedules=()
    with pytest.raises(ValueError): run(s,schedules)


def test_later_interest_can_be_paid_beyond_each_opening_balance():
    s,schedules=fixture()
    schedules=tuple(reconstruct(a,debt=reconstruct(a.debt,initial_minimum=reconstruct(
        a.debt.initial_minimum,statement_minimum_original='1000',statement_minimum_remaining='1000')))
        for a in schedules)
    s=reconstruct(s,openings=(reconstruct(s.openings[0],cleared='5000'),))
    r=run(s,schedules)
    assert [d.accepted for d in r.decisions] == list(map(D,['1000','1000','19','19','.36','.36']))
    assert r.liquidity.points[-1].positions[0].cleared == D('2961.28')


def test_zero_minimum_slot_does_not_create_zero_amount_request():
    s,schedules=fixture(); a=schedules[0]
    a=reconstruct(a,debt=reconstruct(a.debt,initial_minimum=reconstruct(
        a.debt.initial_minimum,statement_minimum_original='0',statement_minimum_remaining='0')))
    r=run(s,(a,))
    assert len(r.requests)==2
    assert a.slots[0].slot_id not in {v.request_id for v in r.requests}
    assert len(r.debts[0].checkpoint.credit_events)==3
