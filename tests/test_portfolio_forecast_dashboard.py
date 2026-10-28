from decimal import Decimal as D
from dashboard.portfolio_forecast import practice_forecast, render_example
from test_dashboard_manual import web, call


def test_example_reconciles_one_cash_balance_with_bill():
    _,opening,r=practice_forecast()
    paid=sum(d.accepted for d in r.decisions)
    assert paid==D('206.96')
    assert r.liquidity.points[-1].positions[0].cleared==opening.cleared-D('50')-paid==D('143.04')
    assert all(not d.missed_due_dates for d in r.debts)


def test_shortage_preserves_bill_floor_reserve_and_reports_missed_dates():
    _,_,r=practice_forecast(True)
    assert sum(d.accepted for d in r.decisions)==30
    assert r.liquidity.points[-1].positions[0].cleared==120
    assert all(d.missed_due_dates for d in r.debts)
    assert r.decisions[1].unmet==20


def test_view_separates_request_shortfalls_from_debt_and_exposes_scope():
    html=render_example()
    for expected in ('Synthetic practice data','not a separate debt balance','No income is assumed',
                     '2026-06-18','no extra payments or full payoff date','Overlapping payment lifecycles',
                     '$143.04','$120.00','software has not selected an optimal priority'):
        assert expected in html


def test_forecast_route_is_readonly_and_linked(web):
    before = set(web[1].iterdir())
    status,_,html=call(web,'GET','/portfolio-forecast-example')
    assert status==200
    assert 'Two cards. One cash balance.' in html
    assert 'When cash is short' in html
    status,_,home=call(web,'GET','/')
    assert '/portfolio-forecast-example' in home
    assert set(web[1].iterdir()) == before
