from datetime import date,timedelta
from decimal import Decimal as D,localcontext
from fractions import Fraction as F
import json
import pytest
from SCHEMA import assumed_default,PrepaymentBehavior,LoanType,RebateMethod
from demo_payoff import loan_example,example
from engine.loan_payoff import plan_loan_payoff
from engine.payoff import plan_payoff
from engine.minimum_forecast import PaymentSlot
from engine.common import reconstruct
from engine.liquidity import CashOpening
from engine.payoff import PaymentFunding
from payoff_cli import parse_loan_input,run
from test_dashboard_manual import web,call


def test_zero_rate_loan_four_payments_hand_calculated():
    value=loan_example();value=reconstruct(value,payment_target='250',loan=reconstruct(value.loan,contract_note_rate=assumed_default(D('0'))))
    result=plan_loan_payoff(value)
    assert result.payoff_date==date(2026,4,20) and result.total_paid==1000
    assert result.principal_paid==1000 and result.interest_paid==result.fees_paid==0
    assert result.principal_remaining==result.unposted_interest_remaining==0
    assert result.all_minimums_met and not result.missed_due_dates


def half_up(value):
    pennies=value*100
    return F((pennies.numerator*2//pennies.denominator+1)//2,100)


def test_fraction_oracle_uses_note_rate_and_rounds_only_at_actual_payment():
    value=loan_example();result=plan_loan_payoff(value)
    principal=F(1000);interest_total=F(0);paid_total=F(0);last=value.start.date();payoff=None
    for slot in value.slots:
        day=slot.credited_at.date();interest=half_up(principal*F(12,100)*F((day-last).days,365));last=day
        paid=min(F(150),principal+interest);principal-=paid-interest
        paid_total+=paid;interest_total+=interest
        if principal==0:payoff=day;break
    assert F(result.total_paid)==paid_total and F(result.interest_paid)==interest_total
    assert result.payoff_date==payoff
    assert result.total_paid==1000+result.interest_paid
    assert result==plan_loan_payoff(reconstruct(value,loan=reconstruct(value.loan,disclosed_apr=assumed_default(D('.99')))))
    with localcontext() as context:
        context.prec=6
        assert plan_loan_payoff(value)==result


def test_fees_interest_principal_waterfall_and_source_immutable():
    value=loan_example();first=value.slots[0];at=value.start
    slot=reconstruct(first,initiated_at=at,credited_at=at,debited_at=at,settled_at=at)
    loan=reconstruct(value.loan,fees_outstanding='10',accrued_interest='20',contract_note_rate=assumed_default(D('0')))
    value=reconstruct(value,loan=loan,payment_target='100',slots=(slot,)+value.slots[1:])
    before=value.model_dump_json();result=plan_loan_payoff(value);p=result.payments[0]
    assert (p.fees_paid,p.interest_paid,p.principal_paid)==(10,20,70)
    assert result.principal_paid+result.principal_remaining==1000
    assert result.fees_paid+result.fees_remaining==10
    assert value.model_dump_json()==before


def test_partial_weekly_payments_are_not_missed_when_met_by_due_date():
    value=loan_example();slots=[]
    for day in (6,13,20):
        at=value.start.replace(day=day)
        slots.append(PaymentSlot(slot_id=str(day),initiated_at=at,credited_at=at,debited_at=at,settled_at=at))
    value=reconstruct(value,end=value.start.replace(day=31),slots=tuple(slots),due_dates=(date(2026,1,20),date(2026,2,20)),
        loan=reconstruct(value.loan,contract_note_rate=assumed_default(D('0'))),payment_target='35')
    result=plan_loan_payoff(value)
    assert result.total_paid==105 and result.principal_remaining==895
    assert result.all_minimums_met and result.payments[0].minimum_required==100
    assert result.payments[0].minimum_paid==35
    card=example();debt=card.debts[0]
    debt=reconstruct(debt,account=reconstruct(debt.account,segments=(reconstruct(debt.account.segments[0],balance='500',apr=assumed_default(D('0'))),)),
        initial_minimum=reconstruct(debt.initial_minimum,statement_minimum_original='100',statement_minimum_remaining='100'))
    card=reconstruct(card,debts=(debt,),end=value.end,slots=tuple(slots),payment_target='35')
    card_result=plan_payoff(card)
    assert card_result.all_minimums_met and not card_result.all_minimum_requests_funded


def test_zero_cash_does_not_post_or_discard_unpaid_fractional_interest():
    value=loan_example();value=reconstruct(value,loan=reconstruct(value.loan,contract_note_rate=assumed_default(D('0')),accrued_interest='.004'),
        opening=reconstruct(value.opening,cleared='150'),cash_plans=())
    result=plan_loan_payoff(value)
    assert result.total_paid==0 and result.unposted_interest_remaining==D('.004')
    assert result.interest_posting_adjustment==0 and not result.all_minimums_met
    assert all(p.total_paid==0 for p in result.payments)


def test_loan_cannot_draw_from_an_unrouted_or_protected_account():
    value=loan_example();value=reconstruct(value,cash_plans=(),additional_openings=(CashOpening(account_id='bills',cleared='200',floor='100',reserved='100'),),
        payment_sources=(PaymentFunding(debt_account_id=value.loan.loan_id,cash_account_id='bills'),))
    result=plan_loan_payoff(value)
    assert result.total_paid==0 and not result.all_minimums_met
    assert {p.account_id:p.cleared for p in result.liquidity.points[-1].positions}=={'checking':D('400'),'bills':D('200')}


@pytest.mark.parametrize('mode',['paid_ahead','precomputed','missing_due','duplicate_due','float','precision','naive','overlap'])
def test_missing_contracts_and_invalid_loan_calendars_fail(mode):
    value=loan_example()
    with pytest.raises((ValueError,ArithmeticError)):
        if mode=='paid_ahead':value=reconstruct(value,loan=reconstruct(value.loan,prepayment_behavior=assumed_default(PrepaymentBehavior.PAID_AHEAD)))
        if mode=='precomputed':value=reconstruct(value,loan=reconstruct(value.loan,loan_type=LoanType.PRECOMPUTED,
            prepayment_behavior=assumed_default(PrepaymentBehavior.PRECOMPUTED_REBATE_REDUCTION),rebate_method=assumed_default(RebateMethod.RULE_OF_78)))
        if mode=='missing_due':value=reconstruct(value,due_dates=value.due_dates[:-1])
        if mode=='duplicate_due':value=reconstruct(value,due_dates=(value.due_dates[0],)+value.due_dates)
        if mode=='float':value=reconstruct(value,payment_target=150.1)
        if mode=='precision':value=reconstruct(value,payment_target='150.001')
        if mode=='naive':value=reconstruct(value,start=value.start.replace(tzinfo=None))
        if mode=='overlap':value=reconstruct(value,slots=value.slots[::-1])
        plan_loan_payoff(value)


def test_loan_cli_exact_input_and_csv_replay(tmp_path,capsys):
    value=loan_example();assert parse_loan_input(value.model_dump_json().encode())==value
    output=tmp_path/'loan';run(['--loan-demo','--output-dir',str(output)])
    expected=json.loads((output/'summary.json').read_text())
    run(['--loan-input',str(output/'inputs.json')])
    printed=capsys.readouterr().out
    assert json.loads(printed[printed.index('{'):])==expected
    assert 'principal_paid' in (output/'loan-payments.csv').read_text()


def test_sample_loan_view_and_downloads_match_standalone_engine(web):
    from test_dashboard_manual import call
    status,_,html=call(web,'GET','/loan-payoff-example')
    assert status==200 and '$35.81' in html and '$1,035.81' in html
    assert 'not combined with a card payoff plan' in html
    status,headers,raw=call(web,'GET','/loan-payoff-example/inputs.json')
    assert status==200 and headers['Cache-Control']=='no-store'
    assert parse_loan_input(raw.encode())==loan_example()
    status,headers,csv_text=call(web,'GET','/loan-payoff-example/payments.csv')
    assert status==200 and 'text/csv' in headers['Content-Type'] and 'principal_paid' in csv_text


def test_below_interest_payment_keeps_principal_and_reports_unfinished_debt():
    value=reconstruct(loan_example(),payment_target='5')
    result=plan_loan_payoff(value)
    assert result.principal_remaining==1000 and result.principal_paid==0
    assert result.total_paid==result.interest_paid==60
    assert result.unposted_interest_remaining>D('59')
    assert result.status=='horizon_exhausted' and result.payoff_date is None
    assert not result.all_minimums_met and len(result.missed_due_dates)==12
