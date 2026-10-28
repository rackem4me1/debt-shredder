import re
from decimal import Decimal
from urllib.parse import urlencode
from dashboard.guidance import practice_inputs
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.forms import manual_form, validation_messages
from dashboard.input_review import render_inputs
from dashboard.scenarios import load_scenario, save_scenario
from engine.common import reconstruct
from test_dashboard_manual import web,call,token,post,fields


def sample_post(web, values=None):
    return call(web,'POST','/create-example',urlencode((values or practice_inputs())|{'token':token(web),'scope':'confirmed'}),
                {'Content-Type':'application/x-www-form-urlencoded'})


def test_practice_is_explicitly_synthetic_and_saved_with_correct_results(web):
    status,_,html=call(web,'GET','/practice')
    assert status==200 and 'made-up numbers' in html and 'January 2026' in html
    assert 'action="/preview-example"' in html and 'value="150"' in html
    assert not list(web[1].glob('*.json'))
    status,headers,_=sample_post(web)
    assert status==303
    saved=load_scenario(next(web[1].glob('*.json')))
    assert saved.origin=='synthetic_demo'
    result=saved.project()
    assert result.decisions[0].accepted==120
    assert result.debt_projections[0].account.segments[0].accrued_unposted_interest==Decimal('8.22')
    assert 'Synthetic example' in call(web,'GET',headers['Location'])[2]


def test_practice_error_keeps_mode_and_inputs(web):
    status,_,html=sample_post(web,practice_inputs()|{'minimum_remaining':'501'})
    assert status==422 and 'action="/preview-example"' in html
    assert 'value="501"' in html and 'made-up numbers' in html
    assert not list(web[1].glob('*.json'))


def test_practice_copy_preserves_origin_and_original_file(web):
    _,headers,_=sample_post(web)
    id_=headers['Location'].split('/')[-1]
    path=web[1]/(id_+'.json')
    original=path.read_bytes()
    saved=load_scenario(path)
    status,_,html=call(web,'GET','/edit/'+id_)
    assert status==200 and 'action="/preview-example"' in html
    inputs=editable_inputs(saved)|{'payment_amount':'80','name':'Practice copy'}
    status,headers,_=sample_post(web,inputs)
    assert status==303 and path.read_bytes()==original
    second=load_scenario(web[1]/(headers['Location'].split('/')[-1]+'.json'))
    assert second.origin=='synthetic_demo' and second.name=='Practice copy'


def test_blank_real_form_has_no_financial_defaults(web):
    status,_,html=call(web,'GET','/new')
    assert status==200 and 'action="/preview"' in html
    assert 'name="cash" type="number" value=""' in html
    assert 'name="apr_percent" type="number" value=""' in html
    assert 'value="confirmed" checked' not in html


def test_input_review_is_read_only_and_shows_assumptions(web):
    _,headers,_=post(web,fields()|{'token':token(web)})
    id_=headers['Location'].split('/')[-1]
    path=web[1]/(id_+'.json')
    before=path.read_bytes()
    status,_,html=call(web,'GET','/inputs/'+id_)
    assert status==200 and 'Manually entered estimates' in html
    assert 'Actual days / 365' in html and 'no active grace period' in html
    assert '36.500' in html and 'Cash is committed from this day' in html
    assert path.read_bytes()==before
    assert 'Back to result' in html and 'Jan 01, 2026' in html
    assert 'Review inputs and assumptions' in call(web,'GET',headers['Location'])[2]


def test_input_review_escapes_text_and_does_not_invent_zero_payment_dates():
    scenario=ManualScenario(**(fields()|{'payment_amount':'0','name':'<img src=x>'})).scenario()
    html=render_inputs(scenario)
    assert '<img' not in html and '&lt;img' in html
    assert html.count('Not used — no payment requested')==5


def test_input_review_rejects_unrepresentable_saved_data(web):
    from demo_portfolio import scenario
    id_='c'*32
    save_scenario(scenario(),web[1]/(id_+'.json'))
    assert call(web,'GET','/inputs/'+id_)[0]==422
    assert call(web,'GET','/inputs/'+'d'*32)[0]==404
    assert call(web,'GET','/inputs/../../SCHEMA.py')[0]==404


def test_field_help_is_linked_to_unique_input_ids():
    html=manual_form('token')
    ids=re.findall(r'\bid="([^"]+)"',html)
    assert len(ids)==len(set(ids))
    for id_ in re.findall(r'aria-describedby="([^"]+)"',html):
        assert id_ in ids
    assert 'Do not assume 0 if it is unknown.' in html


def test_validation_messages_use_visible_labels():
    assert validation_messages([{'loc':('apr_percent',),'msg':'Field required'}])==['Annual interest rate (%): Field required']
    assert validation_messages([{'loc':(),'msg':'Value error, Dates must be ordered'}])==['Dates must be ordered']


def test_practice_endpoint_still_requires_token(web):
    status,_,_=call(web,'POST','/create-example',urlencode(practice_inputs()|{'scope':'confirmed'}),
                   {'Content-Type':'application/x-www-form-urlencoded'})
    assert status==403 and not list(web[1].glob('*.json'))
