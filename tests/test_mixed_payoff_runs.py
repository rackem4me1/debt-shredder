import json,re
from html import unescape
from urllib.parse import urlencode
import pytest
from demo_payoff import mixed_example
from engine.common import reconstruct
from engine.mixed_payoff import compare_mixed_payoff
from dashboard import mixed_payoff_runs as store
from payoff_cli import parse_mixed_input,mixed_summary
from test_dashboard_manual import web,call,token


def hidden(html):return {k:unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}


def post(web,path,values,**headers):
    return call(web,'POST',path,urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'}|headers)


def test_immutable_runs_round_trip_and_distinct_saves(tmp_path):
    run=store.MixedPayoffRun(name='Sample',origin='synthetic_demo',inputs=mixed_example())
    a=store.save(tmp_path,run);original=(tmp_path/'mixed_payoff_runs'/(a+'.json')).read_bytes()
    b=store.save(tmp_path,reconstruct(run,name='Other',inputs=reconstruct(run.inputs,payment_target='200')))
    assert a!=b and store.load(tmp_path,a)==run
    assert (tmp_path/'mixed_payoff_runs'/(a+'.json')).read_bytes()==original
    assert 'Sample accounts' in store.library(tmp_path)
    with pytest.raises(ValueError):store.load(tmp_path,'../money_snapshot')


@pytest.mark.parametrize('mode',['float','duplicate','version','format','blank','bad_zone','unsupported'])
def test_import_rejects_invalid_or_unsupported_inputs(mode):
    value=mixed_example().model_dump(mode='json');name='My calculation'
    if mode=='float':value['payment_target']=300.1
    if mode=='version':value['version']=True
    if mode=='format':value['format']='wrong'
    if mode=='blank':name='  '
    if mode=='bad_zone':value['loans'][0]['timezone_name']='Not/AZone'
    if mode=='unsupported':value['loans'][0]['loan']['prepayment_behavior']['value']='paid_ahead'
    raw=json.dumps(value).encode()
    if mode=='duplicate':raw=raw.replace(b'"payment_target": "300"',b'"payment_target": "300", "payment_target": "301"')
    with pytest.raises(ValueError):store.review(name,raw)


def test_sample_save_signature_and_reopen_exports_are_exact(web):
    status,_,html=call(web,'GET','/mixed-payoff-example?target=300')
    assert status==200
    values=hidden(html)
    assert post(web,'/mixed-payoff/save',values|{'signature':'wrong'})[0]==409
    assert post(web,'/mixed-payoff/save',values|{'payload':values['payload'].replace('300','301',1)})[0]==409
    assert not list((web[1]/'mixed_payoff_runs').glob('*.json'))
    status,headers,_=post(web,'/mixed-payoff/save',values)
    assert status==303 and headers['Cache-Control']=='no-store'
    location=headers['Location'];identifier=location.rsplit('/',1)[1]
    saved=store.load(web[1],identifier);original=saved.model_dump_json()
    assert saved.origin=='synthetic_demo'
    status,_,html=call(web,'GET',location)
    assert status==200 and '$146.39' in html and 'Saved calculation' in html
    assert 'name="target"' not in html
    status,headers,raw=call(web,'GET',location+'/inputs.json')
    assert status==200 and headers['Cache-Control']=='no-store'
    assert parse_mixed_input(raw.encode())==mixed_example()
    status,_,raw=call(web,'GET',location+'/summary.json')
    assert status==200 and json.loads(raw)==mixed_summary(compare_mixed_payoff(mixed_example()))
    assert call(web,'GET',location+'/smallest-balance.csv')[0]==200
    assert 'Sample cards and loan' in call(web,'GET','/mixed-payoff-runs')[2]
    assert store.load(web[1],identifier).model_dump_json()==original


def test_import_review_requires_no_write_then_signed_save_and_escapes_name(web):
    csrf=token(web);name='<script>alert(1)</script>'
    raw=mixed_example().model_dump_json()
    status,_,html=post(web,'/mixed-payoff/import-preview',{'token':csrf,'name':name,'inputs':raw})
    assert status==200 and '&lt;script&gt;' in html and '<script>alert' not in html
    assert not list((web[1]/'mixed_payoff_runs').glob('*.json'))
    assert 'Supplied-input estimate' in html
    status,headers,_=post(web,'/mixed-payoff/save',hidden(html))
    assert status==303
    saved=store.load(web[1],headers['Location'].rsplit('/',1)[1])
    assert saved.name==name and saved.origin=='supplied_estimate' and saved.inputs==mixed_example()


def test_import_invalid_fields_csrf_origin_and_corrupt_saved_record(web):
    csrf=token(web);values={'token':csrf,'name':'Prepared','inputs':mixed_example().model_dump_json()}
    assert post(web,'/mixed-payoff/import-preview',values|{'token':'bad'})[0]==403
    assert post(web,'/mixed-payoff/import-preview',values,Origin='https://example.invalid')[0]==403
    assert post(web,'/mixed-payoff/import-preview',values|{'extra':'field'})[0]==400
    assert post(web,'/mixed-payoff/import-preview',values|{'inputs':'bad JSON'})[0]==422
    assert call(web,'GET','/mixed-payoff-run/'+'a'*32)[0]==404
    folder=web[1]/'mixed_payoff_runs';folder.mkdir();path=folder/('b'*32+'.json');path.write_text('broken')
    assert call(web,'GET','/mixed-payoff-run/'+'b'*32)[0]==422
    assert path.read_text()=='broken' and 'file has been kept' in call(web,'GET','/mixed-payoff-runs')[2]
