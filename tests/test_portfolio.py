from datetime import date,datetime,timedelta,timezone
from decimal import Decimal as D
import pytest
from SCHEMA import GracePeriodState as G,assumed_default
from engine.common import ZERO,reconstruct
from engine.portfolio import PortfolioDebt,PortfolioPaymentRequest,RequestKind,coordinate_payments,PortfolioProjection
from engine.liquidity import CashOpening,CashPlan,CashKind
from test_SCHEMA import _account,_segment
from test_search_simulation import cycles,minimum

T=datetime(2026,1,1,tzinfo=timezone.utc)
END=datetime(2026,1,21,tzinfo=timezone.utc)


def debt(id_,balance='100',due='0'):
    a=_account(account_id=id_,current_grace_state=G.LOST_GRACE,
        segments=(_segment(account_id=id_,balance=balance,apr=assumed_default(ZERO)),))
    return PortfolioDebt(account=a,cycles=tuple(reconstruct(c,account_id=id_) for c in cycles()),
        initial_minimum=reconstruct(minimum(due),account_id=id_))


def request(id_,account,amount,day,kind=RequestKind.EXTRA,priority=0,source='checking',delay=0):
    at=T+timedelta(days=day-1)
    return PortfolioPaymentRequest(request_id=id_,debt_account_id=account,source_account_id=source,amount=amount,
        kind=kind,priority=priority,initiated_at=at,credited_at=at+timedelta(days=delay),
        debited_at=at+timedelta(days=delay+1),settled_at=at+timedelta(days=delay+2))


def openings(cash='150',floor='20'):
    return (CashOpening(account_id='checking',cleared=cash,floor=floor,primary=True),)


def income(amount,day):
    at=T+timedelta(days=day-1)
    return CashPlan(plan_id='income',kind=CashKind.INCOME,amount=amount,destination_account_id='checking',
        initiated_at=at,credited_at=at,debited_at=at,settled_at=at)


def test_future_minimums_reserved_before_earlier_extras():
    requests=(request('extra','a','80',2),request('min-a','a','40',10,RequestKind.MINIMUM,0),
        request('min-b','b','40',10,RequestKind.MINIMUM,1))
    r=coordinate_payments((debt('a',due='40'),debt('b',due='40')),openings(),(),requests,T,END)
    assert {d.request_id:d.accepted for d in r.decisions}=={'extra':D(50),'min-a':D(40),'min-b':D(40)}
    assert r.all_minimum_requests_funded and not r.all_requests_funded
    assert not r.missed_minimum_account_ids
    assert r.liquidity.points[-1].positions[0].cleared==20
    assert sum((p.amount for a in r.debt_projections for p in a.payments),ZERO)==r.liquidity.external_outflows==130


def test_short_cash_marks_unfunded_minimum_and_actual_missed_due():
    requests=(request('a','a','40',10,RequestKind.MINIMUM,0),request('b','b','40',10,RequestKind.MINIMUM,1))
    r=coordinate_payments((debt('a',due='40'),debt('b',due='40')),openings('60','10'),(),requests,T,END)
    assert [d.accepted for d in r.decisions]==[40,10]
    assert not r.all_minimum_requests_funded
    assert r.missed_minimum_account_ids==('b',)
    assert r.liquidity.status.value=='healthy'


def test_future_income_cannot_fund_earlier_extra():
    requests=(request('extra','a','20',2),request('minimum','b','80',10,RequestKind.MINIMUM))
    r=coordinate_payments((debt('a'),debt('b',due='80')),openings('20','20'),(income('80',9),),requests,T,END)
    assert [d.accepted for d in r.decisions]==[0,80]


def test_pending_debit_keeps_shared_cash_committed():
    requests=(request('a','a','70',2,delay=8),request('b','b','70',3,delay=8))
    r=coordinate_payments((debt('a'),debt('b')),openings('100','0'),(),requests,T,END)
    assert [d.accepted for d in r.decisions]==[70,30]
    assert r.liquidity.external_outflows==100
    point=next(p for p in r.liquidity.points if p.at==T+timedelta(days=2))
    assert point.positions[0].cleared==100 and point.positions[0].committed==100


def test_same_day_credits_on_one_debt_stay_distinct():
    requests=(request('one','a','30',2,priority=0),request('two','a','30',2,priority=1))
    r=coordinate_payments((debt('a'),),openings('100','0'),(),requests,T,END)
    assert [p.event_id for p in r.debt_projections[0].payments]==['one','two']
    assert r.debt_projections[0].account.total_balance()==40


def test_opening_balance_cap_prevents_overpayment():
    requests=(request('one','a','60',2),request('two','a','60',3))
    r=coordinate_payments((debt('a','70'),),openings('200','0'),(),requests,T,END)
    assert [d.accepted for d in r.decisions]==[60,10]
    assert r.decisions[1].reason=='opening_balance_limit'
    assert r.debt_projections[0].account.total_balance()==0


def test_reserves_stay_with_their_physical_account():
    cash=openings('50','0')+(CashOpening(account_id='savings',cleared='500',reserved='400',floor='50'),)
    requests=(request('save','a','100',2,source='savings'),request('check','b','100',3))
    r=coordinate_payments((debt('a'),debt('b')),cash,(),requests,T,END)
    assert [d.accepted for d in r.decisions]==[50,50]
    savings=next(p for p in r.liquidity.points[-1].positions if p.account_id=='savings')
    assert savings.reserved==400 and savings.cleared==450


def test_missing_requests_do_not_hide_missed_minimums():
    r=coordinate_payments((debt('a',due='25'),),openings(),(),(),T,END)
    assert r.all_minimum_requests_funded # no supplied request is unfunded
    assert r.missed_minimum_account_ids==('a',) # but a contractual due was missed


def test_ambiguous_simultaneous_priorities_rejected():
    with pytest.raises(ValueError,match='distinct explicit priorities'):
        coordinate_payments((debt('a'),debt('b')),openings(),(),(request('a','a','10',2),request('b','b','10',2)),T,END)


def test_base_cash_payment_cannot_duplicate_debt_request():
    req=request('one','a','10',2)
    with pytest.raises(ValueError,match='requests'):
        coordinate_payments((debt('a'),),openings(),(req.cash_plan(D(10)),),(req,),T,END)


def test_portfolio_results_are_reproducible_immutable_and_serializable():
    inputs=((debt('a'),debt('b')),openings(),(),(request('a','a','70',2),request('b','b','70',3)),T,END)
    first=coordinate_payments(*inputs)
    assert first==coordinate_payments(*inputs)==PortfolioProjection.model_validate_json(first.model_dump_json())


def test_interest_runs_after_actual_credit_not_initiation():
    d=debt('a')
    d=reconstruct(d,account=reconstruct(d.account,segments=(reconstruct(d.account.segments[0],apr=assumed_default(D('3.65'))),)))
    r=coordinate_payments((d,),openings('100','0'),(),(request('a','a','100',2,delay=8),),T,END)
    assert r.debt_projections[0].account.segments[0].accrued_unposted_interest==9
    assert r.debt_projections[0].payments[0].on==date(2026,1,10)


def test_request_input_order_does_not_change_explicit_priority_result():
    requests=(request('extra','a','80',2),request('a','a','40',10,RequestKind.MINIMUM,0),request('b','b','40',10,RequestKind.MINIMUM,1))
    inputs=((debt('a',due='40'),debt('b',due='40')),openings(),())
    assert coordinate_payments(*inputs,requests,T,END)==coordinate_payments(*inputs,tuple(reversed(requests)),T,END)


def test_existing_cash_shortfall_is_reported_and_new_spending_stops():
    r=coordinate_payments((debt('a'),),openings('10','20'),(),(request('a','a','5',2),),T,END)
    assert r.decisions[0].accepted==0 and r.liquidity.status.value=='buffer_breach'


def test_credit_order_can_differ_from_initiation_order_without_overpaying():
    requests=(request('earlier-init','a','60',2,delay=10),request('later-init','a','60',3,delay=0))
    r=coordinate_payments((debt('a'),),openings('200','0'),(),requests,T,END)
    assert [d.accepted for d in r.decisions]==[60,40]
    assert [p.event_id for p in r.debt_projections[0].payments]==['later-init','earlier-init']
    assert r.debt_projections[0].account.total_balance()==0


def test_seeded_shared_cash_invariants_across_request_sets():
    import random
    rng=random.Random(2610)
    for case in range(15):
        available=D(rng.randrange(1,150));floor=D(rng.randrange(0,30))
        ds=(debt('a','100'),debt('b','100'))
        reqs=tuple(request(str(i),'a' if i%2==0 else 'b',str(rng.randrange(1,70)),2+i,
            RequestKind.MINIMUM if i<2 else RequestKind.EXTRA) for i in range(4))
        r=coordinate_payments(ds,openings(str(available+floor),str(floor)),(),reqs,T,END)
        total=sum((d.accepted for d in r.decisions),ZERO)
        assert total<=available
        assert r.liquidity.points[-1].positions[0].cleared==available+floor-total
        assert all(row.above_floor>=0 for point in r.liquidity.points for row in point.positions)
        assert all(a.account.total_balance()>=0 for a in r.debt_projections)
        assert total==sum((p.amount for a in r.debt_projections for p in a.payments),ZERO)


def test_shared_cash_demo_preserves_floor_and_both_minimums():
    from demo_portfolio import run
    r=run()
    assert r['ending_checking']=='100.00'
    assert r['debt_balances']=={'card-a':'150.00','card-b':'450.00'}
    assert [D(d['accepted']) for d in r['decisions']]==[D(300),D(50),D(50)]
    assert not r['missed_minimum_account_ids']
