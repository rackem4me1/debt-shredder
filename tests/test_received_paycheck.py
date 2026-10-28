from datetime import date
import pytest
from dashboard import my_money, payday_cash, paycheck_week
from engine.common import reconstruct
from test_paycheck_week import inputs


def received_inputs():
    original=inputs()
    receipt=my_money.ReceivedPaycheck(received_on='2026-01-06',amount='699.50',
        replaces_expected_payday='2026-01-07',automatic_transfers_completed=True,
        rent_balance='900',kc_balance='80',iphone_balance='25')
    snapshot=reconstruct(original.base.snapshot,reported_on='2026-01-06',checking='450',
        bills_box='600',received_paycheck=receipt)
    return reconstruct(original,base=reconstruct(original.base,snapshot=snapshot))


def test_received_paycheck_blocks_repeat_income_transfers_and_draft_saves(tmp_path):
    value=received_inputs()
    for calculate,arg in ((paycheck_week.calculate,value),(payday_cash.calculate,value.base)):
        with pytest.raises(ValueError,match='already received'):calculate(arg)
    for save,arg in ((paycheck_week.save_draft,value),(payday_cash.save_draft,value.base)):
        with pytest.raises(ValueError,match='already received'):save(tmp_path,arg)
    assert not (tmp_path/'paycheck_drafts').exists()
    assert not (tmp_path/'payday_drafts').exists()


def test_current_pages_show_separate_balances_without_forecast_or_paid_claim():
    value=received_inputs()
    for html in (my_money.render(value.base.snapshot),payday_cash.render(value.base),paycheck_week.render(value)):
        assert '$699.50' in html and '$450.00' in html and '$900.00' in html
        assert '$80.00' in html and '$25.00' in html
        assert 'No bills have been marked paid' in html
        assert 'will not be added again' in html
        assert 'Save this week draft' not in html
        assert 'approximate amount' not in html


def test_receipt_roundtrip_history_and_next_payday_are_explicit(tmp_path):
    before=inputs().base.snapshot
    my_money.save(tmp_path,before)
    current=received_inputs().base.snapshot
    my_money.save(tmp_path,current)
    assert my_money.load(tmp_path)==current
    assert len(list((tmp_path/'money_history').glob('*.json')))==1
    assert before.received_paycheck is None
    assert my_money.needs_next_payday(current)
    next_snapshot=reconstruct(current,expected_payday='2026-01-14',expected_paycheck='710')
    assert not my_money.needs_next_payday(next_snapshot)
    assert next_snapshot.received_paycheck==current.received_paycheck


@pytest.mark.parametrize('field,value',[('amount','1.001'),('kc_balance',1.2),('iphone_balance','NaN')])
def test_receipt_financial_precision(field,value):
    receipt=received_inputs().base.snapshot.received_paycheck
    with pytest.raises((ValueError,ArithmeticError)):reconstruct(receipt,**{field:value})
