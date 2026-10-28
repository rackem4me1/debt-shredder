from decimal import Decimal, localcontext
import pytest
from dashboard.strategies import strategy_example, strategy_variants, strategy_results, render_strategies
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.scenarios import save_scenario
from engine.common import reconstruct
from test_multi_manual import scenario, card
from test_dashboard_manual import web,call


def test_same_budget_scope_and_cash_conservation():
    original=strategy_example();raw=original.model_dump_json()
    variants=strategy_variants(original)
    for _,s in variants:
        assert sum(r.amount for r in s.requests)==400
        assert (s.debts,s.openings,s.cash_plans,s.start,s.end)==(original.debts,original.openings,original.cash_plans,original.start,original.end)
    rows=strategy_results(original)
    assert [r['paid'] for r in rows]==[{'card':70,'card-2':50},{'card':70,'card-2':50},{'card':50,'card-2':70}]
    assert all(r['cash']==30 and r['total_paid']==120 and not r['missed'] for r in rows)
    assert rows[2]['interest']>rows[1]['interest']
    assert original.model_dump_json()==raw


def test_highest_rate_on_second_card_receives_extra_first():
    original=scenario(card(apr_percent='60'),apr_percent='12')
    rows=strategy_results(original)
    assert rows[0]['paid']=={'card':70,'card-2':50}
    assert rows[1]['paid']=={'card':50,'card-2':70}


def test_insufficient_cash_keeps_shortfalls_visible():
    original=scenario(card(),cash='100')
    rows=strategy_results(original)
    assert all(r['total_paid']==70 for r in rows)
    assert all(r['missed']==('card-2',) for r in rows)
    assert 'card-2' in render_strategies(original)


@pytest.mark.parametrize('original',[
    scenario(), scenario(card(payment_amount='0')),
    scenario(card(credited='2026-01-04')),
    scenario(card(payment_amount='20'),payment_amount='20'),
    scenario(card(),payment_amount='900'),
])
def test_unsupported_comparisons_explain_without_mutation(original):
    before=original.model_dump_json()
    with pytest.raises(ValueError):strategy_variants(original)
    assert 'needs a change first' in render_strategies(original)
    assert original.model_dump_json()==before


def test_equal_rates_and_balances_have_stable_ties():
    rows=strategy_results(scenario(card()))
    assert rows[0]['paid']==rows[1]['paid']==rows[2]['paid']


def test_budget_equal_to_minimums_has_no_extras():
    rows=strategy_results(scenario(card(payment_amount='50'),payment_amount='50'))
    assert all(r['total_requested']==100 and r['paid']=={'card':50,'card-2':50} for r in rows)


def test_three_cards_and_scheduled_cash_preserved():
    original=scenario(card(balance='200'),card(balance='150'),payment_amount='100',
        cash_events=({'kind':'income','label':'Pay','amount':'100','date':'2026-01-01','cadence':'weekly'},))
    for _,candidate in strategy_variants(original):
        assert candidate.cash_plans==original.cash_plans
        assert candidate.manual_cash_schedules==original.manual_cash_schedules
        assert sum(r.amount for r in candidate.requests)==500


def test_decimal_context_independence_and_escaped_labels():
    original=scenario(card(card_name='<Travel>'),card_name='<Everyday>')
    expected=strategy_results(original)
    with localcontext() as context:
        context.prec=6
        actual=strategy_results(original)
    assert actual==expected
    html=render_strategies(original)
    assert '&lt;Travel&gt;' in html and '<Travel>' not in html
    assert 'not an entire debt payoff' in html


def test_http_comparison_is_read_only_and_linked(web):
    id_='a'*32;path=web[1]/(id_+'.json')
    save_scenario(strategy_example(),path);before=path.read_bytes()
    status,_,html=call(web,'GET','/strategies/'+id_)
    assert status==200 and 'Highest interest first' in html and 'Smallest balance first' in html
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==1
    assert '/strategies/'+id_ in call(web,'GET','/scenario/'+id_)[2]
    assert call(web,'GET','/strategies/'+'b'*32)[0]==404
    assert call(web,'GET','/strategies/../../SCHEMA.py')[0]==404


def test_example_route_never_saves(web):
    status,_,html=call(web,'GET','/strategies-example')
    assert status==200 and 'Practice data' in html and '$70.00' in html
    assert not list(web[1].glob('*.json'))
