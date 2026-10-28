import json
import pytest
from dashboard import setup_backup as backup,payoff_setup as setup,setup_plan as plan
from engine.common import reconstruct
from test_setup_plan import complete,hidden,post
from test_dashboard_manual import web,call


def files(directory):return {str(p.relative_to(directory)):p.read_bytes() for p in directory.rglob('*.json')}


def test_complete_backup_round_trip_preserves_partial_answers_and_source(tmp_path):
    identifier,w,p=complete(tmp_path)
    p=reconstruct(p,settings=reconstruct(p.settings,target=None,reviewed='no'))
    plan.save(tmp_path,identifier,p,plan.Planning());before=files(tmp_path)
    value=backup.capture(tmp_path,identifier)
    assert backup.parse(value.model_dump_json().encode())==value
    restored=backup.restore(tmp_path,value)
    assert restored!=identifier and setup.load(tmp_path,restored)==w and plan.load(tmp_path,restored)==p
    assert all(files(tmp_path)[name]==raw for name,raw in before.items())
    assert plan.missing(setup.load(tmp_path,restored),plan.load(tmp_path,restored))
    again=backup.restore(tmp_path,value)
    assert again not in (identifier,restored)


def test_backup_without_sidecar_does_not_create_one_on_download(tmp_path):
    identifier,w,_=complete(tmp_path);before=files(tmp_path)
    assert backup.capture(tmp_path,identifier).planning==plan.Planning()
    assert files(tmp_path)==before


@pytest.mark.parametrize('mode',['root_version_bool','nested_version_bool','planning_version_float','extra','float_money','unknown_format','duplicate_key','oversize','accounts_only'])
def test_backup_rejects_ambiguous_unsupported_or_corrupt_input(tmp_path,mode):
    identifier,_,_=complete(tmp_path);data=backup.capture(tmp_path,identifier).model_dump(mode='json')
    if mode=='root_version_bool':data['version']=True
    if mode=='nested_version_bool':data['accounts']['version']=True
    if mode=='planning_version_float':data['planning']['version']=1.0
    if mode=='extra':data['unexpected']='discard me'
    if mode=='float_money':data['accounts']['accounts'][0]['balance']=123.4
    if mode=='unknown_format':data['format']='other'
    if mode=='accounts_only':data=data['accounts']
    raw=json.dumps(data).encode()
    if mode=='duplicate_key':raw=raw.replace(b'"version": 1',b'"version": 1, "version": 1',1)
    if mode=='oversize':raw=b' '*(backup.MAX_BYTES+1)
    before=files(tmp_path)
    with pytest.raises(ValueError):backup.parse(raw)
    assert files(tmp_path)==before


def test_failed_inventory_publish_leaves_no_visible_or_partial_copy(tmp_path,monkeypatch):
    identifier,_,_=complete(tmp_path);value=backup.capture(tmp_path,identifier);before=files(tmp_path)
    def fail(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr(setup,'write',fail)
    with pytest.raises(OSError):backup.restore(tmp_path,value)
    assert files(tmp_path)==before


def test_restore_collision_cannot_replace_existing_setup(tmp_path,monkeypatch):
    identifier,_,_=complete(tmp_path);value=backup.capture(tmp_path,identifier);before=files(tmp_path)
    class ExistingID:hex=identifier
    monkeypatch.setattr(backup,'uuid4',lambda:ExistingID())
    with pytest.raises(FileExistsError):backup.restore(tmp_path,value)
    assert files(tmp_path)==before


def test_http_complete_backup_preview_save_retains_original_and_exact_plan(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning());before=files(web[1])
    status,headers,raw=call(web,'GET','/setup/'+identifier+'/complete-backup.json')
    assert status==200 and 'application/json' in headers['Content-Type']
    assert backup.parse(raw.encode())==backup.Backup(accounts=w,planning=p)
    assert files(web[1])==before
    _,_,form=call(web,'GET','/setup/restore');fields=hidden(form)|{'payload':raw}
    status,_,html=post(web,'/setup/restore-preview',fields)
    assert status==200 and 'Nothing has been saved yet' in html and 'practice setup' in html
    assert files(web[1])==before
    reviewed=hidden(html)
    assert post(web,'/setup/restore-save',reviewed|{'payload':reviewed['payload']+' '})[0]==409
    assert files(web[1])==before
    status,headers,_=post(web,'/setup/restore-save',reviewed)
    assert status==303
    restored=headers['Location'].split('/')[2]
    assert restored!=identifier
    assert setup.load(web[1],restored)==w and plan.load(web[1],restored)==p
    assert all(files(web[1])[name]==raw for name,raw in before.items())
    assert call(web,'GET',headers['Location'])[0]==200


def test_http_restore_security_size_and_wrong_format_are_read_only(web):
    identifier,_,_=complete(web[1]);before=files(web[1])
    _,_,html=call(web,'GET','/setup/restore');fields=hidden(html)|{'payload':backup.capture(web[1],identifier).model_dump_json()}
    assert post(web,'/setup/restore-preview',fields|{'token':'wrong'})[0]==403
    assert post(web,'/setup/restore-preview',fields,Origin='https://other.test')[0]==403
    assert post(web,'/setup/restore-preview',fields,Host='other.test')[0]==403
    assert post(web,'/setup/restore-preview',fields|{'extra':'x'})[0]==400
    assert post(web,'/setup/restore-save',fields)[0]==400
    assert post(web,'/setup/restore-preview',fields|{'payload':' '*(backup.MAX_BYTES+1)})[0]==413
    assert post(web,'/setup/restore-preview',fields|{'payload':setup.load(web[1],identifier).model_dump_json()})[0]==422
    assert call(web,'GET','/setup/'+'0'*32+'/complete-backup.json')[0]==404
    assert files(web[1])==before


def test_personal_origin_and_unreviewed_cash_are_preserved_not_promoted(tmp_path):
    identifier,w,p=complete(tmp_path)
    value=backup.Backup(accounts=reconstruct(w,origin='personal'),planning=plan.update_flow(p,reconstruct(p.flows[0],include='review',amount=None)))
    restored=backup.restore(tmp_path,value)
    assert setup.load(tmp_path,restored).origin=='personal'
    restored_flow=next(f for f in plan.load(tmp_path,restored).flows if f.flow_id==p.flows[0].flow_id)
    assert restored_flow.include=='review' and restored_flow.amount is None
    with pytest.raises(ValueError):plan.build(setup.load(tmp_path,restored),plan.load(tmp_path,restored))
