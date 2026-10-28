from datetime import timedelta
from decimal import Decimal as D
import csv,json
from io import StringIO
import pytest
from demo_payoff import example,template_example,saved_example
from engine.common import reconstruct
from engine.payoff import PaymentFunding,plan_payoff,compare_payoff
from engine.liquidity import CashOpening,CashKind,CashPlan
from engine.payoff_calendar import expand_payoff_template
from dashboard import payoff_view,payoff_repeat,payoff_runs
from payoff_exports import payment_csv
from payoff_cli import summary


def funded():
    value=example()
    savings=CashOpening(account_id='bills-box',cleared='300',floor='100',reserved='100')
    return reconstruct(value,opening=reconstruct(value.opening,cleared='200'),additional_openings=(savings,),cash_plans=(),
        payment_sources=(PaymentFunding(debt_account_id='high-rate',cash_account_id='bills-box'),
            PaymentFunding(debt_account_id='small-balance',cash_account_id='checking')))


def test_unrouted_savings_never_becomes_extra_checking_cash():
    value=example();value=reconstruct(value,opening=reconstruct(value.opening,cleared='200'),cash_plans=(),
        additional_openings=(CashOpening(account_id='savings',cleared='10000',floor='0'),))
    result=plan_payoff(value)
    assert result.total_paid==50
    positions={p.account_id:p for p in result.liquidity.points[-1].positions}
    assert positions['savings'].cleared==10000 and positions['checking'].cleared==150
    assert all(p.source_account_id=='checking' for p in result.payments)


def test_named_routes_preserve_each_floor_and_reserve_and_shared_target():
    value=funded();result=plan_payoff(value)
    first=result.payments[:2]
    assert [(p.account_id,p.source_account_id,p.total_paid) for p in first]==[
        ('high-rate','bills-box',D('100')),('small-balance','checking',D('50'))]
    assert result.total_paid==150
    positions={p.account_id:p for p in result.liquidity.points[-1].positions}
    assert positions['bills-box'].cleared==200 and positions['bills-box'].reserved==100
    assert positions['checking'].cleared==150
    assert all(p.above_floor>=0 for point in result.liquidity.points for p in point.positions)
    rows=list(csv.DictReader(StringIO(payment_csv(result))))
    assert rows[0]['funding_account']=='bills-box'
    report=summary(compare_payoff(value))
    assert set(report['results'][0]['ending_cash_accounts'])=={'checking','bills-box'}
    assert D(report['results'][0]['ending_checking'])==150
    assert report['results'][0]['primary_cash_account_id']=='checking'


def test_a_missing_minimum_blocks_extras_even_in_another_well_funded_account():
    value=funded();value=reconstruct(value,opening=reconstruct(value.opening,cleared='1000'),
        additional_openings=(reconstruct(value.additional_openings[0],cleared='200'),))
    result=plan_payoff(value)
    a,b=result.payments[:2]
    assert a.minimum_paid==0 and b.minimum_paid==25
    assert a.extra_paid==b.extra_paid==0
    assert not result.all_minimums_met
    assert compare_payoff(value).lowest_interest_strategy is None


def test_delayed_internal_transfer_cannot_fund_a_payment_before_arrival():
    value=funded();slot=value.slots[0];sent=slot.initiated_at-timedelta(days=1)
    plan=CashPlan(plan_id='move-to-bills',kind=CashKind.TRANSFER,amount='100',source_account_id='checking',destination_account_id='bills-box',
        initiated_at=sent,debited_at=sent,credited_at=slot.initiated_at+timedelta(days=1),settled_at=slot.initiated_at+timedelta(days=2))
    value=reconstruct(value,opening=reconstruct(value.opening,cleared='400'),
        additional_openings=(reconstruct(value.additional_openings[0],cleared='200'),),cash_plans=(plan,))
    result=plan_payoff(value)
    assert result.payments[0].minimum_paid==0
    assert any(p.total_paid>0 for p in result.payments[2:] if p.account_id=='high-rate')
    assert result.liquidity.external_income==0
    assert result.liquidity.external_outflows==result.total_paid
    assert result.liquidity.points[-1].aggregate_cash==600-result.total_paid
    assert result.transfers==(plan,)
    html=payoff_view.result_section(saved_example(),compare_payoff(value))
    assert 'Declared internal transfers' in html and 'Paid from' in html


@pytest.mark.parametrize('mode',['unknown_route','duplicate_route','missing_route','duplicate_cash','second_primary','other_payment'])
def test_ambiguous_funding_is_rejected(mode):
    value=funded()
    if mode=='unknown_route':value=reconstruct(value,payment_sources=(reconstruct(value.payment_sources[0],cash_account_id='missing'),)+value.payment_sources[1:])
    if mode=='duplicate_route':value=reconstruct(value,payment_sources=(value.payment_sources[0],)*2)
    if mode=='missing_route':value=reconstruct(value,payment_sources=value.payment_sources[:1])
    if mode=='duplicate_cash':value=reconstruct(value,additional_openings=(value.opening,))
    if mode=='second_primary':value=reconstruct(value,additional_openings=(reconstruct(value.additional_openings[0],primary=True),))
    if mode=='other_payment':
        at=value.slots[0].initiated_at
        value=reconstruct(value,cash_plans=(CashPlan(plan_id='other',kind=CashKind.PAYMENT,amount='1',source_account_id='checking',initiated_at=at,credited_at=at,debited_at=at,settled_at=at),))
    with pytest.raises(ValueError):plan_payoff(value)


def test_template_preserves_named_cash_accounts_and_routes():
    original=template_example();value=funded()
    template=reconstruct(original,opening=value.opening,additional_openings=value.additional_openings,payment_sources=value.payment_sources,
        cash_schedules=tuple(reconstruct(s,account_id='bills-box') for s in original.cash_schedules))
    expanded=expand_payoff_template(template)
    assert expanded.inputs.additional_openings==value.additional_openings
    assert expanded.inputs.payment_sources==value.payment_sources
    assert all(p.source_account_id=='bills-box' or p.destination_account_id=='bills-box' for p in expanded.inputs.cash_plans)
    assert plan_payoff(expanded.inputs).liquidity.external_income==18000


def test_existing_app_routes_are_preserved_with_nonprimary_first_and_saved_runs(tmp_path):
    source=saved_example();extra=CashOpening(account_id='bills-box',cleared='2000',floor='100',reserved='200')
    source=reconstruct(source,openings=(extra,source.openings[0]),requests=tuple(reconstruct(r,source_account_id='bills-box') if r.debt_account_id=='high-rate' else r for r in source.requests))
    adapted=payoff_view.inputs_from_scenario(source,'250')
    assert adapted.opening.account_id=='checking' and adapted.additional_openings==(extra,)
    assert {p.debt_account_id:p.cash_account_id for p in adapted.payment_sources}=={'high-rate':'bills-box','small-balance':'checking'}
    from test_payoff_repeat import values
    expanded=expand_payoff_template(payoff_repeat.template_from_scenario(source,values()))
    run=payoff_runs.PayoffRun(source_id='a'*32,source=source,expanded=expanded)
    identifier=payoff_runs.save(tmp_path,run)
    assert payoff_runs.load(tmp_path,identifier)==run
    assert 'bills-box' in payoff_runs.render(run)


def test_multiaccount_adapter_does_not_guess_a_missing_debt_funding_route():
    source=saved_example();source=reconstruct(source,openings=source.openings+(CashOpening(account_id='savings',cleared='1000',floor='100'),),
        requests=tuple(r for r in source.requests if r.debt_account_id=='high-rate'))
    with pytest.raises(ValueError,match='funding route'):payoff_view.inputs_from_scenario(source,'250')
