from decimal import Decimal as D, localcontext
import json
import pytest
from dashboard.comparison import compare, render_comparison
from dashboard.manual import ManualScenario
from dashboard.scenarios import save_scenario
from engine.common import reconstruct
from test_dashboard_manual import fields, web, call, post, token


def pair():
    return (ManualScenario(**fields()).scenario(),
            ManualScenario(**(fields()|{'name':'Smaller payment','payment_amount':'80'})).scenario())


def test_comparison_quantifies_tradeoffs_without_recommending_a_winner():
    a,b=pair()
    result=compare(a,b)
    rows={r['label']:r for r in result['rows']}
    assert result['comparable']
    assert result['changes']==['Requested payments and timing']
    assert D(rows['Payments applied']['difference'])==-40
    assert D(rows['Cash left in accounts']['difference'])==40
    assert D(rows['Posted card debt']['difference'])==40
    assert D(rows['Interest awaiting statement posting']['difference'])==D('.76')
    html=render_comparison(a,b)
    assert '$40.00 less' in html and '$0.76 more' in html
    assert 'not which plan you should choose' in html


def test_different_windows_hide_differences():
    a,_=pair()
    b=ManualScenario(**(fields()|{'end':'2026-01-22'})).scenario()
    result=compare(a,b)
    assert not result['comparable'] and all(r['difference'] is None for r in result['rows'])
    assert any('time windows' in warning for warning in result['warnings'])


def test_cash_windows_checked_even_when_debt_windows_match():
    a,_=pair()
    b=ManualScenario(**(fields()|{'initiated':'2026-01-03'})).scenario()
    result=compare(a,b)
    assert result['left']['debt_end']==result['right']['debt_end']
    assert result['left']['cash_end']!=result['right']['cash_end']
    assert not result['comparable']


def test_account_set_mismatch_and_source_labels_are_explicit():
    a,b=pair()
    opening=reconstruct(b.openings[0],account_id='other')
    request=reconstruct(b.requests[0],source_account_id='other')
    b=reconstruct(b,openings=(opening,),requests=(request,),origin='synthetic_demo')
    result=compare(a,b)
    assert not result['comparable']
    assert len(result['warnings'])==2
    assert 'Synthetic example' in render_comparison(a,b)


def test_comparison_uses_own_decimal_context_and_escapes_names():
    a,b=pair()
    expected=compare(a,b)
    with localcontext() as context:
        context.prec=3
        assert compare(a,b)==expected
    html=render_comparison(reconstruct(a,name='<script>unsafe</script>'),b)
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_zero_payment_keeps_actual_missed_due_visible():
    a,_=pair()
    b=ManualScenario(**(fields()|{'payment_amount':'0'})).scenario()
    result=compare(a,b)
    assert not result['left']['missed_minimum_account_ids']
    assert result['right']['missed_minimum_account_ids']==['card']
    assert 'Missed due dates: card' in render_comparison(a,b)


def test_identical_inputs_are_explicit_and_not_optimized():
    a,_=pair()
    b=reconstruct(a,name='Same inputs')
    result=compare(a,b)
    assert not result['changes']
    assert all(D(r['difference'])==0 for r in result['rows'])
    assert 'financial inputs are identical' in render_comparison(a,b)


def test_http_comparison_is_read_only_with_saved_choices(web):
    a,b=pair()
    ids=['a'*32,'b'*32]
    for id_,item in zip(ids,(a,b)):save_scenario(item,web[1]/(id_+'.json'))
    before={p.name:p.read_bytes() for p in web[1].glob('*.json')}
    status,_,html=call(web,'GET','/compare?left='+ids[0])
    assert status==200 and 'value="'+ids[0]+'" selected' in html
    status,_,html=call(web,'GET','/compare?left='+ids[0]+'&right='+ids[1])
    assert status==200 and '$0.76 more' in html
    assert {p.name:p.read_bytes() for p in web[1].glob('*.json')}==before


@pytest.mark.parametrize('query,status',[
    ('left=../secret&right='+'b'*32,400),
    ('left='+'a'*32+'&left='+'b'*32,400),
    ('left='+'a'*32+'&right='+'a'*32,422),
    ('left='+'a'*32+'&right='+'b'*32,404),
    ('unknown=value',400),
])
def test_bad_comparison_selections_do_not_access_other_files(web,query,status):
    assert call(web,'GET','/compare?'+query)[0]==status


def test_empty_home_example_comparison_creates_no_files(web):
    status,_,html=call(web,'GET','/compare')
    assert status==200 and 'Save a scenario first' in html
    status,_,html=call(web,'GET','/compare-example')
    assert status==200 and 'Synthetic example' in html and '$100.00 more' in html
    assert not list(web[1].glob('*.json'))


def test_report_separates_requested_dollars_from_contract_minimum():
    from dashboard.report import render
    a,_=pair()
    html=render(a)
    assert 'No missed minimum dates' in html
    assert 'Some requested payment dollars do not fit' in html
    assert 'not fully funded' not in html
    assert 'Jan 01, 2026 at 12:00 AM CST' in html
    assert 'Dates shown in America/Chicago' in html


def test_display_dates_follow_creditor_zone_across_dst():
    from dashboard.report import readable_time
    assert readable_time('2026-03-08T08:00:00+00:00','America/Chicago')=='Mar 08, 2026 at 03:00 AM CDT'
    assert readable_time('2026-01-01T03:00:00+00:00','America/Chicago')=='Dec 31, 2025 at 09:00 PM CST'


def test_subcent_interest_difference_is_not_reported_as_zero():
    a,_=pair()
    b=ManualScenario(**(fields()|{'apr_percent':'36.50001'})).scenario()
    html=render_comparison(a,b)
    assert 'Less than $0.01 more' in html
    assert '$0.00 more' not in html
