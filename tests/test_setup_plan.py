from datetime import date,time
from decimal import Decimal as D
from uuid import uuid4
from html import unescape
from urllib.parse import urlencode
import re,json
import pytest
from dashboard import payoff_setup as setup,setup_plan as plan
from engine.common import reconstruct
from engine.mixed_payoff import compare_mixed_payoff
from demo_payoff import mixed_example
from SCHEMA import DayCountConvention as Day,RoundingMode as Round,SemimonthlyShortMonthRule as Short
from test_dashboard_manual import web,call,token


def complete(tmp_path):
    identifier=setup.start(tmp_path,setup.Counts(checking=1,savings=0,cards=2,loans=1),practice=True)
    w=setup.load(tmp_path,identifier);accounts=list(w.accounts);asof=date(2025,12,31)
    accounts[0]=reconstruct(accounts[0],name='Everyday checking',balance='400',floor='100',reserved='50',balance_date=asof)
    for i,balance,apr in ((1,'1000','24'),(2,'500','12')):
        accounts[i]=reconstruct(accounts[i],name='Card '+str(i),balance=balance,apr=apr,balance_date=asof,minimum='25',due_date=date(2026,1,20),payment_from='checking-1',promo='none')
    accounts[3]=reconstruct(accounts[3],name='Installment loan',balance='1000',apr='20',note_rate='12',minimum='100',due_date=date(2026,1,20),payment_from='checking-1',loan_type='simple',prepayment='principal',balance_type='principal',balance_date=asof)
    w=reconstruct(w,accounts=tuple(accounts));setup.write(tmp_path,identifier,w,previous=setup.load(tmp_path,identifier))
    settings=plan.Settings(balance_date=asof,end=date(2026,12,31),timezone='UTC',primary='checking-1',target='300',first_payment=date(2026,1,20),cadence='monthly',payment_time=time(),credit_days=0,debit_days=0,settlement_days=0,short_month=Short.CLAMP_TO_LAST_DAY_OF_MONTH,reviewed='yes',pending='none')
    terms=tuple(plan.Terms(account_id='card-'+str(i),day_count=Day.ACTUAL_365,rounding=Round.HALF_UP,accrued='0',ordinary='yes',previous_start=date(2025,12,1),previous_close=asof,next_close=date(2026,1,31),next_due=date(2026,2,20),close_day=31,due_day=20,original_minimum='25',minimum_floor='25',minimum_rate='1') for i in (1,2))
    terms+=(plan.Terms(account_id='loan-1',day_count=Day.ACTUAL_365,rounding=Round.HALF_UP,accrued='0',fees='0',due_day=20,monthly='yes'),)
    flows=(plan.Flow(flow_id=uuid4().hex,kind='income',name='Monthly income',amount='1200',first_date=date(2026,1,1),cadence='monthly',clock=time(),destination='checking-1',include='yes'),
        plan.Flow(flow_id=uuid4().hex,kind='expense',name='Living costs',amount='900',first_date=date(2026,1,2),cadence='monthly',clock=time(),source='checking-1',include='yes'))
    return identifier,w,plan.Planning(settings=settings,terms=terms,flows=flows)


def oracle():
    # Account IDs break equal-rate ties. Match IDs as well as financial terms;
    # relabeling a loan/card tie can legitimately change posting dates by a month.
    from engine.mixed_payoff import MixedPayoffInputs
    ids={'high-rate':'card-1','small-balance':'card-2','sample-loan':'loan-1','checking':'checking-1'}
    def rename(value):
        if isinstance(value,dict):return {k:rename(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [rename(v) for v in value]
        return ids.get(value,value) if isinstance(value,str) else value
    return compare_mixed_payoff(MixedPayoffInputs.model_validate(rename(mixed_example().model_dump())))


def hidden(html):return {k:unescape(v) for k,v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">',html)}
def post(web,path,values,**headers):return call(web,'POST',path,urlencode(values),{'Content-Type':'application/x-www-form-urlencoded'}|headers)


def test_wizard_to_real_engine_matches_independent_existing_mixed_example(tmp_path):
    _,w,p=complete(tmp_path);before=w.model_dump_json();assert not plan.missing(w,p)
    run=plan.build(w,p);actual=compare_mixed_payoff(run.inputs);expected=oracle()
    for a,e in zip(actual.results,expected.results):
        assert (a.total_paid,a.interest_total,a.payoff_date,a.all_minimums_met)==(e.total_paid,e.interest_total,e.payoff_date,e.all_minimums_met)
        assert [v.cleared for v in a.liquidity.points[-1].positions]==[v.cleared for v in e.liquidity.points[-1].positions]
    assert w.model_dump_json()==before
    assert run.account_labels[0].name=='Everyday checking'
    assert run.inputs.start.date()==date(2026,1,1)
    assert all(f.initiated_at.date()>date(2025,12,31) for f in run.inputs.cash_plans)
    assert not w.accounts[1].credit_limit and not w.accounts[0].apy


@pytest.mark.parametrize('case',['promo','unknown_promo','precomputed','paid_ahead','unknown_principal','stale','missing_route','missing_accrued','missing_cash','pending','not_reviewed','prior_income'])
def test_missing_or_unsupported_facts_never_become_a_plan(tmp_path,case):
    _,w,p=complete(tmp_path);accounts=list(w.accounts)
    if case=='promo':accounts[1]=reconstruct(accounts[1],promo='deferred')
    if case=='unknown_promo':accounts[1]=reconstruct(accounts[1],promo='unknown')
    if case=='precomputed':accounts[3]=reconstruct(accounts[3],loan_type='precomputed')
    if case=='paid_ahead':accounts[3]=reconstruct(accounts[3],prepayment='paid_ahead')
    if case=='unknown_principal':accounts[3]=reconstruct(accounts[3],balance_type='unknown')
    if case=='stale':accounts[0]=reconstruct(accounts[0],balance_date=date(2025,12,30))
    if case=='missing_route':accounts[1]=reconstruct(accounts[1],payment_from=None)
    if case=='missing_accrued':p=plan.update_terms(p,reconstruct(p.terms[0],accrued=None))
    if case=='missing_cash':p=plan.update_flow(p,reconstruct(p.flows[0],clock=None))
    if case=='pending':p=reconstruct(p,settings=reconstruct(p.settings,pending='present'))
    if case=='not_reviewed':p=reconstruct(p,settings=reconstruct(p.settings,reviewed='no'))
    if case=='prior_income':p=plan.update_flow(p,reconstruct(p.flows[0],first_date=date(2025,12,31)))
    w=reconstruct(w,accounts=tuple(accounts))
    assert plan.missing(w,p)
    with pytest.raises(ValueError):plan.build(w,p)


def test_cash_accounts_do_not_pool_and_delayed_transfer_remains_internal(tmp_path):
    _,w,p=complete(tmp_path)
    w=setup.add_account(w,'savings');accounts=list(w.accounts)
    savings=next(i for i,a in enumerate(accounts) if a.kind=='savings')
    accounts[savings]=reconstruct(accounts[savings],balance='100',floor='100',reserved='0',balance_date=p.settings.balance_date)
    card=next(i for i,a in enumerate(accounts) if a.account_id=='card-1');accounts[card]=reconstruct(accounts[card],payment_from='savings-1')
    w=reconstruct(w,accounts=tuple(accounts))
    cash=plan.Flow(flow_id=uuid4().hex,kind='transfer',name='Fund savings',amount='200',first_date=date(2026,1,20),cadence='once',clock=time(),source='checking-1',destination='savings-1',debit_days=0,credit_days=1,settlement_days=2,include='yes')
    p=plan.update_flow(p,cash);r=compare_mixed_payoff(plan.build(w,p).inputs).results[0]
    assert next(v for v in r.payments if v.account_id=='card-1').total_paid==0
    assert not r.all_minimums_met
    assert r.liquidity.external_income==18000
    assert r.liquidity.external_outflows==13500+r.total_paid


def test_sidecar_round_trip_history_and_stale_save(tmp_path):
    identifier,w,p=complete(tmp_path);original=(tmp_path/'account_wizards'/(identifier+'.json')).read_bytes()
    blank=plan.load(tmp_path,identifier);plan.save(tmp_path,identifier,p,blank)
    assert plan.load(tmp_path,identifier)==p
    with pytest.raises(ValueError):plan.save(tmp_path,identifier,blank,blank)
    plan.save(tmp_path,identifier,reconstruct(p,settings=reconstruct(p.settings,target='200')),p)
    assert list((tmp_path/'account_wizards'/'planning'/'history').glob('*.json'))
    assert (tmp_path/'account_wizards'/(identifier+'.json')).read_bytes()==original


def test_setup_preview_signed_save_reopen_and_source_unchanged(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning());original=setup.load(web[1],identifier)
    status,_,html=call(web,'GET','/setup/'+identifier+'/plan');assert status==200 and 'Calculate my payoff preview' in html
    status,_,html=post(web,'/setup/'+identifier+'/plan/preview',hidden(html))
    assert status==200 and ('$'+str(oracle().results[0].interest_total)) in html and 'Everyday checking' in html
    save_fields=hidden(html)
    assert post(web,'/mixed-payoff/save',save_fields|{'signature':'bad'})[0]==409
    status,headers,_=post(web,'/mixed-payoff/save',save_fields);assert status==303
    status,_,html=call(web,'GET',headers['Location']);assert status==200 and 'Everyday checking' in html and ('$'+str(oracle().results[0].interest_total)) in html
    assert setup.load(web[1],identifier)==original


def test_settings_terms_flow_forms_validation_and_stale_context(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning());csrf=token(web)
    location='/setup/'+identifier+'/plan/settings'
    status,_,html=call(web,'GET',location);assert status==200
    values={k:'' if v is None else str(v) for k,v in p.settings.model_dump(mode='json').items()}
    status,_,_=post(web,location,hidden(html)|values|{'target':'2.001'});assert status==422
    assert post(web,location,hidden(html)|values|{'extra':'bad'})[0]==400
    assert post(web,location,hidden(html)|values|{'token':'wrong'})[0]==403
    assert post(web,location,hidden(html)|values,Origin='https://example.invalid')[0]==403
    assert post(web,location,hidden(html)|values|{'target':'200'})[0]==303
    assert post(web,location,hidden(html)|values)[0]==409
    for suffix in ('terms/card-1','terms/loan-1','flow/'+p.flows[0].flow_id):assert call(web,'GET','/setup/'+identifier+'/plan/'+suffix)[0]==200
    assert call(web,'GET','/setup/'+identifier+'/plan/terms/card-20')[0]==404
    assert call(web,'GET','/setup/'+identifier+'/plan/flow/'+'a'*32)[0]==404


def test_saved_cash_import_is_review_only_does_not_duplicate_debt_or_infer_recurrence(web):
    from dashboard.my_money import MoneySnapshot,save as save_money
    from dashboard.bills import Bill,BillBook
    from dashboard import bills
    identifier,w,p=complete(web[1]);w=reconstruct(w,origin='personal')
    snapshot=MoneySnapshot(reported_on=date(2025,12,31),checking='400',checking_floor='100',bills_box='0',card_balance='1000',statement_minimum='25',statement_due=date(2026,1,20),expected_paycheck='600',expected_payday=date(2026,1,6))
    save_money(web[1],snapshot)
    book=BillBook(source_date=date(2025,12,31),bills=(Bill(bill_id='utility',name='Utility',amount='50',due=date(2026,1,10),route='checking'),
        Bill(bill_id='card-min',name='Card minimum',amount='25',due=date(2026,1,20),route='checking',cash_kind='debt_payment'),
        Bill(bill_id='paid',name='Covered bill',amount='20',due=date(2025,12,30),route='checking',status='covered')))
    (web[1]/'bills_book.json').write_text(book.model_dump_json())
    before={name:(web[1]/name).read_bytes() for name in ('money_snapshot.json','bills_book.json')}
    imported=plan.import_cash(web[1],w,plan.Planning())
    assert len(imported.flows)==3
    pay=next(f for f in imported.flows if f.kind=='income')
    assert pay.cadence is None and pay.destination is None and pay.clock is None and pay.include=='review'
    utility=next(f for f in imported.flows if f.name=='Utility')
    assert utility.cadence=='once' and utility.include=='review' and utility.source is None
    assert next(f for f in imported.flows if f.name=='Covered bill').include=='no'
    assert plan.import_cash(web[1],w,imported)==imported
    for name,raw in before.items():assert (web[1]/name).read_bytes()==raw


def test_http_cash_add_edit_and_terms_save_retains_facts(web):
    identifier,w,p=complete(web[1]);plan.save(web[1],identifier,p,plan.Planning())
    base='/setup/'+identifier+'/plan'
    _,_,html=call(web,'GET',base)
    status,headers,_=post(web,base+'/add-flow',hidden(html)|{'kind':'expense'})
    assert status==303
    location=headers['Location'];current=plan.load(web[1],identifier);f=current.flows[-1]
    _,_,html=call(web,'GET',location)
    values={'name':'Future bill','amount':'12.34','first_date':'2026-02-02','cadence':'monthly','clock':'08:00','until':'','source':'checking-1','include':'yes','notes':'Entered estimate'}
    assert post(web,location,hidden(html)|values)[0]==303
    assert plan.load(web[1],identifier).flows[-1].amount==D('12.34')
    _,_,html=call(web,'GET',base+'/terms/loan-1')
    fields={'day_count':'actual_365_fixed','rounding':'ROUND_HALF_UP','accrued':'0.004','fees':'0','due_day':'20','monthly':'yes'}
    assert post(web,base+'/terms/loan-1',hidden(html)|fields)[0]==303
    assert plan.term_for(plan.load(web[1],identifier),'loan-1').accrued==D('.004')
    assert 'step="any"' in html


@pytest.mark.parametrize('mode',['dates','rounds','card_calendar','loan_calendar','transfer_order','all_zero','zero_loan_installment'])
def test_invalid_calendar_and_money_relationships_fail_before_result(tmp_path,mode):
    _,w,p=complete(tmp_path)
    if mode=='dates':p=reconstruct(p,settings=reconstruct(p.settings,first_payment=date(2025,12,31)))
    if mode=='rounds':p=reconstruct(p,settings=reconstruct(p.settings,first_payment=date(2027,1,20)))
    if mode=='card_calendar':p=plan.update_terms(p,reconstruct(p.terms[0],next_due=date(2026,2,21)))
    if mode=='loan_calendar':p=plan.update_terms(p,reconstruct(p.terms[-1],due_day=21))
    if mode=='transfer_order':p=plan.update_flow(p,plan.Flow(flow_id=uuid4().hex,kind='transfer',name='Bad timing',amount='10',first_date=date(2026,1,3),cadence='once',clock=time(),source='checking-1',destination='checking-1',debit_days=2,credit_days=1,settlement_days=3,include='yes'))
    if mode=='all_zero':w=reconstruct(w,accounts=tuple(reconstruct(a,balance='0') if a.kind in ('card','loan') else a for a in w.accounts))
    if mode=='zero_loan_installment':w=reconstruct(w,accounts=tuple(reconstruct(a,minimum='0') if a.kind=='loan' else a for a in w.accounts))
    with pytest.raises(ValueError):
        run=plan.build(w,p)
        compare_mixed_payoff(run.inputs)


def test_loan_only_and_explicit_zero_debt_skip_are_supported(tmp_path):
    _,w,p=complete(tmp_path)
    w=reconstruct(w,accounts=tuple(reconstruct(a,balance='0',promo='unknown',apr=None) if a.kind=='card' else a for a in w.accounts))
    run=plan.build(w,p);assert not run.inputs.cards and len(run.inputs.loans)==1
    result=compare_mixed_payoff(run.inputs).results[0]
    assert result.status=='paid_off' and result.all_minimums_met
    assert not plan.missing(w,p)


def test_import_reuses_spending_and_transfer_amounts_but_leaves_timing_unknown(web):
    from dashboard import payday_cash,paycheck_week
    identifier,w,p=complete(web[1]);w=reconstruct(w,origin='personal')
    budget=payday_cash.EverydayBudget(food='140',fuel='60')
    (web[1]/'payday_budget.json').write_text(budget.model_dump_json())
    settings=paycheck_week.PaycheckSettings(bills_box_transfer='200',kc_transfer='50',food='140',fuel='60')
    (web[1]/'paycheck_settings.json').write_text(settings.model_dump_json())
    imported=plan.import_cash(web[1],w,plan.Planning())
    assert len(imported.flows)==4
    assert {f.amount for f in imported.flows}=={D('140'),D('60'),D('200'),D('50')}
    assert all(f.first_date is None and f.cadence is None and f.clock is None and f.source is None and f.include=='review' for f in imported.flows)
    assert all(f.debit_days is None and f.credit_days is None and f.settlement_days is None for f in imported.flows if f.kind=='transfer')
    assert plan.import_cash(web[1],w,imported)==imported
    with pytest.raises(ValueError):plan.import_cash(web[1],reconstruct(w,origin='practice'),plan.Planning())


def test_home_resumes_personal_setup_and_preview_rejects_newly_changed_accounts(web):
    identifier,w,p=complete(web[1]);w=reconstruct(w,origin='personal');setup.write(web[1],identifier,w,previous=setup.load(web[1],identifier))
    plan.save(web[1],identifier,p,plan.Planning())
    _,_,html=call(web,'GET','/setup/'+identifier+'/plan');fields=hidden(html)
    old=setup.load(web[1],identifier);new=reconstruct(old,revision=old.revision+1,accounts=tuple(reconstruct(a,name='Renamed checking') if a.kind=='checking' else a for a in old.accounts))
    setup.write(web[1],identifier,new,previous=old)
    assert post(web,'/setup/'+identifier+'/plan/preview',fields)[0]==409
    status,_,html=call(web,'GET','/')
    assert status==200 and 'href="/setup/'+identifier+'/plan"' in html and 'Continue my payoff plan' in html


def test_unused_cash_accounts_stay_outside_plan_without_invented_zero_balances(tmp_path):
    _,w,p=complete(tmp_path);w=setup.add_account(w,'savings')
    unused=next(a for a in w.accounts if a.kind=='savings')
    assert unused.balance is None and unused.floor is None
    assert not plan.missing(w,p)
    run=plan.build(w,p)
    assert not run.inputs.additional_openings
    assert all(f.source_account_id!=unused.account_id and f.destination_account_id!=unused.account_id for f in run.inputs.cash_plans)
    result=compare_mixed_payoff(run.inputs).results[0]
    assert result.total_paid==oracle().results[0].total_paid
    # Adding an actual route makes reconciliation mandatory before using it.
    flow=plan.Flow(flow_id=uuid4().hex,kind='transfer',name='Use savings',amount='100',first_date=date(2026,1,3),cadence='once',clock=time(),source=unused.account_id,destination='checking-1',debit_days=0,credit_days=0,settlement_days=0,include='yes')
    assert plan.missing(w,plan.update_flow(p,flow))
    with pytest.raises(ValueError):plan.build(w,plan.update_flow(p,flow))


def test_balance_review_distinguishes_unknown_zero_outside_and_mismatched_dates(tmp_path):
    from dashboard.setup_plan_view import overview
    identifier,w,p=complete(tmp_path);w=setup.add_account(w,'savings')
    accounts=list(w.accounts)
    accounts=[reconstruct(a,balance=None,balance_date=None,name='<Unknown card>') if a.account_id=='card-1'
              else reconstruct(a,balance='0') if a.account_id=='card-2'
              else reconstruct(a,balance_date=date(2025,12,30)) if a.kind=='checking'
              else a for a in accounts]
    w=reconstruct(w,accounts=tuple(accounts));before=w.model_dump_json(),p.model_dump_json()
    html=overview(w,p,identifier,'test')
    assert '<Unknown card>' not in html and '&lt;Unknown card&gt;' in html
    assert 'Update or reconcile date' in html and 'Dec 30, 2025' in html
    assert 'Known zero debt — no payments' in html and '$0.00' in html
    assert 'Balance needed' in html and '<td>Unknown</td>' in html
    assert 'Outside this estimate' in html and 'Accounts outside this estimate' in html
    assert 'not live bank balances' in html
    assert (w.model_dump_json(),p.model_dump_json())==before


def test_changing_starting_date_does_not_refresh_balances_or_cash_events(tmp_path):
    from dashboard.setup_plan_view import overview
    identifier,w,p=complete(tmp_path)
    updated=reconstruct(p,settings=reconstruct(p.settings,balance_date=date(2026,1,1)))
    html=overview(w,updated,identifier,'test')
    assert 'Common starting date: Jan 01, 2026' in html
    assert 'Dec 31, 2025' in html and html.count('Update or reconcile date')==4
    assert 'already-received money is not added again' in html
    assert 'Calculate my payoff preview' not in html and 'Your next step' in html
    assert 'href="/setup/'+identifier+'/account/0">Continue this step' in html
    assert all(a.balance_date==date(2025,12,31) for a in w.accounts)
    assert updated.flows==p.flows
    with pytest.raises(ValueError):plan.build(w,updated)


def test_http_review_is_read_only_and_next_step_follows_remaining_checks(web):
    identifier,w,p=complete(web[1]);base='/setup/'+identifier+'/plan'
    before={str(f):f.read_bytes() for f in web[1].rglob('*.json')}
    status,_,html=call(web,'GET',base)
    assert status==200 and 'Your next step' in html
    assert 'href="'+base+'/settings">Continue this step' in html
    assert {str(f):f.read_bytes() for f in web[1].rglob('*.json')}==before

    assert not plan.path(web[1],identifier).exists()
    plan.save(web[1],identifier,p,plan.Planning())
    before={str(f):f.read_bytes() for f in web[1].rglob('*.json')}
    status,_,html=call(web,'GET',base)
    assert status==200 and 'Your next step' not in html
    assert 'Calculate my payoff preview' in html and 'Date matches the starting date' in html
    assert {str(f):f.read_bytes() for f in web[1].rglob('*.json')}==before


def test_cash_review_shows_saved_schedule_routes_and_unknowns_without_inventing_dates(tmp_path):
    from dashboard.setup_plan_view import overview
    identifier,w,p=complete(tmp_path)
    w=reconstruct(w,accounts=tuple(reconstruct(a,name='<Everyday>') if a.kind=='checking' else a for a in w.accounts))
    transfer=plan.Flow(flow_id=uuid4().hex,kind='transfer',name='Future transfer',amount=None,include='review')
    stopped=reconstruct(p.flows[1],until=date(2026,6,2))
    p=plan.update_flow(plan.update_flow(p,stopped),transfer)
    before=p.model_dump_json()
    html=overview(w,p,identifier,'test')
    assert 'Jan 01, 2026 · Monthly · Into &lt;Everyday&gt;' in html
    assert 'Stops Jun 02, 2026 · From &lt;Everyday&gt;' in html
    assert 'Date not set · Frequency not set · Source not chosen → destination not chosen' in html
    assert '<Everyday>' not in html
    assert p.model_dump_json()==before
