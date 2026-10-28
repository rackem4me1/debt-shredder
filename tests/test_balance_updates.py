from datetime import date
from decimal import Decimal as D
import pytest
from dashboard import payoff_setup as setup,setup_plan as plan
from engine.common import reconstruct
from test_setup_plan import complete,hidden,post
from test_dashboard_manual import web,call


def values(w,p):
    return {a.account_id+'__'+k:('' if getattr(a,k) is None else str(getattr(a,k))) for a in plan.balance_accounts(w,p) for k in plan.balance_fields(a)}


def test_balance_refresh_changes_only_declared_figures_preserves_unknown_and_unused(tmp_path):
    _,w,p=complete(tmp_path);w=setup.add_account(w,'savings');original=p.model_dump_json()
    v=values(w,p)|{'checking-1__balance':'-20.50','checking-1__floor':'0','checking-1__reserved':'','card-1__balance':'0','card-1__balance_date':'2026-01-01','card-2__balance':''}
    changed=plan.change_balances(w,p,v)
    assert changed.revision==w.revision+1 and changed.reviewed==w.reviewed and changed.next_step==w.next_step
    for a,b in zip(w.accounts,changed.accounts):
        assert a.model_dump(exclude=set(plan.balance_fields(a)))==b.model_dump(exclude=set(plan.balance_fields(b)))
        if a.kind=='savings':assert a==b and a.balance is None
    assert changed.accounts[0].balance==D('-20.50') and changed.accounts[0].floor==0 and changed.accounts[0].reserved is None
    assert next(a for a in changed.accounts if a.account_id=='card-1').balance==0
    assert next(a for a in changed.accounts if a.account_id=='card-2').balance is None
    assert p.model_dump_json()==original and p.settings.balance_date==date(2025,12,31)
    with pytest.raises(ValueError):plan.build(changed,p)


@pytest.mark.parametrize('changes',[{'card-1__balance':'-1'},{'checking-1__balance':'1.001'},{'checking-1__floor':'-1'},{'checking-1__reserved':'NaN'},{'card-2__balance_date':'bad-date'},{'card-1__apr':'5'},{'unknown__balance':'12'}])
def test_invalid_batch_never_partly_changes_the_inventory(tmp_path,changes):
    _,w,p=complete(tmp_path);before=w.model_dump_json()
    with pytest.raises(ValueError):plan.change_balances(w,p,values(w,p)|changes)
    assert w.model_dump_json()==before


def test_http_refresh_keeps_planning_and_saved_runs_unchanged_and_rejects_stale_tab(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning())
    base='/setup/'+identifier+'/plan';raw_plan=plan.path(web[1],identifier).read_bytes()
    _,_,html=call(web,'GET',base+'/balances');fields=hidden(html)|values(w,p)
    assert 'checking-1__balance' in html and 'card-1__balance_date' in html
    status,headers,_=post(web,base+'/balances',fields|{'checking-1__balance':'525.25'})
    assert status==303 and headers['Location']==base
    changed=setup.load(web[1],identifier)
    assert changed.accounts[0].balance==D('525.25') and changed.accounts[1:]==w.accounts[1:]
    assert plan.path(web[1],identifier).read_bytes()==raw_plan
    assert list((web[1]/'account_wizards'/'history').glob('*.json'))
    assert not list((web[1]/'mixed_payoff_runs').glob('*.json'))
    assert post(web,base+'/balances',fields)[0]==409
    assert setup.load(web[1],identifier)==changed


def test_invalid_http_refresh_keeps_typed_answers_and_all_original_files(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning());base='/setup/'+identifier+'/plan/balances'
    before={str(f):f.read_bytes() for f in web[1].rglob('*.json')}
    _,_,html=call(web,'GET',base);fields=hidden(html)|values(w,p)
    status,_,html=post(web,base,fields|{'checking-1__balance':'123.45','card-1__balance':'-5'})
    assert status==422 and 'value="123.45"' in html and 'value="-5"' in html
    assert {str(f):f.read_bytes() for f in web[1].rglob('*.json')}==before
    assert post(web,base,fields|{'token':'wrong'})[0]==403
    assert post(web,base,fields,Origin='https://other.test')[0]==403
    assert post(web,base,fields|{'card-1__apr':'1'})[0]==422
    assert {str(f):f.read_bytes() for f in web[1].rglob('*.json')}==before


def test_max_inventory_balance_form_can_save_without_form_field_limit_loss(web):
    identifier=setup.start(web[1],setup.Counts(checking=20,savings=0,cards=20,loans=20),practice=True)
    w=setup.load(web[1],identifier)
    # Route all cash accounts through explicit included cash events; no amounts inferred.
    from uuid import uuid4
    p=plan.Planning(settings=plan.Settings(primary='checking-1'),flows=tuple(plan.Flow(flow_id=uuid4().hex,kind='income',name='Income '+str(i),destination='checking-'+str(i),include='yes',amount='1') for i in range(1,21)))
    plan.save(web[1],identifier,p,plan.Planning());base='/setup/'+identifier+'/plan/balances'
    _,_,html=call(web,'GET',base);fields=hidden(html)|values(w,p)
    assert len(fields)==162
    assert post(web,base,fields)[0]==303
    assert len(setup.load(web[1],identifier).accounts)==60
