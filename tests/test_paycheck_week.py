from datetime import date
from decimal import Decimal as D,localcontext
import pytest
from dashboard import paycheck_week,payday_cash,bills,my_money
from engine.common import reconstruct
from engine.liquidity import CashKind
from test_payday_cash import inputs as base_inputs
from test_dashboard_manual import web,call
from test_restore import hidden,post


def inputs():
    return paycheck_week.WeekInputs(base=base_inputs(),settings=paycheck_week.PaycheckSettings(
        bills_box_transfer='100',kc_transfer='20',kc_opening=None,food='40',fuel='10'))


def pos(result):return {p.account_id:p for p in result.points[-1].positions}


def test_one_income_internal_transfer_and_unknown_kc_hold_conserve_cash():
    value=inputs();r,*_=paycheck_week.calculate(value);p=pos(r)
    # Jan5 phone30 checking; Jan10 utility unresolved; no insurance untilJan15.
    assert p['checking'].cleared==770 #200+700-100-30
    assert p['bills_box'].cleared==600
    assert p['checking'].reserved==120 #50 before +50 after +20 pendingKC
    assert 'kc_open' not in p
    assert r.external_income==700 and r.external_outflows==30
    assert r.points[-1].aggregate_cash==700+700-30
    assert all(a.kind==CashKind.TRANSFER for a in r.audit if a.plan_id=='fund-bills')
    assert all(a.kind==CashKind.RESERVE for a in r.audit if a.plan_id=='hold-kc')
    assert r.end.astimezone(payday_cash.ZoneInfo(payday_cash.ZONE)).date()==date(2026,1,13)


def test_known_kc_balance_enables_real_internal_transfer_not_income_or_expense():
    value=inputs();value=reconstruct(value,settings=reconstruct(value.settings,kc_opening='80',kc_as_of='2026-01-01'))
    r,*_=paycheck_week.calculate(value);p=pos(r)
    assert p['checking'].cleared==750 and p['kc_open'].cleared==100
    assert p['checking'].reserved==100
    assert r.external_income==700 and r.external_outflows==30
    assert all(a.kind==CashKind.TRANSFER for a in r.audit if a.plan_id=='fund-kc')


def test_payday_bill_first_exposes_shortage_even_with_identical_ending_balances():
    value=inputs();snapshot=reconstruct(value.base.snapshot,checking='100')
    bill=bills.Bill(bill_id='payday',name='Payday bill',amount='60',due=snapshot.expected_payday,route='checking')
    base=reconstruct(value.base,snapshot=snapshot,book=reconstruct(value.base.book,bills=(bill,)))
    value=reconstruct(value,base=base)
    normal=paycheck_week.calculate(value)[0];early=paycheck_week.calculate(value,bills_first=True)[0]
    assert normal.status.value=='healthy'
    assert early.status.value!='healthy'
    assert pos(normal)==pos(early)
    assert early.first_breach_at<next(a.at for a in early.audit if a.plan_id=='expected-pay')


def test_delayed_bills_box_arrival_cannot_fund_earlier_bill():
    value=inputs();snapshot=reconstruct(value.base.snapshot,bills_box='0')
    bill=bills.Bill(bill_id='payday',name='Savings bill',amount='50',due=snapshot.expected_payday,route='bills_box')
    base=reconstruct(value.base,snapshot=snapshot,book=reconstruct(value.base.book,bills=(bill,)))
    value=reconstruct(value,base=base,settings=reconstruct(value.settings,bills_box_delay=2))
    r,*_=paycheck_week.calculate(value)
    assert r.status.value=='negative_cash' and pos(r)['bills_box'].cleared==50
    assert r.first_breach_at is not None
    assert r.external_income==700 and r.external_outflows==50


def test_transfer_still_in_transit_at_end_is_not_in_destination_balance():
    value=inputs();value=reconstruct(value,settings=reconstruct(value.settings,bills_box_delay=8))
    r,*_=paycheck_week.calculate(value)
    assert pos(r)['bills_box'].cleared==500
    assert r.points[-1].in_transit==100
    assert r.points[-1].aggregate_cash==1370


def test_card_charge_never_becomes_cash_outflow_and_opening_day_is_unresolved():
    value=inputs();card=reconstruct(value.base.book.bills[3],due='2026-01-08')
    old=reconstruct(value.base.book.bills[0],due=value.base.snapshot.reported_on)
    base=reconstruct(value.base,book=reconstruct(value.base.book,bills=(card,old)))
    r,_,unresolved,charges,*_=paycheck_week.calculate(reconstruct(value,base=base))
    assert r.external_outflows==0
    assert charges==(card,) and unresolved[0][0]==old


@pytest.mark.parametrize('field,value',[('kc_transfer','-1'),('food','1.001'),('kc_opening',1.1),('kc_delay',True),('bills_box_delay',15)])
def test_invalid_settings_rejected(field,value):
    with pytest.raises((ValueError,ArithmeticError)):reconstruct(inputs().settings,**{field:value})


def test_save_reopen_preserves_all_inputs_and_results(tmp_path):
    value=inputs();id_=paycheck_week.save_draft(tmp_path,value)
    loaded=paycheck_week.load_draft(tmp_path,id_)
    assert loaded==value
    assert paycheck_week.calculate(loaded)==paycheck_week.calculate(value)
    assert paycheck_week.calculate(loaded,bills_first=True)==paycheck_week.calculate(value,bills_first=True)
    html=paycheck_week.render(loaded,saved=True)
    assert 'Open current week picture' in html and 'Adjust paycheck estimates' not in html
    with localcontext() as c:
        c.prec=6
        assert paycheck_week.calculate(value)==paycheck_week.calculate(loaded)


def test_web_settings_save_and_draft_source_checks(web):
    value=inputs();my_money.save(web[1],value.base.snapshot);bills.save(web[1],value.base.book)
    payday_cash.save_budget(web[1],value.base.budget);paycheck_week.save_settings(web[1],value.settings)
    status,_,html=call(web,'GET','/paycheck-week');assert status==200
    fields=hidden(html)
    assert post(web,'/paycheck-week/save',fields|{'token':'bad'})[0]==403
    assert post(web,'/paycheck-week/save',fields|{'fingerprint':'bad'})[0]==409
    status,headers,_=post(web,'/paycheck-week/save',fields)
    assert status==303 and headers['Location'].startswith('/week-draft/')
    assert call(web,'GET',headers['Location'])[0]==200
    settings=hidden(call(web,'GET','/paycheck-week/settings')[2])|{key:str(getattr(value.settings,key)) if getattr(value.settings,key) is not None else '' for key,_,_ in paycheck_week.FIELDS}
    status,_,html=post(web,'/paycheck-week/settings-save',settings|{'food':'1.001'})
    assert status==422 and 'value="1.001"' in html
    assert post(web,'/paycheck-week/settings-save',settings|{'food':'60'})[0]==303
    assert post(web,'/paycheck-week/save',fields)[0]==409
    assert call(web,'GET',headers['Location'])[0]==200
    assert (web[1]/'paycheck_settings_history').exists()
    assert '/week-draft/' in call(web,'GET','/paycheck-week/saved')[2]


def test_kc_balance_cannot_be_silently_reused_with_a_new_starting_date():
    value=inputs()
    with pytest.raises(ValueError):reconstruct(value.settings,kc_opening='80')
    value=reconstruct(value,settings=reconstruct(value.settings,kc_opening='80',kc_as_of='2026-01-02'))
    with pytest.raises(ValueError,match='same reported date'):paycheck_week.calculate(value)
