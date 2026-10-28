import re
from urllib.parse import urlencode
from html import unescape
import pytest
from dashboard.strategies import strategy_example, selected_strategy
from dashboard.scenarios import save_scenario, load_scenario
from dashboard.manual import editable_inputs
from engine.common import reconstruct
from test_dashboard_manual import web, call

def post(web,fields):
    return call(web,"POST","/save-strategy",urlencode(fields),{"Content-Type":"application/x-www-form-urlencoded"})


def review(web, source='example', choice='smallest-balance'):
    status,_,html=call(web,'GET',f'/strategy-review/{source}/{choice}')
    assert status==200
    fields={k:unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}
    return fields,html


@pytest.mark.parametrize('choice',['highest-interest','smallest-balance'])
def test_save_preserves_exact_candidate_and_projection(web,choice):
    original=strategy_example();id_='a'*32;path=web[1]/(id_+'.json')
    save_scenario(original,path);before=path.read_bytes()
    fields,html=review(web,id_,choice)
    assert 'Save as a separate scenario' in html and 'Payment request order' in html
    assert html.count('<h1>')==1
    assert 'saved request priorities determine' in html
    assert 'Timing and card order determine' not in html
    assert len(list(web[1].glob('*.json')))==1
    status,headers,_=post(web,fields)
    assert status==303
    saved=load_scenario(web[1]/(headers['Location'].split('/')[-1]+'.json'))
    expected=selected_strategy(original,choice)
    assert saved==expected
    assert saved.project()==expected.project()
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==2
    page=call(web,'GET',headers['Location'])
    assert page[0]==200 and 'Payment request order' in page[2]
    if choice=='smallest-balance':
        with pytest.raises(ValueError):editable_inputs(saved)
        assert 'simple editor cannot preserve' in page[2]
        assert 'Adjust a copy' not in page[2]
    assert call(web,'GET','/timeline/'+headers['Location'].split('/')[-1])[0]==200


def test_synthetic_review_and_save_keep_practice_origin(web):
    fields,_=review(web)
    assert not list(web[1].glob('*.json'))
    status,headers,_=post(web,fields)
    assert status==303
    saved=load_scenario(next(web[1].glob('*.json')))
    assert saved.origin=='synthetic_demo'
    assert saved==selected_strategy(strategy_example(),'smallest-balance')


@pytest.mark.parametrize('change,status',[
    ({'token':'bad'},403),({'fingerprint':'bad'},409),({'fingerprint':'é'},409),
    ({'source':'../../SCHEMA'},400),({'choice':'invented'},422),
    ({'amount':'999'},400),({'choice':'highest-interest'},409),
])
def test_invalid_save_never_writes(web,change,status):
    fields,_=review(web)
    assert post(web,fields|change)[0]==status
    assert not list(web[1].glob('*.json'))


def test_changed_source_requires_review_again(web):
    path=web[1]/('a'*32+'.json');original=strategy_example()
    save_scenario(original,path)
    fields,_=review(web,'a'*32)
    changed=reconstruct(original,name='Changed since review')
    save_scenario(changed,path,overwrite=True)
    before=path.read_bytes()
    assert post(web,fields)[0]==409
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==1


def test_deleted_source_and_missing_review_do_not_save(web):
    path=web[1]/('a'*32+'.json');save_scenario(strategy_example(),path)
    fields,_=review(web,'a'*32);path.unlink()
    assert post(web,fields)[0]==404
    assert call(web,'GET','/strategy-review/'+'a'*32+'/smallest-balance')[0]==404
    assert call(web,'GET','/strategy-review/example/nope')[0]==404
    assert not list(web[1].glob('*.json'))


def test_order_review_escapes_names_and_matches_allocation_order(web):
    original=reconstruct(strategy_example(),card_names=('<First>','<Second>'))
    save_scenario(original,web[1]/('a'*32+'.json'))
    _,html=review(web,'a'*32)
    assert '&lt;First&gt;' in html and '<First>' not in html
    order=html.split('<h2>Payment request order</h2>',1)[1].split('</tbody>',1)[0]
    assert re.findall(r'<tr><td>(.*?)</td><td>(.*?)</td>',order)==[
        ('&lt;First&gt; (card)','minimum'),('&lt;Second&gt; (card-2)','minimum'),
        ('&lt;Second&gt; (card-2)','extra'),('&lt;First&gt; (card)','extra')]
