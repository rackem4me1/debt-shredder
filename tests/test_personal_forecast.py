from datetime import datetime, timezone
from decimal import Decimal as D
import pytest
from SCHEMA import assumed_default
from dashboard.multimonth import example
from dashboard.forecast_terms import change_terms
from dashboard.personal_forecast import calculate
from dashboard.scenarios import save_scenario
from engine.common import reconstruct
from test_dashboard_manual import web,call
from test_restore import hidden,post


def source():
    s=example()
    s=reconstruct(s,debts=(reconstruct(s.debts[0],cycles=s.debts[0].cycles[:2]),),requests=(),end=datetime(2026,1,15,tzinfo=timezone.utc))
    return change_terms(s,{'name':s.name,'formula':'understood','floor_0':'25','rate_0':'1','rounding_0':'ROUND_HALF_UP','provenance_0':'user_provided_estimate','date_0':''})


def values():
    v={'end':'2026-03-31','ack':'understood','priority_0':'0'}
    for j,(start,end,due) in enumerate((('2026-02-01','2026-02-28','2026-03-20'),('2026-03-01','2026-03-31','2026-04-20'))):
        v.update({f'c_0_{j}_{key}':value for key,value in {'start':start,'end':end,'statement':end,'due':due}.items()})
    for j,month in enumerate((1,2,3)):
        v.update({f'p_0_{j}_{key}':f'2026-{month:02d}-20' for key in ('initiated','credited','debited','settled')})
    return v


def test_personal_schedule_matches_independent_three_statement_fixture():
    r,plans,end=calculate(source(),values())
    assert [d.accepted for d in r.decisions]==list(map(D,['25','40.76','37.72']))
    assert r.debts[0].account.total_balance()==D('985.33')
    assert r.liquidity.points[-1].positions[0].cleared==D('296.52')
    assert r.liquidity.end.date().isoformat()=='2026-06-18'


@pytest.mark.parametrize('field,value',[('c_0_0_start','2026-02-02'),('end','2027-12-31'),('end','2026-04-01'),
 ('p_0_0_credited','2026-01-19'),('priority_0','-1'),('ack','')])
def test_ambiguous_dates_and_missing_scope_rejected(field,value):
    with pytest.raises(ValueError):calculate(source(),values()|{field:value})


def test_assumed_minimum_terms_do_not_silently_become_explicit():
    s=source();debt=s.debts[0]
    s=reconstruct(s,debts=(reconstruct(debt,account=reconstruct(debt.account,minimum_payment_rate=assumed_default(D('.01')))),))
    with pytest.raises(ValueError,match='Review future minimum terms'):calculate(s,values())


def test_recurring_cash_expands_through_new_horizon():
    from dashboard.cash_inputs import ManualCashEvent, expand_cash_events, cash_horizon
    schedule=ManualCashEvent(kind='income',label='Paycheck',amount='10',date='2026-01-02',cadence='weekly')
    s=source();events=(schedule,)
    s=reconstruct(s,manual_cash_schedules=events,cash_plans=expand_cash_events(events,s.start,cash_horizon(s.start,s.end,s.requests),'UTC'))
    r,plans,_=calculate(s,values())
    assert len(plans)>len(s.cash_plans)
    assert plans[-1].credited_at.date().isoformat()=='2026-06-12'
    assert r.liquidity.points[-1].positions[0].cleared==D('536.52')


def test_preview_keeps_original_and_errors_preserve_inputs(web):
    s=source();id_='f'*32;path=web[1]/(id_+'.json');save_scenario(s,path);before=path.read_bytes()
    status,_,html=call(web,'GET','/personal-forecast/'+id_)
    assert status==200
    fields=hidden(html)|values()
    status,_,html=post(web,'/personal-forecast-preview',fields)
    assert status==200 and '$296.52' in html and 'This preview is not saved' in html
    assert path.read_bytes()==before and len(list(web[1].glob('*.json')))==1
    status,_,html=post(web,'/personal-forecast-preview',fields|{'c_0_0_start':'2026-02-02'})
    assert status==422 and 'value="2026-02-02"' in html
    assert post(web,'/personal-forecast-preview',fields|{'fingerprint':'old'})[0]==409


def test_two_cards_share_cash_without_reusing_original_requests():
    s=source();a=s.debts[0]
    b=reconstruct(a,account=reconstruct(a.account,account_id='second',
        segments=tuple(reconstruct(seg,account_id='second') for seg in a.account.segments),
        allocation_rule=reconstruct(a.account.allocation_rule,account_id='second')),
        cycles=tuple(reconstruct(c,account_id='second') for c in a.cycles),
        initial_minimum=reconstruct(a.initial_minimum,account_id='second'))
    s=reconstruct(s,debts=(a,b),card_names=('First','Second'))
    v=values()
    for key,value in list(v.items()):
        if key.startswith(('c_0_','p_0_')):v[key.replace('_0_','_1_',1)]=value
    v['priority_1']='1'
    r,_,_=calculate(s,v)
    assert sum(d.accepted for d in r.decisions)==D('206.96')
    assert r.liquidity.points[-1].positions[0].cleared==D('193.04')
    with pytest.raises(ValueError,match='priorities'):calculate(s,v|{'priority_1':'0'})
