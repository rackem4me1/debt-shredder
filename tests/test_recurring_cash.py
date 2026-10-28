from datetime import date, datetime, timezone
from html import unescape
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
import re
import pytest
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.scenarios import parse_scenario
from dashboard.cash_inputs import cash_horizon, expand_cash_events, ManualCashEvent
from dashboard.cash_review import cash_review
from dashboard.comparison import compare
from test_dashboard_manual import fields, web, call, token


def recurring(**updates):
    return dict(kind='income', label='Paycheck', amount='100', date='2026-01-02', cadence='biweekly') | updates


def make(*events, **updates):
    return ManualScenario.model_validate(fields() | updates | dict(cash_events=events)).scenario()


def local_dates(s):
    return [p.initiated_at.astimezone(ZoneInfo('America/Chicago')).date().isoformat() for p in s.cash_plans]


def test_biweekly_cash_dates_and_dst_use_local_midnight():
    s = make(recurring())
    assert local_dates(s) == ['2026-01-02','2026-01-16','2026-01-30','2026-02-13','2026-02-27','2026-03-13','2026-03-27']
    assert s.cash_plans[0].initiated_at.hour == 6
    assert s.cash_plans[-1].initiated_at.hour == 5
    assert s.project().decisions[0].accepted == 200
    assert cash_horizon(s.start,s.end,s.requests) == s.project().liquidity.end


def test_weekly_stop_is_inclusive_and_cash_limits_use_all_bills():
    s = make(recurring(kind='expense', amount='10', cadence='weekly', until='2026-01-16'))
    assert local_dates(s) == ['2026-01-02','2026-01-09','2026-01-16']
    assert s.project().decisions[0].accepted == 90


@pytest.mark.parametrize('rule,expected', [
    ('clamp_to_last_day_of_month',['2026-01-31','2026-02-28','2026-03-31']),
    ('roll_to_next_month_first_day',['2026-01-31','2026-03-01','2026-03-31'])])
def test_monthly_31st_requires_explicit_short_month_semantics(rule,expected):
    s = make(recurring(date='2026-01-31',cadence='monthly',short_month_rule=rule))
    assert local_dates(s) == expected


def test_leap_february_and_no_weekend_adjustment():
    event=ManualCashEvent(**recurring(date='2028-01-31',cadence='monthly',short_month_rule='clamp_to_last_day_of_month'))
    tz=ZoneInfo('America/Chicago')
    plans=expand_cash_events((event,),datetime(2028,1,1,tzinfo=tz),datetime(2028,3,31,tzinfo=tz),'America/Chicago')
    assert [p.initiated_at.astimezone(tz).day for p in plans]==[31,29,31]
    s=make(recurring(date='2026-01-03',cadence='weekly',until='2026-01-10'))
    assert local_dates(s)==['2026-01-03','2026-01-10']  # Saturdays remain Saturdays.


@pytest.mark.parametrize('changes', [dict(cadence='monthly'),dict(cadence='daily'),
    dict(short_month_rule='clamp_to_last_day_of_month'),dict(until='2026-01-01'),
    dict(cadence='once',until='2026-02-01'),dict(cadence='monthly',short_month_rule='guess')])
def test_incomplete_or_incompatible_schedule_terms_rejected(changes):
    with pytest.raises(ValueError): make(recurring(**changes))


def test_schedule_intent_survives_save_parse_and_edit():
    original=make(recurring(),recurring(kind='expense',label='Rent',date='2026-01-01',cadence='monthly',
        short_month_rule='clamp_to_last_day_of_month',until='2026-12-31'),recurring(cadence='once',label='One bill',kind='expense'))
    restored=parse_scenario(original.model_dump_json().encode())
    assert restored==original
    assert ManualScenario.model_validate(editable_inputs(restored)).scenario()==original
    assert 'Every two weeks' in cash_review(original) and 'Dec 31, 2026' in cash_review(original)
    later_stop = editable_inputs(original) | {'cash_1_until':'2027-12-31'}
    changed = ManualScenario.model_validate(later_stop).scenario()
    assert changed.cash_plans == original.cash_plans
    assert 'Income and bill schedule settings' in compare(original,changed)['changes']


@pytest.mark.parametrize('mutation', ['amount','remove','cadence','time'])
def test_schedule_metadata_cannot_disagree_with_cash_events(mutation):
    data=make(recurring()).model_dump(mode='json')
    if mutation=='amount':data['cash_plans'][0]['amount']='999'
    if mutation=='remove':data['cash_plans'].pop()
    if mutation=='cadence':data['manual_cash_schedules'][0]['cadence']='weekly'
    if mutation=='time':data['cash_plans'][0]['settled_at']='2026-01-02T07:00:00Z'
    import json
    with pytest.raises(ValueError):parse_scenario(json.dumps(data).encode())


def test_changing_payment_date_reexpands_schedule_for_new_horizon():
    original=make(recurring(cadence='weekly'))
    inputs=editable_inputs(original)|dict(initiated='2026-01-09',credited='2026-01-10',debited='2026-01-11',settled='2026-01-12')
    changed=ManualScenario.model_validate(inputs).scenario()
    assert len(changed.cash_plans)==len(original.cash_plans)+1
    assert local_dates(changed)[-1]=='2026-04-03'


def test_old_scenarios_without_schedule_field_still_load():
    s=make()
    data=s.model_dump(mode='json');data.pop('manual_cash_schedules')
    import json
    assert parse_scenario(json.dumps(data).encode())==s


def submit(web,path,values):
    return call(web,'POST',path,urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'})


def hidden(html):
    return {unescape(k):unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}


def test_preview_change_and_save_exact_dates_with_synthetic_origin(web):
    values=fields()|{'token':token(web)}|{f'cash_0_{k}':v for k,v in recurring(label='<Pay & check>').items()}
    status,_,html=submit(web,'/preview-example',values)
    assert status==200 and 'nothing saved yet' in html and '7 occurrences' in html
    assert '&lt;Pay &amp; check&gt;' in html and '<Pay & check>' not in html
    assert 'Mar 27, 2026' in html and not list(web[1].glob('*.json'))
    carried=hidden(html)
    status,_,revised=submit(web,'/revise-example',carried)
    assert status==200 and 'action="/preview-example"' in revised
    assert '<option value="biweekly" selected>' in revised
    assert not list(web[1].glob('*.json'))
    status,headers,_=submit(web,'/create-example',carried)
    assert status==303
    from dashboard.scenarios import load_scenario
    s=load_scenario(next(web[1].glob('*.json')))
    assert s.origin=='synthetic_demo' and len(s.cash_plans)==7
    assert call(web,'GET',headers['Location'])[0]==200


def test_preview_validation_and_save_revalidation(web):
    values=fields()|{'token':token(web)}|{f'cash_0_{k}':v for k,v in recurring(cadence='monthly').items()}
    assert submit(web,'/preview',values)[0]==422
    values['cash_0_short_month_rule']='clamp_to_last_day_of_month'
    status,_,html=submit(web,'/preview',values)
    assert status==200
    carried=hidden(html);carried['cash_0_amount']='-1'
    assert submit(web,'/create',carried)[0]==422
    assert not list(web[1].glob('*.json'))


@pytest.mark.parametrize('path',['/preview','/preview-example','/revise','/revise-example'])
def test_new_post_routes_require_token_and_reject_get(web,path):
    assert submit(web,path,fields())[0]==403
    assert call(web,'GET',path)[0]==404


def test_six_complete_rows_and_unused_defaults_fit_http_limit(web):
    values=fields()|{'token':token(web)}
    for i in range(6):
        row=recurring(label=f'Paycheck {i}')|{'until':'','short_month_rule':''}
        values.update({f'cash_{i}_{k}':v for k,v in row.items()})
    status,_,html=submit(web,'/preview',values)
    assert status==200 and '42 occurrences' in html
    assert not list(web[1].glob('*.json'))
