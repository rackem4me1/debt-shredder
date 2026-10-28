from datetime import date
from decimal import Decimal as D
import pytest
from dashboard.multimonth import example,statement_rows
from engine.common import reconstruct
from engine.simulation import simulate_revolving,resume_revolving,DebtCheckpoint
from test_dashboard_manual import web,call


def replay(end,payments):
    debt=example().debts[0]
    return simulate_revolving(debt.account,date(2026,1,1),end,debt.cycles,debt.initial_minimum,
        tuple(d for d in payments if d<=end),lambda day,*args:payments[day])


def test_independent_three_statement_arithmetic():
    # Daily rate .001. Jan: 19*1 + 12*.9 = 29.80; ending 929.80.
    # Feb: 19*.9298 + 9*.8298 = 25.1344 ->25.13; ending 854.93.
    # Mar: 19*.85493 +12*.75493 =25.30283 ->25.30; ending780.23.
    # Minimum: max(25, interest + 1% of posted balance), rounded cents.
    rows,projection=statement_rows(example())
    assert [(r['interest'],r['balance'],r['minimum']) for r in rows]==[
        (D('29.80'),D('929.80'),D('39.10')),(D('25.13'),D('854.93'),D('33.68')),
        (D('25.30'),D('780.23'),D('33.10'))]
    assert sum(r['paid'] for r in rows)==300
    assert projection.liquidity.points[-1].positions[0].cleared==100
    assert projection.missed_minimum_account_ids==()
    assert rows[-1]['due']==date(2026,4,20)


@pytest.mark.parametrize('cut',[date(2026,1,20),date(2026,1,31),date(2026,2,20),date(2026,2,28)])
def test_restart_matches_three_cycle_continuous_replay(cut):
    payments={date(2026,m,20):D('100') for m in (1,2,3)}
    first=replay(cut,payments)
    cp=DebtCheckpoint.model_validate_json(first.checkpoint.model_dump_json())
    resumed=resume_revolving(cp,date(2026,3,31),tuple(d for d in payments if d>cut),lambda day,*args:payments[day])
    assert resumed==replay(date(2026,3,31),payments)
    assert len([a for a in resumed.audit if a.kind=='interest_posting'])==3


def test_statement_day_credit_precedes_interest_and_posting():
    result=replay(date(2026,1,31),{date(2026,1,31):D('100')})
    assert result.account.total_balance()==D('930.90') #30*1+.9 interest
    assert result.missed_due_dates==(date(2026,1,20),)


def test_posted_balance_payoff_leaves_residual_interest():
    result=replay(date(2026,1,31),{date(2026,1,20):D('1000')})
    assert result.account.total_balance()==19 # 19 days interest before payoff
    assert result.minimum_remaining==19


def test_cash_shortfall_does_not_rebudget_statement_prefix():
    rows,p=statement_rows(example('150'))
    assert [r['paid'] for r in rows]==[150,150,0]
    assert p.missed_minimum_account_ids==('card-a',)
    assert p.liquidity.points[-1].positions[0].cleared==100


def test_multimonth_example_readonly(web):
    status,_,html=call(web,'GET','/multimonth-example')
    assert status==200 and '$780.23' in html and 'April 20' in html
    assert 'does not generate future payments automatically' in html
    assert not list(web[1].glob('*.json'))
