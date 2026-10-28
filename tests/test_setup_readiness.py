from datetime import date,time
from uuid import uuid4
import pytest
from dashboard import setup_plan as plan
from dashboard.setup_plan_view import overview
from engine.common import reconstruct
from SCHEMA import SemimonthlyShortMonthRule as Short
from test_setup_plan import complete


@pytest.mark.parametrize('mode,where,phrase',[
    ('past_payment','settings','first payment must follow'),
    ('after_horizon','settings','complete payment round'),
    ('unsettled_round','settings','complete payment round'),
    ('payment_delays','settings','creditor credit'),
    ('overdue_card','account/1','overdue opening payment'),
    ('statement_order','terms/card-1','previous and next statement dates'),
    ('minimum_bounds','terms/card-1','unpaid minimum cannot exceed'),
    ('close_day','terms/card-1','monthly closing day'),
    ('due_day','terms/card-1','following-month due-day rule'),
    ('loan_day','terms/loan-1','monthly due-day rule'),
    ('zero_installment','account/3','positive required installment'),
    ('transfer_delays','flow/','before or on arrival'),
])
def test_conflicting_answers_have_actionable_review_links_before_calculation(tmp_path,mode,where,phrase):
    identifier,w,p=complete(tmp_path);accounts=list(w.accounts);s=p.settings;t=p.terms[0]
    if mode=='past_payment':s=reconstruct(s,first_payment=s.balance_date)
    if mode=='after_horizon':s=reconstruct(s,first_payment=date(2027,1,1))
    if mode=='unsettled_round':s=reconstruct(s,first_payment=s.end,settlement_days=1)
    if mode=='payment_delays':s=reconstruct(s,credit_days=2,debit_days=1,settlement_days=3)
    if mode=='overdue_card':accounts[1]=reconstruct(accounts[1],due_date=s.balance_date)
    if mode=='statement_order':t=reconstruct(t,previous_start=t.previous_close)
    if mode=='minimum_bounds':t=reconstruct(t,original_minimum='20')
    if mode=='close_day':t=reconstruct(t,close_day=30)
    if mode=='due_day':t=reconstruct(t,due_day=21)
    if mode=='loan_day':p=plan.update_terms(p,reconstruct(p.terms[-1],due_day=21))
    if mode=='zero_installment':accounts[3]=reconstruct(accounts[3],minimum='0')
    if mode=='transfer_delays':
        f=plan.Flow(flow_id=uuid4().hex,kind='transfer',name='Transfer timing',amount='10',first_date=date(2026,1,2),cadence='once',clock=time(),source='checking-1',destination='checking-1',include='yes',debit_days=2,credit_days=1,settlement_days=3)
        p=plan.update_flow(p,f)
    p=plan.update_terms(reconstruct(p,settings=s),t);w=reconstruct(w,accounts=tuple(accounts))
    errors=plan.missing(w,p)
    assert any(phrase in message and path.startswith(where) for message,path in errors)
    html=overview(w,p,identifier,'test')
    assert 'Calculate my payoff preview' not in html and phrase in html
    with pytest.raises(ValueError):plan.build(w,p)


def test_partial_answers_can_be_saved_without_date_comparison_errors(tmp_path):
    identifier,w,_=complete(tmp_path);p=plan.Planning()
    assert plan.missing(w,p)
    assert 'Your next step' in overview(w,p,identifier,'test')


def test_loan_short_month_rollover_anchor_is_not_mistaken_for_a_conflict(tmp_path):
    _,w,p=complete(tmp_path)
    accounts=tuple(reconstruct(a,balance='0') if a.kind=='card' else reconstruct(a,due_date=date(2026,3,1)) if a.kind=='loan' else a for a in w.accounts)
    w=reconstruct(w,accounts=accounts)
    p=reconstruct(p,settings=reconstruct(p.settings,short_month=Short.ROLL_TO_NEXT_MONTH_FIRST_DAY))
    p=plan.update_terms(p,reconstruct(p.terms[-1],due_day=31))
    assert not plan.missing(w,p)
    assert plan.build(w,p).inputs.loans[0].due_dates[0]==date(2026,3,1)
