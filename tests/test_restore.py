import re
from html import unescape
from urllib.parse import urlencode
import pytest
from dashboard.strategies import strategy_example,selected_strategy
from dashboard.scenarios import save_scenario,load_scenario,MAX_BYTES
from engine.common import reconstruct
from test_dashboard_manual import web,call,token


def post(web,path,values,headers=None):
    return call(web,'POST',path,urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'}|(headers or {}))


def hidden(html):
    return {k:unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}


def preview(web,scenario):
    status,_,html=post(web,'/restore-preview',{'token':token(web),'payload':scenario.model_dump_json()})
    assert status==200
    return hidden(html),html


def test_restore_exact_priority_candidate_without_overwriting(web):
    original=selected_strategy(strategy_example(),'smallest-balance')
    path=web[1]/('a'*32+'.json');save_scenario(original,path);before=path.read_bytes()
    fields,html=preview(web,original)
    assert 'Nothing has been saved yet' in html and 'Payment request order' in html
    assert html.count('<h1>')==1
    assert len(list(web[1].glob('*.json')))==1
    status,headers,_=post(web,'/restore-save',fields)
    assert status==303
    restored=load_scenario(web[1]/(headers['Location'].split('/')[-1]+'.json'))
    assert restored==original and restored.project()==original.project()
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==2


@pytest.mark.parametrize('payload',['{}','not json','{"version":1,"version":1}', '['*1200, '\ufeff{}'])
def test_bad_backups_write_nothing(web,payload):
    status,_,html=post(web,'/restore-preview',{'token':token(web),'payload':payload})
    assert status==422 and 'Nothing was saved' in html
    assert not list(web[1].glob('*.json'))


@pytest.mark.parametrize('change,status',[
    ({'signature':'bad'},409),({'signature':'é'},409),({'token':'bad'},403),
    ({'payload':'{}'},409),({'unexpected':'yes'},400),
])
def test_restore_rejects_unreviewed_changes(web,change,status):
    fields,_=preview(web,strategy_example())
    assert post(web,'/restore-save',fields|change)[0]==status
    assert not list(web[1].glob('*.json'))


def test_restore_size_and_cross_origin_limits(web):
    auth=token(web)
    assert post(web,'/restore-preview',{'token':auth,'payload':'x'*(MAX_BYTES+1)})[0]==413
    assert post(web,'/restore-preview',{'token':auth,'payload':'{}'}, {'Origin':'https://example.com'})[0]==403
    assert not list(web[1].glob('*.json'))


def test_restore_escapes_html_and_preserves_manual_origin(web):
    s=reconstruct(strategy_example(),name='<script>alert(1)</script>',origin='manual')
    fields,html=preview(web,s)
    assert '<script>alert(1)</script>' not in html and '&lt;script&gt;' in html
    assert post(web,'/restore-save',fields)[0]==303
    assert load_scenario(next(web[1].glob('*.json')))==s


def test_restore_ui_and_script_are_local_and_packaged(web):
    status,_,html=call(web,'GET','/restore')
    assert status==200 and 'type="file"' in html and 'name="payload"' in html
    assert '/restore.js' in html
    status,headers,script=call(web,'GET','/restore.js')
    assert status==200 and 'text/javascript' in headers['Content-Type']
    assert 'file.text()' in script and 'current !== selection' in script
    assert call(web,'GET','/restore.js/../SCHEMA.py')[0]==404
    from pathlib import Path
    assert '"restore.js"' in Path('pyproject.toml').read_text()
