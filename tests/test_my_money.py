import pytest
from dashboard import my_money
from test_dashboard_manual import web,call
from test_restore import post,hidden


def sample():
    return my_money.MoneySnapshot(reported_on='2026-01-01',checking='200',checking_floor='50',bills_box='500',
        card_balance='1000',statement_minimum='30',statement_due='2026-01-20',expected_paycheck='700',
        expected_payday='2026-01-07',notes='Sample note <script>test</script>')


def values(s):return {k:str(getattr(s,k)) for k,_,_ in my_money.FIELDS}


def test_save_load_and_prior_values_preserved(tmp_path):
    first=sample();my_money.save(tmp_path,first)
    second=my_money.change(first,values(first)|{'checking':'150.25'})
    my_money.save(tmp_path,second)
    assert my_money.load(tmp_path)==second
    history=tmp_path/'money_history'/(my_money.fingerprint(first)+'.json')
    assert my_money.MoneySnapshot.model_validate_json(history.read_text())==first
    assert second.notes==first.notes


@pytest.mark.parametrize('field,value',[('checking','1.001'),('checking_floor','-1'),('expected_paycheck','NaN'),('card_balance',1.1),('reported_on','bad')])
def test_invalid_values_rejected(field,value):
    with pytest.raises((ValueError,ArithmeticError)):my_money.change(sample(),values(sample())|{field:value})


def test_render_labels_estimates_and_does_not_pool_accounts():
    html=my_money.render(sample())
    assert '$200.00' in html and '$500.00' in html
    assert 'not added to checking' in html
    assert 'approximate amount' in html and 'payment status not verified' in html
    assert 'Extra-payment amount: not calculated yet' in html
    assert '<script>' not in html and '&lt;script&gt;' in html


def test_web_update_retains_invalid_input_checks_stale_data_and_keeps_history(web):
    first=sample();my_money.save(web[1],first)
    assert 'Open My Money' in call(web,'GET','/')[2]
    fields=hidden(call(web,'GET','/my-money/edit')[2])|values(first)
    status,_,html=post(web,'/my-money/save',fields|{'checking':'1.001'})
    assert status==422 and 'value="1.001"' in html
    assert my_money.load(web[1])==first
    assert post(web,'/my-money/save',fields|{'token':'wrong'})[0]==403
    assert post(web,'/my-money/save',fields|{'fingerprint':'wrong'})[0]==409
    status,headers,_=post(web,'/my-money/save',fields|{'checking':'150'})
    assert status==303 and headers['Location']=='/my-money'
    assert my_money.load(web[1]).checking==150
    assert post(web,'/my-money/save',fields)[0]==409
    assert list((web[1]/'money_history').glob('*.json'))
    assert not list(web[1].glob('[a-f0-9]'*32+'.json'))


def test_missing_or_corrupt_snapshot_is_not_replaced(web):
    assert 'No starting picture' in call(web,'GET','/my-money')[2]
    path=web[1]/my_money.FILENAME;path.write_text('{broken')
    assert call(web,'GET','/my-money')[0]==422
    assert path.read_text()=='{broken'
