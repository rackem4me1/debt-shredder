from datetime import datetime, timezone
from decimal import Decimal as D
from dashboard.manual import ManualScenario
from dashboard.timeline import timeline_data, render_timeline
from dashboard.scenarios import save_scenario
from engine.common import reconstruct
from engine.liquidity import CashPlan, CashKind, CashOpening
from test_dashboard_manual import fields, web, call


def sample(**changes):
    return ManualScenario(**(fields()|changes)).scenario()


def test_payment_stages_use_accepted_amount_and_engine_cash_snapshots():
    scenario=sample()
    result=timeline_data(scenario)
    points=result['points']
    assert len(points)==6
    assert points[0]['opening'] and not points[0]['events']
    assert [p['events'][0]['label'] for p in points[1:-1]]==[
        'Payment submitted','Card receives payment','Money leaves checking','Payment settles']
    assert all(D(e['amount'])==120 for p in points for e in p['events'])
    assert [D(p['positions'][0]['cleared']) for p in points]==[150,150,150,30,30,30]
    assert [D(p['positions'][0]['committed']) for p in points]==[0,120,120,0,0,0]
    assert D(result['unfunded'][0]['unmet'])==80
    assert not result['due_checks'][0]['missed']
    engine=scenario.project()
    assert [p['at'] for p in points]==[p.at.isoformat() for p in engine.liquidity.points]
    assert [p['in_transit'] for p in points]==[str(p.in_transit) for p in engine.liquidity.points]


def test_same_time_stages_are_one_batch_not_invented_intermediate_balances():
    result=timeline_data(sample(credited='2026-01-02',debited='2026-01-02',settled='2026-01-02'))
    assert len(result['points'])==3
    point=result['points'][1]
    assert len(point['events'])==4
    assert D(point['positions'][0]['cleared'])==30
    assert D(point['positions'][0]['committed'])==0


def test_start_time_events_do_not_leak_into_opening_snapshot():
    result=timeline_data(sample(initiated='2026-01-01'))
    opening,first=result['points'][:2]
    assert opening['at']==first['at']
    assert not opening['events'] and first['events']
    assert D(opening['positions'][0]['committed'])==0
    assert D(first['positions'][0]['committed'])==120


def test_late_credit_keeps_missed_due_visible():
    result=timeline_data(sample(credited='2026-01-21',debited='2026-01-22',settled='2026-01-23'))
    assert result['due_checks']==[dict(account_id='card',on='2026-01-20',zone='America/Chicago',missed=True)]
    assert any(e['label']=='Card receives payment' for p in result['points'] for e in p['events'])


def test_no_payment_does_not_invent_lifecycle_events():
    result=timeline_data(sample(payment_amount='0'))
    assert len(result['points'])==2
    assert not any(p['events'] for p in result['points'])
    assert result['due_checks'][0]['missed']
    assert not result['unfunded']


def test_unfunded_payment_has_no_cash_events():
    result=timeline_data(sample(cash='30'))
    assert D(result['unfunded'][0]['unmet'])==200
    assert not any(p['events'] for p in result['points'])


def transfer_scenario(kind=CashKind.TRANSFER):
    at=lambda day:datetime(2026,1,day,12,tzinfo=timezone.utc)
    scenario=sample(payment_amount='0')
    plan=CashPlan(plan_id='move',kind=kind,amount='50',source_account_id='checking',destination_account_id='savings',
        initiated_at=at(2),debited_at=at(3),credited_at=at(4),settled_at=at(5))
    return reconstruct(scenario,openings=scenario.openings+(CashOpening(account_id='savings',cleared='0',floor='0'),),cash_plans=(plan,))


def test_transfer_keeps_transit_hold_and_conservation_visible():
    scenario=transfer_scenario()
    result=timeline_data(scenario)
    assert any(D(point['in_transit'])==50 for point in result['points'])
    assert any(D(row['held'])==50 for point in result['points'] for row in point['positions'])
    for point in result['points']:
        assert sum(D(row['cleared']) for row in point['positions'])+D(point['in_transit'])==150
    html=render_timeline(scenario)
    assert 'not an expense' in html and 'not income' in html


def test_sinking_contribution_reserve_stays_at_destination():
    result=timeline_data(transfer_scenario(CashKind.CONTRIBUTION))
    final={p['account_id']:p for p in result['points'][-1]['positions']}
    assert D(final['checking']['reserved'])==10
    assert D(final['savings']['reserved'])==50
    assert 'becomes reserved cash' in render_timeline(transfer_scenario(CashKind.CONTRIBUTION))


def test_no_due_checks_claimed_beyond_debt_horizon():
    result=timeline_data(sample(end='2026-01-10'))
    assert not result['due_checks']
    assert result['cash_end']>result['debt_end']
    assert 'No known minimum due date falls inside' in render_timeline(sample(end='2026-01-10'))


def test_names_and_event_ids_are_escaped():
    scenario=sample(name='<script>bad</script>')
    scenario=reconstruct(scenario,requests=(reconstruct(scenario.requests[0],request_id='<script>request</script>'),))
    html=render_timeline(scenario)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'do not add those stages together' in html


def test_saved_timeline_is_read_only_and_routes_are_bounded(web):
    id_='e'*32
    path=save_scenario(sample(),web[1]/(id_+'.json'))
    before=path.read_bytes()
    status,_,html=call(web,'GET','/timeline/'+id_)
    assert status==200 and 'Back to result' in html and 'Payment submitted' in html
    assert path.read_bytes()==before
    assert 'See the payment timeline' in call(web,'GET','/scenario/'+id_)[2]
    assert call(web,'GET','/timeline/'+'f'*32)[0]==404
    assert call(web,'GET','/timeline/../../SCHEMA.py')[0]==404


def test_demo_timeline_does_not_create_saved_files(web):
    status,_,html=call(web,'GET','/demo/timeline')
    assert status==200 and 'Synthetic example' in html and 'minimum-a' in html
    assert not list(web[1].glob('*.json'))


def test_income_expense_and_reserve_events_are_distinguished():
    scenario=sample(payment_amount='0')
    plans=[]
    for day,kind,amount in [(2,CashKind.INCOME,'20'),(3,CashKind.EXPENSE,'5'),(4,CashKind.RESERVE,'10')]:
        at=datetime(2026,1,day,12,tzinfo=timezone.utc)
        plan=dict(plan_id=kind.value,kind=kind,amount=amount,initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
        plan['destination_account_id' if kind==CashKind.INCOME else 'source_account_id']='checking'
        plans.append(CashPlan(**plan))
    result=timeline_data(reconstruct(scenario,cash_plans=tuple(plans)))
    labels=[e['label'] for point in result['points'] for e in point['events']]
    assert labels==['Income arrives','Expense paid','Cash reserved']
    final=result['points'][-1]['positions'][0]
    assert D(final['cleared'])==165 and D(final['reserved'])==20
