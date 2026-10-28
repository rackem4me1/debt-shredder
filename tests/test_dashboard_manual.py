from decimal import Decimal as D
from http.client import HTTPConnection
import re
from threading import Thread
from urllib.parse import urlencode
import pytest
from dashboard.manual import ManualScenario
from dashboard.server import make_server
from dashboard.scenarios import load_scenario
from SCHEMA import ProvenanceSource


def fields():
    return dict(name='My test',cash='150',floor='20',reserved='10',balance='500',unposted_interest='0',
        apr_percent='36.5',day_count='actual_365_fixed',start='2026-01-01',end='2026-01-21',
        previous_start='2025-12-01',previous_close='2025-12-31',minimum_due='2026-01-20',
        next_close='2026-01-31',next_due='2026-02-20',minimum_original='50',minimum_remaining='50',
        payment_amount='200',payment_kind='minimum',initiated='2026-01-02',credited='2026-01-03',
        debited='2026-01-04',settled='2026-01-05',timezone='America/Chicago',scope='confirmed')


def test_manual_decimal_rate_and_exact_engine_result():
    scenario=ManualScenario(**fields()).scenario()
    segment=scenario.debts[0].account.segments[0]
    assert segment.apr.value==D('.365')
    assert segment.apr.provenance==ProvenanceSource.USER_PROVIDED_ESTIMATE
    assert scenario.origin=='manual'
    result=scenario.project()
    assert result.decisions[0].accepted==120
    assert result.liquidity.points[-1].positions[0].cleared==30
    assert result.debt_projections[0].account.total_balance()==380
    assert result.debt_projections[0].account.segments[0].accrued_unposted_interest==D('8.22')
    assert not result.missed_minimum_account_ids


@pytest.mark.parametrize('updates',[
    {'scope':''},{'day_count':'30_360_nasd'},{'end':'2026-01-31'},
    {'minimum_remaining':'501'},{'debited':'2026-01-02'},
    {'timezone':'Not/AZone'},{'cash':150.0},{'payment_amount':'0.001'},
    {'apr_percent':'NaN'},{'unposted_interest':'-1'},
    {'minimum_due':'2025-12-31'}, {'start':'2026-01-21'},
])
def test_manual_rejects_unsupported_or_invalid_inputs(updates):
    with pytest.raises(ValueError):ManualScenario(**(fields()|updates)).scenario()


def test_zero_request_does_not_hide_missed_due():
    result=ManualScenario(**(fields()|{'payment_amount':'0'})).scenario().project()
    assert result.decisions==()
    assert result.missed_minimum_account_ids==('card',)


@pytest.fixture
def web(tmp_path):
    server=make_server(tmp_path,0)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    yield server.server_port,tmp_path
    server.shutdown();thread.join();server.server_close()


def call(web,method,path,body=None,headers=None):
    port,_=web
    connection=HTTPConnection('127.0.0.1',port,timeout=5)
    connection.request(method,path,body=body,headers=headers or {})
    response=connection.getresponse()
    result=(response.status,dict(response.getheaders()),response.read().decode())
    connection.close()
    return result


def token(web):
    status,headers,body=call(web,'GET','/new')
    assert status==200
    assert 'frame-ancestors' in headers['Content-Security-Policy']
    return re.search(r'name="token" value="([^"]+)"',body)[1]


def post(web,values,**extra):
    return call(web,'POST','/create',urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'}|extra)


def test_http_flow_saves_and_reopens_without_overwrite(web):
    values=fields()|{'token':token(web)}
    status,headers,_=post(web,values)
    assert status==303
    url=headers['Location']
    status,_,html=call(web,'GET',url)
    assert status==200 and 'Manually entered scenario' in html and '$120.00' in html
    saved=next(web[1].glob('*.json'))
    assert load_scenario(saved).name=='My test'
    status,headers,_=post(web,values)
    assert status==303 and headers['Location']!=url
    assert len(list(web[1].glob('*.json')))==2
    assert 'My test' in call(web,'GET','/')[2]


def test_invalid_form_preserves_inputs_without_saving(web):
    status,_,html=post(web,fields()|{'token':token(web),'end':'2026-02-01'})
    assert status==422 and 'My test' in html and 'before the next close' in html
    assert not list(web[1].glob('*.json'))


def test_cross_site_and_host_checks_block_writes(web):
    valid=fields()|{'token':token(web)}
    assert post(web,valid,Origin='https://example.org')[0]==403
    assert post(web,valid|{'token':'wrong'})[0]==403
    assert post(web,valid|{'token':'é'})[0]==403
    assert call(web,'GET','/',headers={'Host':'evil.example'})[0]==403
    assert not list(web[1].glob('*.json'))


def test_demo_is_read_only_and_paths_are_bounded(web):
    assert 'Synthetic example' in call(web,'GET','/demo')[2]
    assert call(web,'GET','/scenario/../../SCHEMA.py')[0]==404
    assert not list(web[1].glob('*.json'))


def test_edit_roundtrip_and_original_preserved(web):
    from dashboard.manual import editable_inputs
    original=ManualScenario(**fields()).scenario()
    assert ManualScenario(**editable_inputs(original)).scenario()==original
    _,headers,_=post(web,fields()|{'token':token(web)})
    id_=headers['Location'].split('/')[-1]
    file=web[1]/(id_+'.json')
    before=file.read_bytes()
    status,_,html=call(web,'GET','/edit/'+id_)
    assert status==200 and 'value="200"' in html and 'My test (copy)' in html
    assert 'Adjust a copy' in call(web,'GET',headers['Location'])[2]
    values=editable_inputs(original)|{'payment_amount':'80','name':'Smaller payment','token':token(web)}
    status,headers,_=post(web,values)
    assert status==303 and file.read_bytes()==before
    assert '$80.00' in call(web,'GET',headers['Location'])[2]


def test_edit_rejects_lossy_conversion():
    from dashboard.manual import editable_inputs
    from engine.common import reconstruct
    original=ManualScenario(**fields()).scenario()
    changed=reconstruct(original,openings=(reconstruct(original.openings[0],held='1'),))
    with pytest.raises(ValueError,match='cannot preserve'):editable_inputs(changed)
    zero=ManualScenario(**(fields()|{'payment_amount':'0'})).scenario()
    assert ManualScenario(**editable_inputs(zero)).scenario()==zero


def test_idle_browser_connection_does_not_block_other_requests(web):
    import socket
    with socket.create_connection(('127.0.0.1',web[0]),timeout=2):
        assert call(web,'GET','/')[0]==200


def test_launcher_uses_free_loopback_port_and_stable_storage(monkeypatch,tmp_path):
    from dashboard import launcher
    seen={}
    class Server:
        server_port=12345
        def serve_forever(self):seen['served']=True;raise KeyboardInterrupt()
        def server_close(self):seen['closed']=True
    def factory(path,port):
        seen.update(path=path,port=port)
        return Server()
    monkeypatch.setattr(launcher,'make_server',factory)
    monkeypatch.setattr(launcher.webbrowser,'open',lambda url:seen.update(url=url))
    monkeypatch.chdir(tmp_path)
    launcher.main()
    assert seen['port']==0 and seen['path'].name=='local_scenarios' and seen['path'].is_absolute()
    assert seen['url']=='http://127.0.0.1:12345' and seen['served'] and seen['closed']
