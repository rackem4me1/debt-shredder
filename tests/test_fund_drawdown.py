from datetime import datetime,timedelta,timezone
from decimal import Decimal as D,localcontext
import pytest
from dashboard import weekly_check as check
from test_weekly_check import example
from engine.liquidity import CashOpening,CashPlan,CashKind,project_liquidity
from SCHEMA import CashFlowStatus


def test_back_transfer_is_one_time_cash_support_not_recurring_pay():
    value=example();before=value.model_dump_json();base=check.calculate(value)
    r=check.calculate(value,'back=20')
    assert r['rows']==base['rows'] and r['current_total']==r['tested_total']==350
    assert r['balance_after']==60 and r['goal_end']==420 and r['goal_rate']==D('11.67')
    assert [row[2] for row in r['supported_rows']]==[70,0,-30]
    assert [row[2]-row[1] for row in r['supported_rows']]==[20,20,20]
    assert value.model_dump_json()==before and value.goal.weekly==30


def test_direct_spending_and_checking_transfer_have_different_cash_effects():
    value=example()
    r=check.calculate(value,'back=20&spend=10')
    assert r['balance_after']==50 and r['goal_rate']==D('12.50') and r['goal_end']==410
    spending_only=check.calculate(value,'spend=30')
    assert spending_only['goal_end']==r['goal_end']
    assert all(after==before for _,before,after in spending_only['supported_rows'])
    assert all(after-before==20 for _,before,after in r['supported_rows'])
    assert r['tested_total']==spending_only['tested_total']


@pytest.mark.parametrize('query',['back=81','spend=81','back=50&spend=31','back=-1','spend=0.001','weeks=0','weeks=521','weeks=True','weeks=2.5','weeks=','back=1&back=2','pool=1&rent=1&bills=1&back=1&spend=1&weeks=2&extra=0'])
def test_invalid_or_unfunded_trial_cannot_spend_future_deposits(query):
    with pytest.raises(ValueError):check.calculate(example(),query)


def test_withdrawal_and_fewer_remaining_contributions_recalculate_goal_gap():
    r=check.calculate(example(),'back=20&weeks=6&pool=20')
    assert r['opportunities']==6 and r['goal_rate']==D('23.34')
    assert r['goal_end']==180 and r['goal_shortfall']==20
    assert r['tested_total']==340
    assert check.calculate(example(),'back=80')['balance_after']==0
    assert check.calculate(example(),'back=80')['goal_rate']==D('16.67')


def test_drawdown_display_is_context_safe_and_explains_one_time_assumption():
    value=example();query='back=20&spend=10&weeks=6'
    expected=check.calculate(value,query)
    with localcontext() as context:
        context.prec=3
        assert check.calculate(value,query)==expected
    html=check.render(value,query)
    assert 'not new income' in html and 'not repeated in later weeks' in html
    assert 'Balance after those one-time withdrawals: $50.00' in html
    assert 'The tested automatic contribution stays $30.00/week' in html
    assert 'after support for this week' in html.lower()


def test_existing_ledger_transfer_conservation_and_settlement_gate_support():
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    openings=(CashOpening(account_id='checking',cleared='0',floor='0',primary=True),CashOpening(account_id='fund',cleared='80',reserved='60',floor='0'))
    transfer=CashPlan(plan_id='support',kind=CashKind.TRANSFER,amount='20',source_account_id='fund',destination_account_id='checking',initiated_at=start,debited_at=start,credited_at=start+timedelta(days=1),settled_at=start+timedelta(days=2))
    plain=project_liquidity(openings,(transfer,),start,end_at=start+timedelta(days=3))
    assert plain.external_income==plain.external_outflows==0
    assert all(point.aggregate_cash==80 for point in plain.points)
    def spend(at):return CashPlan(plan_id='bill',kind=CashKind.EXPENSE,amount='20',source_account_id='checking',initiated_at=at,debited_at=at,credited_at=at,settled_at=at)
    early=project_liquidity(openings,(transfer,spend(start+timedelta(days=1,hours=1))),start,end_at=start+timedelta(days=3))
    late=project_liquidity(openings,(transfer,spend(start+timedelta(days=2,hours=1))),start,end_at=start+timedelta(days=3))
    assert early.status!=CashFlowStatus.HEALTHY and late.status==CashFlowStatus.HEALTHY
    assert early.external_income==late.external_income==0
    assert early.external_outflows==late.external_outflows==20
    assert all(next(p for p in point.positions if p.account_id=='fund').reserved==60 for point in late.points)


def test_scenario_sweep_conserves_fund_money_and_goal_rate_is_minimal():
    value=example()
    for weeks in (1,6,12):
        for back in ('0','17.13','40'):
            for spending in ('0','12.56','40'):
                if D(back)+D(spending)>value.goal.balance:continue
                for weekly in ('0','5.33','30'):
                    r=check.calculate(value,f'weeks={weeks}&back={back}&spend={spending}&pool={weekly}')
                    # Transfer-back and direct spending must explain every change
                    # in the fund; neither can silently multiply by future weeks.
                    assert r['goal_end']+D(back)+D(spending)==value.goal.balance+D(weekly)*weeks
                    required_cents=max(0,20000-int(r['balance_after']*100))
                    expected_rate_cents=(required_cents+weeks-1)//weeks
                    assert int(r['goal_rate']*100)==expected_rate_cents
                    assert r['balance_after']+r['goal_rate']*weeks>=value.goal.target
                    if r['goal_rate']:
                        assert r['balance_after']+(r['goal_rate']-D('.01'))*weeks<value.goal.target
