from dashboard.simple_view import saved_plan,walkthrough
from dashboard.strategies import strategy_example
from dashboard.scenarios import save_scenario
from engine.common import reconstruct
from test_dashboard_manual import web,call


def test_walkthrough_reflects_funded_and_shortage_engine_results():
    funded=walkthrough();short=walkthrough(True)
    assert '$206.96' in funded and '$143.04' in funded and '$1,970.66' in funded
    assert '$30.00' in short and '$120.00' in short and '$2,153.27' in short
    assert 'Some minimum due dates will be missed' in short
    assert 'Both cards’ minimum payments fit' not in short
    assert 'Sample money' in funded and 'No new income is assumed' in funded


def test_saved_summary_preserves_missing_payments_warning_and_escapes():
    s=reconstruct(strategy_example(),requests=(),name='<script>bad</script>')
    html=saved_plan(s,'a'*32)
    assert 'This plan has no payment requests' in html
    assert 'misses a minimum-payment due date' in html
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Cash stays attached to each account' in html


def test_home_and_simple_plan_are_readonly_and_linked(web):
    s=strategy_example();id_='a'*32;path=web[1]/(id_+'.json');save_scenario(s,path);before=path.read_bytes()
    status,_,home=call(web,'GET','/')
    assert status==200 and 'Show me how it works' in home and '/plan/'+id_ in home
    for route in ('/walkthrough','/walkthrough-shortage','/plan/'+id_):
        status,_,html=call(web,'GET',route)
        assert status==200 and 'Debt Shredder' in html
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==1
    assert call(web,'GET','/plan/'+'b'*32)[0]==404
