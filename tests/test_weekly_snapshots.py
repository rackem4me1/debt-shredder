from decimal import Decimal as D
import json
from pathlib import Path
import pytest
from dashboard import weekly_check as check,weekly_snapshots as snapshots
from engine.common import reconstruct
from test_weekly_check import example
from test_setup_plan import hidden,post
from test_dashboard_manual import web,call


def all_files(directory):return {str(p.relative_to(directory)):p.read_bytes() for p in directory.rglob('*.json')}


def test_saved_snapshot_round_trip_retains_source_and_one_time_choices(tmp_path):
    source=example();value=snapshots.prepare(source,'back=20&spend=5&weeks=6')
    identifier=snapshots.save(tmp_path,value)
    assert snapshots.load(tmp_path,identifier)==value
    assert check.calculate(value.report,value.query)['goal_end']==235
    assert check.calculate(value.report,value.query)['tested_total']==350
    second=snapshots.save(tmp_path,value)
    assert second!=identifier and snapshots.load(tmp_path,identifier)==value


def test_snapshot_collision_never_replaces_a_saved_comparison(tmp_path,monkeypatch):
    value=snapshots.prepare(example());identifier=snapshots.save(tmp_path,value);raw=snapshots.location(tmp_path,identifier).read_bytes()
    class Collision:hex=identifier
    monkeypatch.setattr(snapshots,'uuid4',lambda:Collision())
    with pytest.raises(FileExistsError):snapshots.save(tmp_path,value)
    assert snapshots.location(tmp_path,identifier).read_bytes()==raw
    assert not list((tmp_path/'weekly_comparisons').glob('.weekly-*'))


@pytest.mark.parametrize('mutation',['root_bool','child_bool','extra','float','wrong_format','noncanonical','oversize','duplicate'])
def test_invalid_saved_inputs_are_rejected(mutation):
    data=snapshots.prepare(example()).model_dump(mode='json')
    if mutation=='root_bool':data['version']=True
    if mutation=='child_bool':data['report']['version']=True
    if mutation=='extra':data['unexpected']='ignored'
    if mutation=='float':data['report']['goal']['balance']=80.1
    if mutation=='wrong_format':data['format']='other'
    if mutation=='noncanonical':data['query']='back=20'
    raw=json.dumps(data).encode()
    if mutation=='oversize':raw=b' '*(snapshots.MAX_BYTES+1)
    if mutation=='duplicate':raw=raw.replace(b'"version": 1',b'"version":1,"version":1',1)
    with pytest.raises(ValueError):snapshots.parse(raw)


def test_http_signed_save_reload_download_and_future_source_changes(web):
    source=example();p=web[1]/check.FILENAME;p.write_text(source.model_dump_json());before=p.read_bytes()
    status,_,html=call(web,'GET','/weekly-check?back=20&spend=5&weeks=6')
    assert status==200
    fields=hidden(html)
    assert snapshots.parse(fields['payload'].encode()).report==source
    assert all_files(web[1])=={check.FILENAME:before}
    assert post(web,'/weekly-check/save',fields|{'payload':fields['payload']+' '})[0]==409
    assert post(web,'/weekly-check/save',fields|{'token':'wrong'})[0]==403
    assert post(web,'/weekly-check/save',fields,Origin='https://other.test')[0]==403
    assert post(web,'/weekly-check/save',fields|{'extra':'x'})[0]==400
    status,headers,_=post(web,'/weekly-check/save',fields)
    assert status==303 and headers['Location'].startswith('/weekly-checks/')
    location=headers['Location'];identifier=location.split('/')[-1]
    saved_raw=snapshots.location(web[1],identifier).read_bytes()
    status,_,html=call(web,'GET',location)
    assert status==200 and 'Saved comparison' in html and 'does not refresh as time passes' in html
    assert 'Save this weekly comparison' not in html and 'method="get"' not in html
    assert 'Trial transfer back: $20.00' in html and '6 more weekly contributions' in html
    status,headers,raw=call(web,'GET',location+'/inputs.json')
    assert status==200 and 'application/json' in headers['Content-Type']
    assert snapshots.parse(raw.encode())==snapshots.load(web[1],identifier)
    changed=reconstruct(source,goal=reconstruct(source.goal,balance='100'))
    p.write_text(changed.model_dump_json())
    assert post(web,'/weekly-check/save',fields)[0]==409
    assert call(web,'GET',location)[0]==200
    assert 'Reported fund balance: $80.00' in call(web,'GET',location)[2]
    assert snapshots.location(web[1],identifier).read_bytes()==saved_raw
    assert call(web,'GET',location+'?back=0')[0]==400
    assert 'one-time support $20.00' in call(web,'GET','/weekly-checks')[2]
    p.unlink()
    assert call(web,'GET',location)[0]==200
    assert post(web,'/weekly-check/save',fields)[0]==404


def test_snapshot_routes_keep_corrupt_files_and_reject_unknown_ids(web):
    assert call(web,'GET','/weekly-checks/'+'0'*32)[0]==404
    assert call(web,'GET','/weekly-checks?back=2')[0]==400
    assert call(web,'GET','/weekly-checks/../weekly_system_check.json')[0]==404
    folder=web[1]/'weekly_comparisons';folder.mkdir()
    path=folder/('a'*32+'.json');path.write_text('invalid')
    assert call(web,'GET','/weekly-checks/'+'a'*32)[0]==422
    assert 'file has been kept' in call(web,'GET','/weekly-checks')[2]
    assert path.read_text()=='invalid'


def test_trial_paycheck_is_an_additional_hypothesis_not_replacement_income():
    source=example();before=source.model_dump_json()
    value=snapshots.prepare(source,'pay=312.34&back=20')
    r=check.calculate(value.report,value.query)
    assert len(r['rows'])==4 and r['rows'][-1][0]=='Trial paycheck (illustration)'
    assert r['rows'][-1][1:]==(D('312.34'),D('-37.66'),D('-37.66'))
    assert r['supported_rows'][-1][2]==D('-17.66')
    assert source.model_dump_json()==before and len(source.pay_cases)==3
    assert snapshots.parse(value.model_dump_json().encode())==value
    assert check.calculate(source,'pay=')['custom_pay'] is None
    assert len(check.calculate(source,'pay=0')['rows'])==4


@pytest.mark.parametrize('query',['pay=-1','pay=0.001','pay=NaN','pay=Infinity','pay=1&pay=2','pay=1000000001'])
def test_trial_paycheck_validation(query):
    with pytest.raises(ValueError):snapshots.prepare(example(),query)


def test_csv_preserves_exact_math_negative_margins_and_text_labels():
    import csv
    from io import StringIO
    from decimal import localcontext
    source=example();source=reconstruct(source,pay_cases=(check.PayCase(name='=SUM(1,2)',net='300'),))
    value=snapshots.prepare(source,'back=20&spend=5&weeks=6&pay=312.34')
    expected=snapshots.summary_csv(value)
    with localcontext() as context:
        context.prec=3
        assert snapshots.summary_csv(value)==expected
    rows=list(csv.DictReader(StringIO(expected)))
    assert rows[0]['alternative_scenario']=="'=SUM(1,2)"
    assert rows[0]['unassigned_before_support']=='-50'
    assert rows[0]['unassigned_for_one_supported_week']=='-30'
    assert rows[0]['fund_balance_after_draws']=='55'
    assert rows[0]['projected_fund_balance']=='235'
    assert rows[1]['net_pay']=='312.34' and rows[1]['unassigned_for_one_supported_week']=='-17.66'


def test_http_csv_replays_exact_snapshot_and_is_read_only(web):
    source=example();(web[1]/check.FILENAME).write_text(source.model_dump_json())
    _,_,html=call(web,'GET','/weekly-check?back=20&pay=312.34')
    _,headers,_=post(web,'/weekly-check/save',hidden(html))
    location=headers['Location'];identifier=location.split('/')[-1];before=all_files(web[1])
    status,headers,raw=call(web,'GET',location+'/summary.csv')
    assert status==200 and 'text/csv' in headers['Content-Type']
    assert raw==snapshots.summary_csv(snapshots.load(web[1],identifier))
    assert all_files(web[1])==before


def test_download_routes_require_literal_extensions(web):
    value=snapshots.prepare(example());identifier=snapshots.save(web[1],value)
    assert call(web,'GET','/weekly-checks/'+identifier+'/inputsXjson')[0]==404
    assert call(web,'GET','/weekly-checks/'+identifier+'/summaryXcsv')[0]==404


def test_invalid_trial_retains_entries_for_correction_without_computing_or_saving(web):
    p=web[1]/check.FILENAME;p.write_text(example().model_dump_json());before=all_files(web[1])
    status,_,html=call(web,'GET','/weekly-check?back=81&pay=312.34&pool=30')
    assert status==422 and 'exceed the reported fund balance' in html
    assert 'name="back" value="81"' in html and 'name="pay" value="312.34"' in html
    assert 'Save this weekly comparison' not in html and 'No comparison was calculated' in html
    assert all_files(web[1])==before
    status,_,html=call(web,'GET','/weekly-check?back=81&back=82')
    assert status==422 and 'one value per field' in html and 'value="81"' not in html
    status,_,html=call(web,'GET','/weekly-check?pay=%22%3E%3Cscript%3Ex%3C/script%3E')
    assert status==422 and '<script>x</script>' not in html
    assert all_files(web[1])==before
