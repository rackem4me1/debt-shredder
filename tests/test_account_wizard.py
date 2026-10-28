from decimal import Decimal as D
from html import unescape
import json,re
from urllib.parse import urlencode
import pytest
from dashboard import payoff_setup as setup
from engine.common import reconstruct
from test_dashboard_manual import web,call,token


def post(web,path,values,**headers):return call(web,'POST',path,urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'}|headers)


def hidden(html):return {k:unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}


def create(web,**counts):
    status,headers,_=post(web,'/setup/start',{'token':token(web),'checking':'1','savings':'1','cards':'1','loans':'1'}|counts)
    assert status==303
    return headers['Location'].split('/')[2]


def form_values(wizard,step):
    a=wizard.accounts[step];values=a.model_dump(mode='json')
    return {k:'' if values[k] is None else str(values[k]) for k in setup.fields(a)}


def test_counts_build_exact_account_types_unknown_values_and_no_debt_defaults(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=2,savings=3,cards=4,loans=2))
    wizard=setup.load(tmp_path,identifier)
    assert len(wizard.accounts)==11
    assert [a.kind for a in wizard.accounts]==['checking']*2+['savings']*3+['card']*4+['loan']*2
    assert all(a.balance is None and a.apr is None and a.floor is None and a.reserved is None for a in wizard.accounts)
    assert wizard.accounts[5].promo=='unknown'
    assert wizard.accounts[-1].loan_type==wizard.accounts[-1].prepayment=='unknown'


@pytest.mark.parametrize('counts',[dict(checking=0,savings=0,cards=0,loans=0),dict(checking=20,savings=1,cards=1,loans=1),dict(checking=-1,savings=0,cards=1,loans=0)])
def test_invalid_account_counts_rejected(counts):
    with pytest.raises(ValueError):setup.Counts(**counts)


def test_bank_save_and_resume_preserves_unknown_vs_known_zero_and_history(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=1,savings=0,cards=1,loans=0));original=setup.load(tmp_path,identifier)
    values=form_values(original,0)|{'name':'Household checking','balance':'125.50','balance_date':'2026-10-25','floor':'0','reserved':''}
    changed=setup.change(original,0,values,'later');changed=reconstruct(changed,revision=1)
    setup.write(tmp_path,identifier,changed,previous=original)
    saved=setup.load(tmp_path,identifier)
    assert saved.accounts[0].balance==D('125.50') and saved.accounts[0].floor==0 and saved.accounts[0].reserved is None
    assert saved.next_step==0 and saved.reviewed==('checking-1',)
    assert list((tmp_path/'account_wizards'/'history').glob('*.json'))
    with pytest.raises(ValueError):setup.write(tmp_path,identifier,original,previous=original)
    assert setup.load(tmp_path,identifier)==saved


def test_promotions_and_precomputed_loans_remain_flagged_and_are_not_projected(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=0,savings=0,cards=1,loans=1));wizard=setup.load(tmp_path,identifier)
    values=form_values(wizard,0)|{'balance':'1000','apr':'29.99','credit_limit':'1500','promo':'deferred','promo_balance':'800','promo_apr':'0','promo_end':'2027-01-31'}
    updated=setup.change(wizard,0,values,'next')
    assert updated.accounts[0].promo_apr==0 and updated.accounts[0].post_promo_apr is None
    html=setup.summary(updated,identifier,'test-token')
    assert 'promotional balance accrues interest' in html and 'no ordinary-rate payoff assumption' in html
    loan=form_values(updated,1)|{'loan_type':'precomputed','prepayment':'rebate','balance':'2500'}
    updated=setup.change(updated,1,loan,'next')
    assert updated.accounts[1].loan_type=='precomputed' and updated.accounts[1].note_rate is None
    assert 'supported servicer schedule' in setup.summary(updated,identifier,'test-token')
    assert not list(tmp_path.glob('mixed_payoff_runs/*'))


def test_rejects_contradictory_promotions_unknown_routes_and_invalid_financial_values(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=1,savings=0,cards=1,loans=0));wizard=setup.load(tmp_path,identifier)
    for changes in ({'promo':'none','promo_balance':'100'},{'promo':'zero','balance':'50','promo_balance':'100'},{'apr':'-1'},
        {'balance':'10.001'},{'payment_from':'missing'},{'name':'  '}):
        with pytest.raises(ValueError):setup.change(wizard,1,form_values(wizard,1)|changes,'next')
    raw=json.loads(wizard.model_dump_json());raw['accounts'][0]['balance']=1.1
    with pytest.raises(ValueError):setup.parse(json.dumps(raw).encode())
    # Overdrafts and over-limit cards are facts, not malformed data.
    assert setup.change(wizard,0,form_values(wizard,0)|{'balance':'-10'},'next').accounts[0].balance==-10
    updated=setup.change(wizard,1,form_values(wizard,1)|{'balance':'150','credit_limit':'100'},'next')
    assert 'Balance exceeds' in setup.summary(updated,identifier,'test-token')


def test_add_account_preserves_ids_funding_and_existing_answers(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=1,savings=0,cards=1,loans=0));wizard=setup.load(tmp_path,identifier)
    wizard=setup.change(wizard,1,form_values(wizard,1)|{'payment_from':'checking-1','name':'Daily card'},'next')
    updated=setup.add_account(wizard,'checking')
    assert [a.account_id for a in updated.accounts]==['checking-1','checking-2','card-1']
    assert updated.accounts[-1].payment_from=='checking-1' and updated.accounts[-1].name=='Daily card'
    assert updated.next_step==1


def test_browser_routes_save_unknowns_later_reload_and_download(web):
    identifier=create(web)
    wizard=setup.load(web[1],identifier)
    status,headers,html=call(web,'GET','/setup/'+identifier+'/account/0')
    assert status==200 and headers['Cache-Control']=='no-store'
    values=hidden(html)|form_values(wizard,0)|{'intent':'later','balance':'200','floor':'100'}
    status,headers,_=post(web,'/setup/'+identifier+'/account/0',values)
    assert status==303 and headers['Location']=='/setup/'+identifier
    status,_,html=call(web,'GET',headers['Location'])
    assert status==200 and 'date not confirmed' in html and '$200.00' in html
    assert 'Continue my setup' in html
    status,headers,raw=call(web,'GET','/setup/'+identifier+'/backup.json')
    assert status==200 and setup.parse(raw.encode())==setup.load(web[1],identifier)
    assert '4 accounts' in call(web,'GET','/setup/drafts')[2]
    assert post(web,'/setup/'+identifier+'/account/0',values)[0]==409


def test_wizard_post_protections_errors_and_original_data_unchanged(web):
    identifier=create(web);wizard=setup.load(web[1],identifier)
    _,_,html=call(web,'GET','/setup/'+identifier+'/account/2');fields=hidden(html)|form_values(wizard,2)|{'intent':'next'}
    assert post(web,'/setup/'+identifier+'/account/2',fields|{'token':'wrong'})[0]==403
    assert post(web,'/setup/'+identifier+'/account/2',fields,Origin='https://example.invalid')[0]==403
    assert post(web,'/setup/'+identifier+'/account/2',fields|{'unexpected':'field'})[0]==400
    status,_,body=post(web,'/setup/'+identifier+'/account/2',fields|{'balance':'2.001'})
    assert status==422 and '2.001' in body and 'role="alert"' in body
    assert setup.load(web[1],identifier)==wizard
    assert call(web,'GET','/setup/'+identifier+'/account/99')[0]==404
    assert call(web,'GET','/setup/'+'f'*32)[0]==404
    assert 'Continue my payoff plan' in call(web,'GET','/')[2]


def test_http_add_and_safe_name_escaping(web):
    identifier=create(web,checking='0',savings='0',loans='0');wizard=setup.load(web[1],identifier)
    _,_,html=call(web,'GET','/setup/'+identifier+'/account/0')
    status,headers,_=post(web,'/setup/'+identifier+'/account/0',hidden(html)|form_values(wizard,0)|{'intent':'later','name':'<script>unsafe</script>'})
    assert status==303
    status,_,html=call(web,'GET','/setup/'+identifier)
    assert '&lt;script&gt;' in html and '<script>unsafe' not in html
    status,headers,_=post(web,'/setup/'+identifier+'/add',hidden(html)|{'kind':'savings'})
    assert status==303
    assert setup.load(web[1],identifier).counts.savings==1


def test_reuse_keeps_original_dates_and_does_not_refresh_older_card_as_of(web):
    from dashboard.my_money import MoneySnapshot,save,load
    from datetime import date
    snapshot=MoneySnapshot(reported_on=date(2026,10,20),checking='200',checking_floor='50',bills_box='300',card_balance='500',statement_minimum='25',
        statement_due=date(2026,11,9),expected_paycheck='600',expected_payday=date(2026,10,27))
    save(web[1],snapshot);raw=(web[1]/'money_snapshot.json').read_bytes()
    identifier=create(web,reuse='yes');wizard=setup.load(web[1],identifier)
    assert wizard.accounts[0].balance_date==date(2026,10,20) and wizard.accounts[0].balance==200
    assert wizard.accounts[2].balance==500 and wizard.accounts[2].balance_date is None
    assert wizard.accounts[2].apr is None and wizard.accounts[2].promo=='unknown'
    assert (web[1]/'money_snapshot.json').read_bytes()==raw


def test_practice_is_labeled_and_does_not_reuse_personal_data(web):
    csrf=token(web)
    status,headers,_=post(web,'/setup/practice',{'token':csrf})
    assert status==303
    identifier=headers['Location'].split('/')[2]
    wizard=setup.load(web[1],identifier)
    assert wizard.origin=='practice' and all(a.balance is None for a in wizard.accounts)
    assert 'Practice setup' in call(web,'GET',headers['Location'])[2]
    assert 'Practice account setup' in call(web,'GET','/setup/drafts')[2]


def test_corrupt_draft_preserved_invalid_start_and_add_count_bounds(web):
    csrf=token(web)
    assert post(web,'/setup/start',{'token':csrf,'checking':'1.0','savings':'0','cards':'0','loans':'0'})[0]==422
    with pytest.raises(ValueError):setup.Counts(checking=True,savings=0,cards=0,loans=0)
    identifier=create(web,checking='20',savings='0',cards='0',loans='0')
    _,_,html=call(web,'GET','/setup/'+identifier)
    assert post(web,'/setup/'+identifier+'/add',hidden(html)|{'kind':'checking'})[0]==422
    path=setup.path_for(web[1],identifier);path.write_text('bad data')
    assert call(web,'GET','/setup/'+identifier)[0]==422
    assert path.read_text()=='bad data' and 'file has been kept' in call(web,'GET','/setup/drafts')[2]
