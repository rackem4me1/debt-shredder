from datetime import date
from decimal import Decimal as D,localcontext
import pytest
from SCHEMA import assumed_default,PrepaymentBehavior
from engine.common import reconstruct
from engine.mixed_payoff import MixedPayoffInputs,PayoffLoan,plan_mixed_payoff,compare_mixed_payoff
from engine.payoff import plan_payoff,PaymentFunding
from engine.loan_payoff import plan_loan_payoff,replay_loan_payoff
from engine.liquidity import CashOpening
from demo_payoff import example,loan_example,mixed_example


def cash_values(cash):
    # Generated event IDs differ; every financial point and audit stage must match.
    return cash.model_dump(exclude={'points':{'__all__':{'trigger_ids'}},'audit':{'__all__':{'plan_id'}}})


def test_card_only_parity_including_cash_and_due_dates():
    value=example();mixed=MixedPayoffInputs(cards=value.debts,**value.model_dump(exclude={'version','debts'}))
    for strategy in ('highest_interest_first','smallest_balance_first'):
        old=plan_payoff(value,strategy);new=plan_mixed_payoff(mixed,strategy)
        assert (new.payments,new.cards)==(old.payments,old.debts)
        assert cash_values(new.liquidity)==cash_values(old.liquidity)
        assert (new.payoff_date,new.total_paid,new.interest_total,new.all_minimums_met)==(old.payoff_date,old.total_paid,old.posted_interest,old.all_minimums_met)


def test_loan_only_parity_exact_waterfall_and_shared_cash():
    value=loan_example();mixed=MixedPayoffInputs(loans=(PayoffLoan(loan=value.loan,timezone_name=value.timezone_name,due_dates=value.due_dates),),
        **value.model_dump(exclude={'format','version','loan','timezone_name','due_dates'}))
    old=plan_loan_payoff(value);new=plan_mixed_payoff(mixed)
    assert new.loans[0].projection.model_dump(exclude={'liquidity'})==old.model_dump(exclude={'liquidity'})
    assert cash_values(new.liquidity)==cash_values(old.liquidity)
    assert new.total_paid==old.total_paid and new.interest_total==old.interest_paid and new.payoff_date==old.payoff_date


def test_single_shared_budget_cash_conservation_and_immutable_inputs():
    value=mixed_example();before=value.model_dump_json();result=plan_mixed_payoff(value)
    for slot in value.slots:
        assert sum(p.total_paid for p in result.payments if p.slot_id==slot.slot_id)<=300
    assert result.total_paid==sum(p.total_paid for p in result.payments)
    assert result.total_paid==sum(p.amount for c in result.cards for p in c.payments)+result.loans[0].projection.total_paid
    ending=result.liquidity.points[-1].positions[0]
    assert ending.cleared==D('400')+D('18000')-D('13500')-result.total_paid
    assert ending.reserved==50 and ending.above_floor>=0
    assert result.loans[0].projection.liquidity==result.liquidity
    assert result.status=='paid_off' and result.all_minimums_met
    assert value.model_dump_json()==before
    with localcontext() as context:
        context.prec=6
        assert plan_mixed_payoff(value)==result


def test_minimums_across_classes_before_extra_and_note_rate_orders_loan():
    value=mixed_example();value=reconstruct(value,loans=(reconstruct(value.loans[0],loan=reconstruct(value.loans[0].loan,
        contract_note_rate=assumed_default(D('.30')),disclosed_apr=assumed_default(D('.01')))),))
    result=plan_mixed_payoff(value);first=[p for p in result.payments if p.slot_id==value.slots[0].slot_id]
    by={p.account_id:p for p in first}
    assert by['sample-loan'].extra_paid>0
    assert by['high-rate'].extra_paid==by['small-balance'].extra_paid==0
    assert all(p.minimum_paid==p.minimum_required for p in first)
    # Loan ranks by its 30% NOTE rate, not 1% disclosed APR.


def test_protected_route_shortage_blocks_all_extras_without_pooling():
    value=mixed_example();ids=[c.account.account_id for c in value.cards]+[value.loans[0].loan.loan_id]
    value=reconstruct(value,additional_openings=(CashOpening(account_id='locked',cleared='200',reserved='100',floor='100'),),
        payment_sources=tuple(PaymentFunding(debt_account_id=k,cash_account_id='locked' if k=='sample-loan' else 'checking') for k in ids))
    result=plan_mixed_payoff(value)
    assert all(p.total_paid==0 for p in result.payments if p.account_id=='sample-loan')
    assert all(p.extra_paid==0 for p in result.payments)
    assert not result.all_minimums_met and result.payoff_date is None
    assert next(p for p in result.liquidity.points[-1].positions if p.account_id=='locked').cleared==200
    assert compare_mixed_payoff(value).lowest_interest_strategy is None


@pytest.mark.parametrize('mode',['duplicate','empty','missing_route','unsupported_loan','float'])
def test_invalid_mixed_contracts_and_identity_rejected(mode):
    value=mixed_example()
    with pytest.raises(ValueError):
        if mode=='duplicate':value=reconstruct(value,loans=(reconstruct(value.loans[0],loan=reconstruct(value.loans[0].loan,loan_id=value.cards[0].account.account_id)),))
        if mode=='empty':value=reconstruct(value,cards=(),loans=())
        if mode=='missing_route':value=reconstruct(value,payment_sources=(PaymentFunding(debt_account_id='sample-loan',cash_account_id='checking'),))
        if mode=='unsupported_loan':value=reconstruct(value,loans=(reconstruct(value.loans[0],loan=reconstruct(value.loans[0].loan,prepayment_behavior=assumed_default(PrepaymentBehavior.PAID_AHEAD))),))
        if mode=='float':value=reconstruct(value,payment_target=300.1)
        plan_mixed_payoff(value)


@pytest.mark.parametrize('bad',[D('-1'),D('.001'),D('999999'),1,D('NaN')])
def test_loan_replay_rejects_invalid_accepted_credits(bad):
    with pytest.raises(ValueError):replay_loan_payoff(loan_example(),lambda _view,_plans:bad)


def test_zero_interest_mixed_schedule_hand_calculated_and_cash_not_doubled():
    value=mixed_example();card=value.cards[0]
    card=reconstruct(card,account=reconstruct(card.account,segments=(reconstruct(card.account.segments[0],balance='500',apr=assumed_default(D('0'))),)))
    loan=reconstruct(value.loans[0],loan=reconstruct(value.loans[0].loan,contract_note_rate=assumed_default(D('0'))))
    value=reconstruct(value,cards=(card,),loans=(loan,),payment_target='200')
    result=plan_mixed_payoff(value)
    assert result.total_paid==1500 and result.interest_total==0
    assert result.payoff_date==date(2026,8,20)
    assert [sum(p.total_paid for p in result.payments if p.slot_id==s.slot_id) for s in value.slots]==[D('200')]*7+[D('100')]+[D('0')]*4
    assert result.all_minimums_met


def test_weekly_partial_minimums_for_both_classes_met_by_due_date():
    from engine.minimum_forecast import PaymentSlot
    value=mixed_example();card=value.cards[0]
    card=reconstruct(card,initial_minimum=reconstruct(card.initial_minimum,statement_minimum_original='100',statement_minimum_remaining='100'))
    slots=[]
    for day in (6,13,20):
        at=value.start.replace(day=day)
        slots.append(PaymentSlot(slot_id=str(day),initiated_at=at,credited_at=at,debited_at=at,settled_at=at))
    value=reconstruct(value,cards=(card,),end=value.start.replace(day=31),slots=tuple(slots),payment_target='70')
    result=plan_mixed_payoff(value)
    assert result.all_minimums_met and not result.all_minimum_requests_funded
    assert result.total_paid==210


def test_mixed_cli_and_csv_replay_exact_input(tmp_path,capsys):
    import json,csv
    from io import StringIO
    from payoff_cli import parse_mixed_input,mixed_summary,run
    value=mixed_example();assert parse_mixed_input(value.model_dump_json().encode())==value
    folder=tmp_path/'mixed';run(['--mixed-demo','--output-dir',str(folder)])
    expected=json.loads((folder/'summary.json').read_text())
    run(['--mixed-input',str(folder/'inputs.json')]);assert json.loads(capsys.readouterr().out)==expected
    assert expected==mixed_summary(compare_mixed_payoff(value))
    for r in expected['results']:
        rows=list(csv.DictReader(StringIO((folder/(r['strategy']+'.csv')).read_text())))
        assert sum(D(p['total_paid']) for p in rows)==D(r['total_paid'])
    with pytest.raises(ValueError):parse_mixed_input(value.model_dump_json().replace('"version":1','"version":true').encode())


from test_dashboard_manual import web,call


def test_mixed_app_target_downloads_and_engine_match(web):
    from payoff_cli import parse_mixed_input
    from dashboard.mixed_payoff_view import sample
    status,_,html=call(web,'GET','/mixed-payoff-example')
    assert status==200 and '$146.39' in html and '$187.25' in html and 'One shared budget' in html
    status,headers,raw=call(web,'GET','/mixed-payoff-example/inputs.json?target=200')
    assert status==200 and headers['Cache-Control']=='no-store'
    assert parse_mixed_input(raw.encode())==sample({'target':['200']})
    status,headers,raw=call(web,'GET','/mixed-payoff-example/highest-interest.csv?target=200')
    assert status==200 and 'funding_account' in raw and 'sample-loan' in raw
    status,_,html=call(web,'GET','/mixed-payoff-example?target=0')
    assert status==200 and 'No winner claimed' in html and 'Not reached' in html
    for query in ('target=NaN','target=-1','target=100.001','target=1&target=2','unknown=1'):
        assert call(web,'GET','/mixed-payoff-example?'+query)[0]==400


def test_shared_transfer_arrival_cannot_fund_earlier_loan_payment():
    from engine.liquidity import CashPlan,CashKind
    value=mixed_example();first=value.slots[0];loan=value.loans[0]
    transfer=CashPlan(plan_id='fund-loan',kind=CashKind.TRANSFER,amount='200',source_account_id='checking',destination_account_id='loan-cash',
        initiated_at=first.initiated_at,debited_at=first.debited_at,credited_at=first.credited_at.replace(day=21),settled_at=first.settled_at.replace(day=22))
    ids=[c.account.account_id for c in value.cards]+[loan.loan.loan_id]
    value=reconstruct(value,additional_openings=(CashOpening(account_id='loan-cash',cleared='100',floor='100'),),
        payment_sources=tuple(PaymentFunding(debt_account_id=k,cash_account_id='loan-cash' if k==loan.loan.loan_id else 'checking') for k in ids),
        cash_plans=value.cash_plans+(transfer,))
    result=plan_mixed_payoff(value)
    payments=[p for p in result.payments if p.account_id==loan.loan.loan_id]
    assert payments[0].total_paid==0 and payments[1].total_paid>0
    assert not result.all_minimums_met
    assert result.liquidity.external_income==18000
    assert result.liquidity.external_outflows==13500+result.total_paid
    assert all(p.extra_paid==0 for p in result.payments if p.slot_id==first.slot_id)
