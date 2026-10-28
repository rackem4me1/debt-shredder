from decimal import Decimal as D
import pytest
from dashboard.forecast_terms import change_terms
from dashboard.strategies import strategy_example
from dashboard.scenarios import save_scenario, load_scenario
from test_dashboard_manual import web, call
from test_restore import post, hidden


def values(s):
    return {'name':'Terms reviewed','formula':'understood',**{f'{key}_{i}':v for i in range(len(s.debts))
        for key,v in {'floor':'30','rate':'1','rounding':'ROUND_HALF_UP','provenance':'user_confirmed','date':'2026-10-16'}.items()}}


def test_changes_only_explicit_terms_and_name():
    s=strategy_example();r=change_terms(s,values(s))
    assert r.model_dump(exclude={'name','debts'})==s.model_dump(exclude={'name','debts'})
    for old,new in zip(s.debts,r.debts):
        assert old.model_dump(exclude={'account'})==new.model_dump(exclude={'account'})
        exclude={'minimum_payment_floor','minimum_payment_rate','rounding_mode'}
        assert old.account.model_dump(exclude=exclude)==new.account.model_dump(exclude=exclude)
        assert new.account.minimum_payment_floor.value==30
        assert new.account.minimum_payment_rate.value==D('.01')
        assert new.account.minimum_payment_rate.provenance.value=='user_confirmed'


@pytest.mark.parametrize('field,value',[('floor_0','-1'),('floor_0','1.001'),('rate_0','NaN'),('rate_0','101'),
    ('rate_0',1.1),('date_0',''),('provenance_0','actual_statement'),('rounding_0','guess'),('formula','')])
def test_invalid_or_implicitly_confirmed_values_rejected(field,value):
    s=strategy_example()
    with pytest.raises((ValueError,ArithmeticError)):change_terms(s,values(s)|{field:value})


def test_estimate_remains_estimate_and_has_no_confirmation_date():
    s=strategy_example();v=values(s)|{'provenance_0':'user_provided_estimate','date_0':''}
    r=change_terms(s,v)
    assert r.debts[0].account.minimum_payment_floor.provenance.value=='user_provided_estimate'
    assert r.debts[0].account.minimum_payment_floor.confirmed_date is None


def test_preview_save_preserves_original_and_signed_candidate(web):
    s=strategy_example();id_='c'*32;path=web[1]/(id_+'.json');save_scenario(s,path);before=path.read_bytes()
    status,_,html=call(web,'GET','/forecast-terms/'+id_)
    assert status==200 and 'assumed default' in html
    status,_,html=post(web,'/forecast-terms-preview',hidden(html)|values(s))
    assert status==200 and 'Previously saved' in html and 'New terms' in html
    assert len(list(web[1].glob('*.json')))==1
    status,headers,_=post(web,'/restore-save',hidden(html))
    assert status==303
    result=load_scenario(web[1]/(headers['Location'].split('/')[-1]+'.json'))
    assert result==change_terms(s,values(s))
    assert path.read_bytes()==before
    assert 'Review future minimum terms' in call(web,'GET',headers['Location'])[2]


def test_stale_source_and_unexpected_fields_rejected(web):
    s=strategy_example();id_='d'*32;save_scenario(s,web[1]/(id_+'.json'))
    v=hidden(call(web,'GET','/forecast-terms/'+id_)[2])|values(s)
    assert post(web,'/forecast-terms-preview',v|{'fingerprint':'stale'})[0]==409
    assert post(web,'/forecast-terms-preview',v|{'balance':'0'})[0]==422
    assert post(web,'/forecast-terms-preview',v|{'token':'bad'})[0]==403
    assert len(list(web[1].glob('*.json')))==1
