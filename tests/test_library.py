from urllib.parse import urlencode
import pytest
from dashboard.scenarios import save_scenario
from dashboard.strategies import strategy_example
from engine.common import reconstruct
from test_dashboard_manual import web,call


def test_library_search_filters_and_never_modifies_files(web):
    manual=reconstruct(strategy_example(),name='Household plan',origin='manual',card_names=('Travel account','Daily'))
    practice=strategy_example()
    for id_,s in [('a'*32,manual),('b'*32,practice)]:save_scenario(s,web[1]/(id_+'.json'))
    before={p.name:p.read_bytes() for p in web[1].glob('*.json')}
    html=call(web,'GET','/?'+urlencode({'q':'tRaVeL','kind':'manual'}))[2]
    assert 'Household plan' in html and 'Two-card priority example' not in html
    assert 'Forecast 2026-01-01 through 2026-01-21' in html
    html=call(web,'GET','/?kind=synthetic_demo')[2]
    assert 'Two-card priority example' in html and 'Household plan' not in html
    assert 'No scenarios match' in call(web,'GET','/?q=missing')[2]
    assert before=={p.name:p.read_bytes() for p in web[1].glob('*.json')}


@pytest.mark.parametrize('query',['kind=other','q=a&q=b','q='+('x'*121),'unexpected=yes','q=a&kind=all&extra=a'])
def test_invalid_filters_rejected(web,query):
    assert call(web,'GET','/?'+query)[0]==400


def test_library_empty_corrupt_and_escaped_names(web):
    assert 'No saved scenarios yet' in call(web,'GET','/')[2]
    (web[1]/('a'*32+'.json')).write_text('{broken')
    save_scenario(reconstruct(strategy_example(),name='<img src=x>'),web[1]/('b'*32+'.json'))
    html=call(web,'GET','/')[2]
    assert 'could not be opened' in html and '&lt;img src=x&gt;' in html and '<img src=x>' not in html
    assert (web[1]/('a'*32+'.json')).read_text()=='{broken'
