from html import unescape
import re
import pytest
from dashboard.payment_edit import change_payments
from dashboard.strategies import strategy_example,selected_strategy
from dashboard.scenarios import save_scenario,load_scenario
from test_dashboard_manual import web,call
from test_restore import post,hidden


def values(s):return {'name':s.name,**{f'amount_{i}':str(r.amount) for i,r in enumerate(s.requests)}}


def test_noop_edit_is_exact_and_changed_amount_preserves_every_other_field():
    s=selected_strategy(strategy_example(),'smallest-balance')
    assert change_payments(s,values(s))==s
    v=values(s)|{'amount_0':'25','name':'Changed request'}
    result=change_payments(s,v)
    assert result.model_dump(exclude={'requests','name'})==s.model_dump(exclude={'requests','name'})
    for a,b in zip(s.requests,result.requests):assert a.model_dump(exclude={'amount'})==b.model_dump(exclude={'amount'})
    assert result.requests[0].amount==25
    assert result.project().missed_minimum_account_ids==('card',)


@pytest.mark.parametrize('amount',['0','-1','1.001','NaN','Infinity',True,1.1])
def test_invalid_amounts_rejected(amount):
    s=strategy_example()
    with pytest.raises(ValueError):change_payments(s,values(s)|{'amount_0':amount})


def test_http_preview_save_exact_original_untouched(web):
    s=selected_strategy(strategy_example(),'smallest-balance');id_='a'*32
    path=web[1]/(id_+'.json');save_scenario(s,path);before=path.read_bytes()
    status,_,html=call(web,'GET','/payment-edit/'+id_)
    assert status==200 and 'Adjust payment amounts' in html
    fields=hidden(html)|values(s)|{'name':'My revised priority','amount_0':'25'}
    status,_,html=post(web,'/payment-preview',fields)
    assert status==200 and 'Review payment changes' in html
    assert len(list(web[1].glob('*.json')))==1
    status,headers,_=post(web,'/payment-save',hidden(html))
    assert status==303 and headers['Location'].startswith('/plan/')
    result=load_scenario(web[1]/(headers['Location'].split('/')[-1]+'.json'))
    assert result==change_payments(s,values(s)|{'name':'My revised priority','amount_0':'25'})
    assert path.read_bytes()==before
    assert 'Adjust payment amounts' in call(web,'GET',headers['Location'])[2]


def test_changed_original_and_extra_fields_fail_without_save(web):
    s=strategy_example();id_='b'*32;path=web[1]/(id_+'.json');save_scenario(s,path)
    fields=hidden(call(web,'GET','/payment-edit/'+id_)[2])|values(s)
    assert post(web,'/payment-preview',fields|{'priority':'0'})[0]==422
    assert post(web,'/payment-preview',fields|{'fingerprint':'changed'})[0]==409
    assert len(list(web[1].glob('*.json')))==1


def test_invalid_entry_keeps_typed_values_and_original_file(web):
    s=strategy_example();id_='c'*32;path=web[1]/(id_+'.json');save_scenario(s,path);before=path.read_bytes()
    fields=hidden(call(web,'GET','/payment-edit/'+id_)[2])|values(s)|{'amount_0':'1.001','name':'My new version'}
    status,_,html=post(web,'/payment-preview',fields)
    assert status==422 and 'value="1.001"' in html and 'value="My new version"' in html
    assert 'role="alert"' in html
    assert path.read_bytes()==before


def test_preview_keeps_missed_dates_unfunded_cash_and_interest_visible():
    from dashboard.payment_edit import payment_preview
    s=selected_strategy(strategy_example(),'smallest-balance')
    changed=change_payments(s,values(s)|{'amount_0':'25'})
    html=payment_preview(changed,s,'a'*32,'test-token')
    assert 'due dates are missed' in html
    assert 'Missed minimum dates:' in html
    assert 'unposted interest' in html
    assert 'Ending cash:' in html and 'Requested before' in html and 'Requested after' in html
    assert '2026-01-' in html


def test_corrupt_source_rejected_without_losing_server(web):
    s=strategy_example();id_='d'*32;path=web[1]/(id_+'.json');save_scenario(s,path)
    fields=hidden(call(web,'GET','/payment-edit/'+id_)[2])|values(s)
    path.write_text('{broken')
    assert post(web,'/payment-preview',fields)[0]==422
    assert call(web,'GET','/')[0]==200
    assert path.read_text()=='{broken'
