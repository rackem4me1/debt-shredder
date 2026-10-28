from decimal import Decimal as D
import pytest
from demo_payoff import example
from dashboard import payoff_view
from dashboard.scenarios import Scenario,save_scenario
from dashboard.strategies import strategy_fingerprint
from engine.common import reconstruct
from engine.payoff import compare_payoff
from engine.portfolio import PortfolioPaymentRequest,RequestKind
from SCHEMA import GracePeriodState
from test_dashboard_manual import web,call
from test_restore import hidden,post


def source_scenario():
    value=example();requests=[]
    for slot in value.slots:
        for i,debt in enumerate(value.debts):
            requests.append(PortfolioPaymentRequest(request_id=slot.slot_id+'-'+str(i),
                debt_account_id=debt.account.account_id,source_account_id='checking',amount='125',
                kind=RequestKind.EXTRA,priority=i,**{k:getattr(slot,k) for k in
                ('initiated_at','credited_at','debited_at','settled_at')}))
    return Scenario(name='Payoff practice: $1,500',origin='synthetic_demo',start=value.start,end=value.end,
        debts=value.debts,openings=(value.opening,),cash_plans=value.cash_plans,requests=tuple(requests),
        card_names=('24% sample card','12% sample card'))


def test_adapter_preserves_terms_cash_and_dates_without_original_payment_amounts():
    source=source_scenario();before=source.model_dump_json()
    adapted=payoff_view.inputs_from_scenario(source,'250')
    assert adapted.debts==source.debts and adapted.opening==source.openings[0]
    assert adapted.cash_plans==source.cash_plans
    assert len(adapted.slots)==12 and adapted.payment_target==250
    result=compare_payoff(adapted);direct=compare_payoff(example())
    for actual,expected in zip(result.results,direct.results):
        assert (actual.total_paid,actual.posted_interest,actual.payoff_date,actual.all_minimums_met)==(
            expected.total_paid,expected.posted_interest,expected.payoff_date,expected.all_minimums_met)
        assert actual.liquidity.external_outflows==expected.liquidity.external_outflows
    assert source.model_dump_json()==before


def test_result_shows_complete_schedule_and_principal_plus_unposted_checks():
    source=source_scenario();html=payoff_view.calculate_section(source,'250')
    assert 'August 31, 2026' in html and 'September 30, 2026' in html
    assert '$74.18' in html and '$93.43' in html
    assert '24% sample card' in html and '12% sample card' in html
    assert '2026-08-20T00:00:00+00:00' in html
    assert 'Interest not yet posted' in html and 'No money moved' in html
    assert 'Minimum required' in html and 'Minimum paid' in html


@pytest.mark.parametrize('mode',['no_dates','different_timing','overlap','grace'])
def test_unsupported_source_is_explained_without_guessed_terms(mode):
    source=source_scenario()
    if mode=='savings':source=reconstruct(source,openings=source.openings+(reconstruct(source.openings[0],account_id='savings',primary=False),))
    if mode=='no_dates':source=reconstruct(source,requests=())
    if mode=='different_timing':
        from datetime import timedelta
        request=reconstruct(source.requests[1],settled_at=source.requests[1].settled_at+timedelta(hours=1))
        source=reconstruct(source,requests=(source.requests[0],request)+source.requests[2:])
    if mode=='overlap':
        from datetime import timedelta
        request=reconstruct(source.requests[1],initiated_at=source.requests[1].initiated_at+timedelta(hours=1),
            credited_at=source.requests[1].credited_at+timedelta(hours=1),debited_at=source.requests[1].debited_at+timedelta(hours=1),settled_at=source.requests[1].settled_at+timedelta(hours=1))
        source=reconstruct(source,requests=(source.requests[0],request)+source.requests[2:])
    if mode=='grace':
        debt=source.debts[0];source=reconstruct(source,debts=(reconstruct(debt,account=reconstruct(debt.account,current_grace_state=GracePeriodState.PENDING)),)+source.debts[1:])
    with pytest.raises(ValueError):payoff_view.inputs_from_scenario(source,'250')
    html=payoff_view.form_section(source,'a'*32,'token')
    assert 'No payoff date has been guessed' in html and 'type="number"' not in html


def test_unfinished_preview_has_no_winner_or_false_payoff_date():
    html=payoff_view.calculate_section(source_scenario(),'0')
    assert 'No winning plan is claimed' in html
    assert 'Not reached within supplied dates' in html
    assert 'Minimum payment missed or underfunded' in html
    assert '2026-01-20' in html


def test_http_payoff_preview_preserves_source_and_does_not_create_files(web):
    source=source_scenario();id_='c'*32;path=web[1]/(id_+'.json');save_scenario(source,path)
    before=path.read_bytes();files=set(web[1].iterdir())
    status,_,html=call(web,'GET','/plan/'+id_)
    assert status==200 and 'Calculate both payoff plans' in html
    fields=hidden(html)|{'payment_target':'250'}
    status,headers,html=post(web,'/payoff-preview/'+id_,fields)
    assert status==200 and 'August 31, 2026' in html and '$74.18' in html
    assert headers['Cache-Control']=='no-store'
    assert path.read_bytes()==before and set(web[1].iterdir())==files
    assert post(web,'/payoff-preview/'+id_,fields|{'payment_target':'250.001'})[0]==422
    assert post(web,'/payoff-preview/'+id_,fields|{'payment_target':'NaN'})[0]==422
    status,_,bad=post(web,'/payoff-preview/'+id_,fields|{'payment_target':'<script>bad</script>'})
    assert status==422 and '<script>' not in bad and '&lt;script&gt;bad' in bad
    assert post(web,'/payoff-preview/'+id_,fields|{'extra':'field'})[0]==400
    assert post(web,'/payoff-preview/'+id_,fields|{'token':'bad'})[0]==403
    assert post(web,'/payoff-preview/'+id_,fields,{'Origin':'https://outside.example'})[0]==403
    save_scenario(reconstruct(source,name='Changed'),path,overwrite=True)
    assert post(web,'/payoff-preview/'+id_,fields)[0]==409
    assert post(web,'/payoff-preview/'+'d'*32,fields)[0]==404
    assert call(web,'GET','/payoff-preview/'+id_)[0]==404


def test_http_short_plan_remains_unfinished(web):
    from dashboard.multimonth import example as short_example
    source=short_example();id_='e'*32;save_scenario(source,web[1]/(id_+'.json'))
    fields=hidden(call(web,'GET','/plan/'+id_)[2])|{'payment_target':'100'}
    status,_,html=post(web,'/payoff-preview/'+id_,fields)
    assert status==200 and 'Not reached within supplied dates' in html
    assert 'No winning plan is claimed' in html


def test_cli_modules_and_entrypoint_are_packaged():
    from pathlib import Path
    import tomllib
    data=tomllib.loads(Path('pyproject.toml').read_text())
    assert {'payoff_cli','demo_payoff'}<=set(data['tool']['setuptools']['py-modules'])
    assert data['project']['scripts']['debt-shredder-payoff']=='payoff_cli:run'
