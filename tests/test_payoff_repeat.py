from datetime import date,time,timedelta
import json
from decimal import Decimal
import pytest
from demo_payoff import saved_example
from dashboard import payoff_repeat,payoff_runs
from dashboard.scenarios import save_scenario
from dashboard.cash_inputs import ManualCashEvent,expand_cash_events,cash_horizon
from engine.common import reconstruct
from engine.payoff_calendar import expand_payoff_template
from engine.payoff import compare_payoff
from test_dashboard_manual import web,call
from test_restore import hidden,post


def values():
    return dict(payment_target='250',end='2027-12-31',cadence='monthly',first_payment='2026-01-20',
        credit_days='0',debit_days='0',settlement_days='0',short_month_rule='clamp_to_last_day_of_month',scope='assumed_calendar')


def repeating_source():
    source=saved_example()
    events=(ManualCashEvent(kind='income',label='Sample pay',amount='1200',date='2026-01-01',cadence='monthly',short_month_rule='clamp_to_last_day_of_month'),
        ManualCashEvent(kind='expense',label='Sample bills',amount='900',date='2026-01-02',cadence='monthly',short_month_rule='clamp_to_last_day_of_month'))
    cash=expand_cash_events(events,source.start,cash_horizon(source.start,source.end,source.requests),'UTC')
    return reconstruct(source,manual_cash_schedules=events,cash_plans=cash)


def test_adapter_reexpands_only_explicit_cash_rules_preserves_original_and_stop_date():
    source=repeating_source();before=source.model_dump_json()
    template=payoff_repeat.template_from_scenario(source,values())
    assert not template.one_off_cash_plans
    expanded=expand_payoff_template(template)
    assert len(expanded.inputs.slots)==24 and len(expanded.inputs.cash_plans)==54
    assert sum(p.amount for p in expanded.inputs.cash_plans if p.kind.value=='income')==27*1200
    assert source.model_dump_json()==before
    assert expanded.template.debts==source.debts
    result=compare_payoff(expanded.inputs)
    assert result.results[0].posted_interest==Decimal('74.18')
    stopped=reconstruct(template,cash_schedules=tuple(reconstruct(s,until=date(2026,3,2)) for s in template.cash_schedules))
    cash=expand_payoff_template(stopped).inputs.cash_plans
    assert len(cash)==6


def test_adapter_with_no_repeat_rules_keeps_each_one_off_once_and_warns():
    source=saved_example();expanded,html=payoff_repeat.calculate(source,values())
    assert expanded.inputs.cash_plans==source.cash_plans
    assert 'No repeating income/bill rules were supplied' in html
    assert len(expanded.inputs.slots)==24
    assert '74.18' in html and 'August 31, 2026' in html


@pytest.mark.parametrize('patch',[{'scope':''},{'end':'2026-01-01'},{'credit_days':'1.5'},{'credit_days':'2','debit_days':'1'},
    {'cadence':'daily'},{'extra':'ignored'},{'payment_target':'250.001'},{'first_payment':'2025-12-01'}])
def test_bad_repeat_inputs_do_not_get_silent_defaults(patch):
    with pytest.raises((ValueError,ArithmeticError)):payoff_repeat.calculate(saved_example(),values()|patch)


def test_run_save_is_immutable_and_independent_of_source_edits(tmp_path):
    source=repeating_source();expanded=expand_payoff_template(payoff_repeat.template_from_scenario(source,values()))
    run=payoff_runs.PayoffRun(source_id='a'*32,source=source,expanded=expanded)
    first=payoff_runs.save(tmp_path,run);second=payoff_runs.save(tmp_path,run)
    assert first!=second and payoff_runs.load(tmp_path,first)==run
    source=reconstruct(source,name='Later source name',openings=(reconstruct(source.openings[0],cleared='1'),))
    loaded=payoff_runs.load(tmp_path,first)
    assert loaded.source.name!='Later source name' and loaded.expanded.inputs.opening.cleared==400
    html=payoff_runs.render(loaded)
    assert 'August 31, 2026' in html and 'Saved estimate' in html
    assert 'Payoff practice' in payoff_runs.library(tmp_path)
    payload=json.loads(run.model_dump_json());payload['expanded']['inputs']['payment_target']='251'
    with pytest.raises(ValueError):payoff_runs.parse(json.dumps(payload).encode())
    for version in (None,True,2):
        payload=json.loads(run.model_dump_json());payload['version']=version
        with pytest.raises(ValueError):payoff_runs.parse(json.dumps(payload).encode())
    with pytest.raises(ValueError):payoff_runs.load(tmp_path,'../outside')


def test_repeat_preview_save_and_reopen_do_not_edit_original(web):
    source=repeating_source();identifier='a'*32;path=web[1]/(identifier+'.json');save_scenario(source,path);original=path.read_bytes()
    status,_,page=call(web,'GET','/plan/'+identifier)
    assert status==200 and 'Repeat a longer payoff calendar' in page
    fields=hidden(page)|values()
    status,_,preview=post(web,'/payoff-repeat/'+identifier,fields)
    assert status==200 and '24 payment rounds' in preview
    assert 'No repeating income/bill rules were supplied' not in preview
    assert 'Save this payoff run' in preview
    assert not (web[1]/'payoff_runs').exists() and path.read_bytes()==original
    save_fields={k:v for k,v in hidden(preview).items() if k in ('token','payload','signature')}
    assert post(web,'/payoff-repeat-save/'+identifier,save_fields|{'signature':'wrong'})[0]==409
    changed=save_fields|{'payload':save_fields['payload'].replace('250','251',1)}
    assert post(web,'/payoff-repeat-save/'+identifier,changed)[0]==409
    assert post(web,'/payoff-repeat-save/'+'b'*32,save_fields)[0]==409
    status,headers,_=post(web,'/payoff-repeat-save/'+identifier,save_fields)
    assert status==303 and headers['Location'].startswith('/payoff-run/')
    status,_,saved=call(web,'GET',headers['Location'])
    assert status==200 and 'August 31, 2026' in saved and 'Saved estimate' in saved
    assert path.read_bytes()==original
    save_scenario(reconstruct(source,name='Changed'),path,overwrite=True)
    assert post(web,'/payoff-repeat-save/'+identifier,save_fields)[0]==409
    assert post(web,'/payoff-repeat/'+identifier,fields)[0]==409
    assert 'Payoff practice' in call(web,'GET','/payoff-runs')[2]
    assert call(web,'GET','/payoff-run/'+'f'*32)[0]==404


def test_repeat_invalid_fields_retained_and_csrf_origin_rejected(web):
    source=saved_example();identifier='c'*32;save_scenario(source,web[1]/(identifier+'.json'))
    fields=hidden(call(web,'GET','/plan/'+identifier)[2])|values()
    assert post(web,'/payoff-repeat/'+identifier,fields|{'token':'bad'})[0]==403
    assert post(web,'/payoff-repeat/'+identifier,fields,{'Origin':'https://outside.example'})[0]==403
    status,_,html=post(web,'/payoff-repeat/'+identifier,fields|{'payment_target':'12.001'})
    assert status==422 and 'value="12.001"' in html
    assert not (web[1]/'payoff_runs').exists()


def test_saved_exports_replay_exact_inputs_and_csv_stays_text(web):
    import csv
    from io import StringIO
    from engine.payoff import plan_payoff
    from payoff_cli import parse_input
    from payoff_exports import payment_csv
    source=repeating_source();expanded=expand_payoff_template(payoff_repeat.template_from_scenario(source,values()))
    run=payoff_runs.PayoffRun(source_id='d'*32,source=source,expanded=expanded)
    identifier=payoff_runs.save(web[1],run);prefix='/payoff-run/'+identifier
    status,headers,raw=call(web,'GET',prefix+'/inputs.json')
    assert status==200 and 'application/json' in headers['Content-Type']
    assert headers['Cache-Control']=='no-store'
    assert parse_input(raw.encode())==expanded.inputs
    assert json.loads(call(web,'GET',prefix+'/template.json')[2])==json.loads(expanded.template.model_dump_json())
    for suffix,strategy in (('highest-interest.csv','highest_interest_first'),('smallest-balance.csv','smallest_balance_first')):
        status,headers,csv_text=call(web,'GET',prefix+'/'+suffix)
        assert status==200 and 'text/csv' in headers['Content-Type']
        rows=list(csv.DictReader(StringIO(csv_text)))
        result=plan_payoff(expanded.inputs,strategy)
        assert sum(Decimal(row['total_paid']) for row in rows)==result.total_paid
        assert rows[0]['credit']=='2026-01-20T12:00:00+00:00'
    result=plan_payoff(expanded.inputs)
    escaped=payment_csv(result,lambda account:'=SUM(A1:A2)')
    assert next(csv.DictReader(StringIO(escaped)))['account'].startswith("'=")
    assert call(web,'GET',prefix+'/other.csv')[0]==404
    assert '/payoff-runs' in call(web,'GET','/')[2]


@pytest.mark.parametrize('mode',['different_due','statement_lag'])
def test_repeat_form_does_not_override_conflicting_known_statement_dates(mode):
    source=saved_example();debt=source.debts[0];latest=debt.cycles[-1]
    if mode=='different_due':changed=reconstruct(latest,due_date=latest.due_date-timedelta(days=1))
    else:changed=reconstruct(latest,statement_date=latest.statement_date+timedelta(days=1))
    source=reconstruct(source,debts=(reconstruct(debt,cycles=debt.cycles[:-1]+(changed,)),)+source.debts[1:])
    with pytest.raises(ValueError,match='statement|Statement'):
        payoff_repeat.calculate(source,values())
