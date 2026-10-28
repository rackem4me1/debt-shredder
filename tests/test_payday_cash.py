from decimal import Decimal as D,localcontext
from datetime import date
import pytest
from dashboard import payday_cash,bills,my_money
from engine.common import reconstruct
from engine.liquidity import CashKind
from test_my_money import sample
from test_bills import book
from test_dashboard_manual import web,call
from test_restore import post,hidden


def inputs():
    return payday_cash.DraftInputs(snapshot=sample(),book=book(),budget=payday_cash.EverydayBudget(food='40',fuel='10'))


def positions(result):return {p.account_id:p for p in result.points[-1].positions}


def test_before_payday_cash_preserves_account_floors_reserves_and_excludes_income():
    r,included,unresolved,outside=payday_cash.calculate(inputs())
    assert [b.bill_id for b in included]==['phone']
    assert positions(r)['checking'].cleared==170
    assert positions(r)['checking'].reserved==50
    assert positions(r)['checking'].above_floor==70
    assert positions(r)['bills_box'].cleared==500
    assert r.external_income==0 and r.external_outflows==30
    assert r.end.astimezone(payday_cash.ZoneInfo(payday_cash.ZONE)).date()==date(2026,1,6)
    assert r.points[0].aggregate_cash-r.external_outflows==r.points[-1].aggregate_cash
    assert 'quarterly' in {b.bill_id for b,_ in unresolved}


def test_future_income_does_not_hide_earlier_floor_shortage():
    value=inputs();value=reconstruct(value,snapshot=reconstruct(value.snapshot,checking='80',expected_paycheck='9999'))
    r,*_=payday_cash.calculate(value)
    assert r.status.value!='healthy'
    assert r.external_income==0
    assert 'exceed available cash' in payday_cash.render(value)


def test_card_charge_and_transfer_routing_are_not_mislabeled_cash_expenses():
    value=inputs();b=value.book
    b=reconstruct(b,bills=tuple(reconstruct(row,due='2026-01-05') for row in b.bills))
    r,included,unresolved,_=payday_cash.calculate(reconstruct(value,book=b))
    assert r.external_outflows==140 # insurance20 + phone30 + quarterly90; no utility40 or card15
    assert {b.bill_id for b,_ in unresolved}=={'utility','subscription'}
    assert all(a.kind!=CashKind.TRANSFER for a in r.audit)


def test_debt_payment_uses_payment_lifecycle_and_zero_bill_is_safe():
    value=inputs();row=reconstruct(value.book.bills[1],cash_kind='debt_payment')
    zero=bills.Bill(bill_id='zero',name='Zero',amount='0',due='2026-01-05',route='checking')
    r,*_=payday_cash.calculate(reconstruct(value,book=reconstruct(value.book,bills=(row,zero))))
    assert r.external_outflows==30
    assert all(a.kind==CashKind.PAYMENT for a in r.audit)
    assert {a.stage for a in r.audit}=={'init','credit','debit','settle'}


def test_same_balance_date_and_payday_bills_are_not_silently_debited():
    value=inputs();b=value.book
    row=reconstruct(b.bills[1],due=value.snapshot.reported_on)
    r,used,unresolved,_=payday_cash.calculate(reconstruct(value,book=reconstruct(b,bills=(row,))))
    assert not used and len(unresolved)==1 and r.external_outflows==0
    row=reconstruct(row,due=value.snapshot.expected_payday)
    r,used,_,outside=payday_cash.calculate(reconstruct(value,book=reconstruct(b,bills=(row,))))
    assert not used and len(outside)==1 and r.external_outflows==0


def test_saved_draft_keeps_exact_inputs_after_current_records_change(tmp_path):
    value=inputs();id_=payday_cash.save_draft(tmp_path,value)
    my_money.save(tmp_path,reconstruct(value.snapshot,checking='1'))
    loaded=payday_cash.load_draft(tmp_path,id_)
    assert loaded==value and payday_cash.calculate(loaded)==payday_cash.calculate(value)
    html=payday_cash.render(loaded,saved=True)
    assert 'Saved draft' in html
    assert 'Open current cash picture' in html
    assert 'Adjust spending cushions' not in html


@pytest.mark.parametrize('food,fuel',[('-1','0'),('1.001','0'),('NaN','0'),(1.1,'0'),('0','Infinity')])
def test_invalid_cushions_rejected(food,fuel):
    with pytest.raises((ValueError,ArithmeticError)):payday_cash.EverydayBudget(food=food,fuel=fuel)


@pytest.mark.parametrize('payday',['2025-12-31','2026-01-01','2026-05-01'])
def test_invalid_window_rejected(payday):
    value=inputs()
    with pytest.raises(ValueError):payday_cash.calculate(reconstruct(value,snapshot=reconstruct(value.snapshot,expected_payday=payday)))


def test_decimal_precision_and_whole_day_timezone_boundaries():
    value=inputs();expected=payday_cash.calculate(value)
    with localcontext() as ctx:
        ctx.prec=6
        assert payday_cash.calculate(value)==expected
    assert expected[0].end.isoformat().startswith('2026-01-07T05:59:59')


def test_web_save_stale_sources_cushion_validation_and_reopening(web):
    value=inputs();my_money.save(web[1],value.snapshot);bills.save(web[1],value.book);payday_cash.save_budget(web[1],value.budget)
    status,_,html=call(web,'GET','/cash-until-payday');assert status==200
    fields=hidden(html)
    assert post(web,'/cash-until-payday/save',fields|{'token':'bad'})[0]==403
    assert post(web,'/cash-until-payday/save',fields|{'fingerprint':'bad'})[0]==409
    status,headers,_=post(web,'/cash-until-payday/save',fields)
    assert status==303 and headers['Location'].startswith('/cash-draft/')
    assert call(web,'GET',headers['Location'])[0]==200
    assert 'Before payday' in call(web,'GET','/cash-until-payday/saved')[2]
    budget_fields=hidden(call(web,'GET','/cash-until-payday/budget')[2])|{'food':'1.001','fuel':'0'}
    status,_,html=post(web,'/cash-until-payday/budget-save',budget_fields)
    assert status==422 and 'value="1.001"' in html
    assert post(web,'/cash-until-payday/budget-save',budget_fields|{'food':'60','fuel':'10'})[0]==303
    assert post(web,'/cash-until-payday/save',fields)[0]==409
    assert call(web,'GET',headers['Location'])[0]==200
    assert (web[1]/'payday_budget_history').exists()


def test_fall_dst_end_uses_local_day_before_payday():
    value=inputs();value=reconstruct(value,snapshot=reconstruct(value.snapshot,reported_on='2026-10-31',expected_payday='2026-11-02'))
    r,*_=payday_cash.calculate(value)
    assert r.end.isoformat()=='2026-11-02T05:59:59.999999+00:00'
    assert r.end.astimezone(payday_cash.ZoneInfo(payday_cash.ZONE)).date()==date(2026,11,1)


def test_snapshot_and_bill_edits_both_invalidate_cash_save(web):
    value=inputs();my_money.save(web[1],value.snapshot);bills.save(web[1],value.book);payday_cash.save_budget(web[1],value.budget)
    original=hidden(call(web,'GET','/cash-until-payday')[2])
    my_money.save(web[1],reconstruct(value.snapshot,checking='210'))
    assert post(web,'/cash-until-payday/save',original)[0]==409
    fresh=hidden(call(web,'GET','/cash-until-payday')[2])
    bills.save(web[1],reconstruct(value.book,bills=()))
    assert post(web,'/cash-until-payday/save',fresh)[0]==409
    assert not (web[1]/'payday_drafts').exists()
