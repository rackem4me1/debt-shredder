from decimal import Decimal as D
import pytest
from dashboard import bills,my_money
from engine.common import reconstruct
from test_my_money import sample
from test_dashboard_manual import web,call
from test_restore import post,hidden


def book():
    return bills.BillBook(source_date='2026-01-01',bills=(
        bills.Bill(bill_id='insurance',name='Insurance',amount='20',due='2026-01-15',route='bills_box'),
        bills.Bill(bill_id='phone',name='Phone',amount='30',due='2026-01-05',route='checking'),
        bills.Bill(bill_id='utility',name='Utility',amount='40',due='2026-01-10',route='checking_from_bills_box'),
        bills.Bill(bill_id='subscription',name='Subscription',amount='15',due='2026-01-20',route='savor'),
        bills.Bill(bill_id='quarterly',name='Quarterly',amount='90',route='bills_box')))


def values(b):return {'name':b.name,'amount':str(b.amount),'due':b.due.isoformat() if b.due else '', 'route':b.route,'status':b.status}


def test_funding_accounts_card_charges_and_undated_items_are_not_double_counted():
    rows,cash,cards=bills.summary(book(),sample())
    assert cash=={'checking':D('30'),'bills_box':D('20'),'checking_from_bills_box':D('40')}
    assert cards==15
    html=bills.render(book(),sample())
    assert '$60.00' in html and '$30.00' in html and '$15.00' in html
    assert 'not a monthly budget' in html and 'Date needs checking' in html


def test_covered_excluded_rows_leave_totals_but_remain_visible():
    b=book();one=b.bills[0]
    changed=bills.change(b,one.bill_id,values(one)|{'status':'covered'})
    assert bills.summary(changed,sample())[1]['bills_box']==0
    assert 'Already in starting balances' in bills.render(changed,sample())
    assert changed.bills[1:]==b.bills[1:]


def test_statement_minimum_uses_current_money_snapshot_not_stale_bill_amount():
    b=reconstruct(book(),bills=(bills.Bill(bill_id='quicksilver-minimum',name='Statement',amount='999',due='2025-01-01',route='bills_box'),))
    current=sample();row=bills.effective(b,current)[0]
    assert row.amount==current.statement_minimum and row.due==current.statement_due
    with pytest.raises(ValueError):bills.change(b,row.bill_id,values(row))


@pytest.mark.parametrize('field,value',[('amount','1.001'),('amount',1.1),('amount','-1'),('route','unknown'),('status','paid'),('due','bad')])
def test_invalid_bill_edits_fail(field,value):
    b=book();one=b.bills[0]
    with pytest.raises((ValueError,ArithmeticError)):bills.change(b,one.bill_id,values(one)|{field:value})


def test_including_unknown_date_is_rejected():
    b=book();one=b.bills[-1]
    with pytest.raises(ValueError):bills.change(b,one.bill_id,values(one)|{'status':'include'})


def test_update_is_scoped_keeps_history_and_protects_stale_inputs(web):
    b=book();bills.save(web[1],b);my_money.save(web[1],sample())
    assert '/bills' in call(web,'GET','/my-money')[2]
    fields=hidden(call(web,'GET','/bills/edit/insurance')[2])|values(b.bills[0])
    status,_,html=post(web,'/bills/save',fields|{'amount':'1.001'})
    assert status==422 and 'value="1.001"' in html and bills.load(web[1])==b
    assert post(web,'/bills/save',fields|{'token':'wrong'})[0]==403
    assert post(web,'/bills/save',fields|{'fingerprint':'wrong'})[0]==409
    status,headers,_=post(web,'/bills/save',fields|{'status':'include'})
    assert status==303 and headers['Location']=='/bills'
    assert bills.load(web[1]).bills[0].status=='include'
    assert (web[1]/'bills_history'/(bills.fingerprint(b)+'.json')).exists()
    assert my_money.load(web[1])==sample()
    assert post(web,'/bills/save',fields)[0]==409


def test_bad_ids_and_corrupt_files_do_not_change_data(web):
    assert call(web,'GET','/bills')[0]==404
    bills.save(web[1],book())
    assert call(web,'GET','/bills/edit/missing')[0]==404
    path=web[1]/bills.FILENAME;path.write_text('{broken')
    assert call(web,'GET','/bills')[0]==422
    assert path.read_text()=='{broken'


def test_before_payday_counts_only_dated_cash_bills_before_payday():
    html=bills.render(book(),sample())
    assert 'Before your expected payday' in html
    before=html.split('Before your expected payday',1)[1].split('</section>',1)[0]
    assert '$0.00 in draft bills funded by Bills Box' in before
    assert '$30.00 directly from checking' in before
    assert 'Same-day payday bills are not in these totals' in before
