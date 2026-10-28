from decimal import Decimal
import pytest
from dashboard.manual import ManualScenario, AdditionalCard, editable_inputs
from dashboard.scenarios import parse_scenario, load_scenario
from dashboard.input_review import render_inputs
from test_dashboard_manual import fields, web, call, token
from test_recurring_cash import submit, hidden, recurring


def card(**updates):
    return {k:v for k,v in (fields()|updates).items() if k in AdditionalCard.model_fields}


def scenario(*cards, **updates):
    return ManualScenario.model_validate(fields()|updates|{'additional_cards':cards}).scenario()


def accepted_by_card(result):
    return {d.account.account_id:sum((r.accepted for r in result.decisions if r.debt_account_id==d.account.account_id),Decimal(0)) for d in result.debt_projections}


def test_two_card_minimums_before_excess_and_no_double_spending():
    s=scenario(card())
    result=s.project()
    assert accepted_by_card(result)=={'card':70,'card-2':50}
    assert sum(r.accepted for r in result.decisions)==120
    assert result.liquidity.points[-1].positions[0].cleared==30
    assert result.missed_minimum_account_ids==()


def test_three_minimums_shortfall_is_visible_in_card_order():
    result=scenario(card(),card()).project()
    assert accepted_by_card(result)=={'card':50,'card-2':50,'card-3':20}
    assert result.missed_minimum_account_ids==('card-3',)


def test_earlier_date_wins_tie_group_not_account_order():
    result=scenario(card(initiated='2026-01-01'),card()).project()
    assert accepted_by_card(result)=={'card':50,'card-2':50,'card-3':20}
    assert result.decisions[0].debt_account_id=='card-2'


def test_requested_extra_does_not_precede_another_cards_minimum():
    result=scenario(card(),payment_kind='extra').project()
    assert accepted_by_card(result)=={'card':70,'card-2':50}


@pytest.mark.parametrize('updates',[{'balance':'-1'},{'balance':1.5},{'payment_amount':'0.001'},
    {'minimum_remaining':'501'},{'next_close':'2026-01-15'},{'minimum_due':'2025-12-31'},
    {'debited':'2026-01-01'},{'day_count':'guess'}])
def test_each_card_gets_full_validation(updates):
    with pytest.raises(ValueError):scenario(card(**updates))


@pytest.mark.parametrize('payment,minimum,kind',[('200','50','minimum'),('0','50','minimum'),('20','50','minimum'),('200','0','minimum'),('80','50','extra')])
def test_lossless_edit_for_split_zero_and_extra_payments(payment,minimum,kind):
    original=scenario(card(payment_amount=payment,minimum_remaining=minimum,payment_kind=kind),
        card(payment_amount='0'),payment_amount='0',cash_events=(recurring(),))
    restored=parse_scenario(original.model_dump_json().encode())
    assert ManualScenario.model_validate(editable_inputs(restored)).scenario()==original
    assert 'Card 3' in render_inputs(original)


def test_future_bill_reduces_shared_capacity():
    result=scenario(card(),cash_events=({'kind':'expense','label':'Bill','amount':'40','date':'2026-02-01'},)).project()
    assert accepted_by_card(result)=={'card':50,'card-2':30}
    assert result.missed_minimum_account_ids==('card-2',)


def test_partial_card_and_gap_rejected():
    for more in ({'card_2_balance':'500'},{f'card_3_{k}':v for k,v in card().items()}):
        with pytest.raises(ValueError):ManualScenario.model_validate(fields()|more).scenario()


def test_multi_preview_save_review_copy_does_not_overwrite(web):
    values=fields()|{'token':token(web)}|{f'card_2_{k}':v for k,v in card().items()}
    status,_,html=submit(web,'/preview-example',values)
    assert status==200 and 'card-2' in html and not list(web[1].glob('*.json'))
    status,headers,_=submit(web,'/create-example',hidden(html))
    assert status==303
    path=next(web[1].glob('*.json'));before=path.read_bytes()
    saved=load_scenario(path);assert len(saved.debts)==2 and saved.origin=='synthetic_demo'
    for route in ('/edit/','/inputs/','/timeline/'):
        assert call(web,'GET',route+path.stem)[0]==200
    copy=editable_inputs(saved)|{'token':token(web),'name':'Copy','card_2_payment_amount':'60'}
    assert submit(web,'/create-example',copy)[0]==303
    assert path.read_bytes()==before


def test_separate_due_dates_are_checked_independently():
    result=scenario(card(minimum_due='2026-01-02')).project()
    assert result.missed_minimum_account_ids==('card-2',)


def test_mismatched_lifecycle_cannot_be_silently_merged_by_editor():
    from engine.common import reconstruct
    from datetime import timedelta
    s=scenario(card())
    requests=list(s.requests)
    requests[1]=reconstruct(requests[1],credited_at=requests[1].credited_at+timedelta(hours=1))
    changed=reconstruct(s,requests=tuple(requests))
    with pytest.raises(ValueError):editable_inputs(changed)


def test_all_form_controls_fit_http_field_limit_and_blank_cards_stay_optional(web):
    values=fields()|{'token':token(web)}
    for i in (2,3):values.update({f'card_{i}_{k}':v for k,v in card().items()})
    for i in range(6):
        values.update({f'cash_{i}_{k}':'' for k in ('kind','label','amount','date','until','short_month_rule')})
        values[f'cash_{i}_cadence']='once'
    assert submit(web,'/preview',values)[0]==200
    for i in (2,3):values.update({f'card_{i}_{k}':'' for k in card()})
    assert submit(web,'/preview',values)[0]==200
    assert not list(web[1].glob('*.json'))
