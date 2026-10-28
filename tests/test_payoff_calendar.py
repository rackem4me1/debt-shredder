from datetime import date,time,timedelta
from decimal import Decimal as D
import json
import pytest
from SCHEMA import SemimonthlyShortMonthRule as Short
from demo_payoff import example,template_example
from engine.common import reconstruct
from engine.payoff import compare_payoff
from engine.payoff_calendar import expand_payoff_template,RecurringPayoffCash,RepeatingPaymentRule
from payoff_cli import parse_template,run


def test_repeating_template_matches_independently_supplied_full_calendar_and_money():
    template=template_example();expanded=expand_payoff_template(template)
    direct=compare_payoff(example());repeated=compare_payoff(expanded.inputs)
    for actual,expected in zip(repeated.results,direct.results):
        assert (actual.total_paid,actual.posted_interest,actual.payoff_date,actual.all_minimums_met)==(
            expected.total_paid,expected.posted_interest,expected.payoff_date,expected.all_minimums_met)
        assert actual.liquidity.external_income==expected.liquidity.external_income
        assert actual.liquidity.external_outflows==expected.liquidity.external_outflows
    assert len(expanded.generated_cycle_ids)==22
    assert len(expanded.inputs.cash_plans)==30
    assert expanded.inputs.debts[0].cycles[:2]==template.debts[0].cycles
    assert expanded.template==template and len(template.debts[0].cycles)==2
    assert expanded.inputs.slots[0].credited_at==example().slots[0].credited_at


def test_clamped_month_ends_leap_year_and_due_day_are_explicit():
    template=template_example()
    template=reconstruct(template,payments=reconstruct(template.payments,first_date=date(2026,1,31)),
        statements=tuple(reconstruct(r,due_day=31) for r in template.statements))
    expanded=expand_payoff_template(template)
    assert [s.credited_at.date() for s in expanded.inputs.slots[:3]]==[date(2026,1,31),date(2026,2,28),date(2026,3,31)]
    cycles=expanded.inputs.debts[0].cycles
    feb=next(c for c in cycles if c.end_date==date(2026,2,28))
    assert feb.start_date==date(2026,2,1) and feb.due_date==date(2026,3,31)
    leap=reconstruct(template,end=template.end.replace(year=2028,month=3,day=31))
    leap_inputs=expand_payoff_template(leap).inputs
    assert any(s.credited_at.date()==date(2028,2,29) for s in leap_inputs.slots)
    assert any(c.end_date==date(2028,2,29) for c in leap_inputs.debts[0].cycles)


def test_roll_short_month_keeps_nominal_month_events_distinct():
    template=template_example();rule=reconstruct(template.payments,first_date=date(2026,1,31),short_month_rule=Short.ROLL_TO_NEXT_MONTH_FIRST_DAY)
    value=expand_payoff_template(reconstruct(template,payments=rule))
    assert [s.initiated_at.date() for s in value.inputs.slots[:3]]==[date(2026,1,31),date(2026,3,1),date(2026,3,31)]
    assert len({s.slot_id for s in value.inputs.slots})==len(value.inputs.slots)


def test_cash_stop_dates_and_one_time_events_do_not_repeat_or_double_count():
    template=template_example();income,bill=template.cash_schedules
    income=reconstruct(income,until=date(2026,3,1))
    once=reconstruct(bill,schedule_id='once-only',cadence='once',short_month_rule=None)
    inputs=expand_payoff_template(reconstruct(template,cash_schedules=(income,once))).inputs
    assert len(inputs.cash_plans)==4
    assert sum(p.amount for p in inputs.cash_plans if p.kind.value=='income')==3600
    assert sum(p.amount for p in inputs.cash_plans if p.kind.value=='expense')==900
    assert sum(p.amount for p in expand_payoff_template(template).inputs.cash_plans if p.kind.value=='income')==18000


def test_weekly_cash_and_payments_calendar_delays_and_ninety_day_tail():
    template=template_example();rule=reconstruct(template.payments,first_date=date(2026,1,6),cadence='weekly',short_month_rule=None,credit_days=1,debit_days=2,settlement_days=3)
    cash=reconstruct(template.cash_schedules[0],first_date=date(2026,1,6),cadence='weekly',short_month_rule=None)
    value=expand_payoff_template(reconstruct(template,payments=rule,cash_schedules=(cash,)))
    first=value.inputs.slots[0]
    assert first.credited_at-first.initiated_at==timedelta(days=1)
    assert first.settled_at-first.initiated_at==timedelta(days=3)
    assert all((s.initiated_at.date()-date(2026,1,6)).days%7==0 for s in value.inputs.slots)
    last_cash=max(p.credited_at for p in value.inputs.cash_plans)
    assert last_cash>template.end
    assert len(value.inputs.slots)==51
    assert value.excluded_payment_dates==(date(2026,12,29),)


@pytest.mark.parametrize('mode',['clock_fold','clock_gap','duplicate_rules','missing_rules','cash_duplicate','first_payment_before_open','too_many_slots','wrong_timezone','bad_delay','float','missing_month_rule','cash_before_open'])
def test_invalid_or_ambiguous_templates_fail(mode):
    template=template_example()
    with pytest.raises((ValueError,ArithmeticError)):
        if mode in ('clock_fold','clock_gap'):
            # Build a common America/New_York source at local midnight.
            from zoneinfo import ZoneInfo
            tz=ZoneInfo('America/New_York')
            template=reconstruct(template,start=template.start.replace(tzinfo=tz),end=template.end.replace(tzinfo=tz),
                debts=tuple(reconstruct(d,credit_timezone='America/New_York') for d in template.debts),
                payments=reconstruct(template.payments,timezone_name='America/New_York',cadence='weekly',short_month_rule=None,
                    first_date=date(2026,11,1) if mode=='clock_fold' else date(2026,3,8),clock=time(1,30) if mode=='clock_fold' else time(2,30)))
        if mode=='duplicate_rules':template=reconstruct(template,statements=(template.statements[0],)*2)
        if mode=='missing_rules':template=reconstruct(template,statements=template.statements[:1])
        if mode=='cash_duplicate':template=reconstruct(template,cash_schedules=(template.cash_schedules[0],)*2)
        if mode=='first_payment_before_open':template=reconstruct(template,payments=reconstruct(template.payments,first_date=date(2025,12,20)))
        if mode=='too_many_slots':template=reconstruct(template,end=template.end.replace(year=2029),payments=reconstruct(template.payments,cadence='weekly',short_month_rule=None))
        if mode=='wrong_timezone':template=reconstruct(template,payments=reconstruct(template.payments,timezone_name='America/Chicago'))
        if mode=='bad_delay':template=reconstruct(template,payments=reconstruct(template.payments,credit_days=2,debit_days=1))
        if mode=='float':template=reconstruct(template,payment_target=200.5)
        if mode=='missing_month_rule':template=reconstruct(template,payments=reconstruct(template.payments,short_month_rule=None))
        if mode=='cash_before_open':template=reconstruct(template,cash_schedules=(reconstruct(template.cash_schedules[0],first_date=date(2025,12,1)),))
        expand_payoff_template(template)


def test_template_cli_exports_explicit_inputs_and_replays_them(tmp_path,capsys):
    template=template_example();path=tmp_path/'template.json';path.write_text(template.model_dump_json())
    assert parse_template(path.read_bytes())==template
    output=tmp_path/'result';run(['--template',str(path),'--output-dir',str(output)])
    assert json.loads((output/'template.json').read_text())==json.loads(path.read_text())
    report=json.loads((output/'summary.json').read_text())
    assert 'Generated dates' in report['calendar_assumption_note']
    run(['--input',str(output/'inputs.json')])
    printed=capsys.readouterr().out
    explicit=json.loads(printed[printed.index('{'):])
    assert explicit['results']==report['results']


def transfer_template(**changes):
    from engine.payoff_calendar import RecurringPayoffTransfer
    from engine.liquidity import CashOpening
    from engine.payoff import PaymentFunding
    template=template_example()
    rule=RecurringPayoffTransfer(schedule_id='bills-funding',amount='200',source_account_id='checking',destination_account_id='bills-box',
        first_date=date(2026,1,3),cadence='monthly',clock=time(),debit_days=0,credit_days=2,settlement_days=3,
        short_month_rule=Short.CLAMP_TO_LAST_DAY_OF_MONTH)
    if changes:rule=reconstruct(rule,**changes)
    return reconstruct(template,additional_openings=(CashOpening(account_id='bills-box',cleared='250',floor='100',reserved='100'),),
        payment_sources=(PaymentFunding(debt_account_id='high-rate',cash_account_id='bills-box'),PaymentFunding(debt_account_id='small-balance',cash_account_id='checking')),
        transfer_schedules=(rule,))


def test_recurring_transfers_match_explicit_physical_account_example():
    from demo_payoff import saved_multiaccount_example
    from dashboard.payoff_view import inputs_from_scenario
    template=transfer_template();expanded=expand_payoff_template(template)
    generated=compare_payoff(expanded.inputs);explicit=compare_payoff(inputs_from_scenario(saved_multiaccount_example(),D('250')))
    assert len([p for p in expanded.inputs.cash_plans if p.kind.value=='transfer'])==15
    assert not expanded.pending_transfer_ids
    for new,old in zip(generated.results,explicit.results):
        assert (new.total_paid,new.posted_interest,new.payoff_date)==(old.total_paid,old.posted_interest,old.payoff_date)
        assert new.liquidity.points[-1].positions==old.liquidity.points[-1].positions
        assert new.liquidity.external_income==18000
        assert new.liquidity.external_outflows==13500+new.total_paid
    assert generated.results[0].posted_interest==D('74.96')


def test_transfer_stop_and_pending_tail_keep_commitments_and_conserve_cash():
    from engine.payoff import cash_horizon
    template=transfer_template(until=date(2026,2,3))
    expanded=expand_payoff_template(template)
    assert len([p for p in expanded.inputs.cash_plans if p.kind.value=='transfer'])==2
    horizon=cash_horizon(expanded.inputs)
    # A declared transfer starts at the horizon and arrives later: keep it pending.
    rule=reconstruct(template.transfer_schedules[0],first_date=horizon.date(),cadence='once',short_month_rule=None,until=None,
        debit_days=1,credit_days=2,settlement_days=3)
    expanded=expand_payoff_template(reconstruct(template,transfer_schedules=(rule,)))
    assert len(expanded.pending_transfer_ids)==1
    cash=compare_payoff(expanded.inputs).results[0].liquidity
    checking=next(p for p in cash.points[-1].positions if p.account_id=='checking')
    assert checking.committed==200
    assert cash.external_income==18000
    assert cash.external_outflows==13500+compare_payoff(expanded.inputs).results[0].total_paid


def test_recurring_contributions_reserve_money_at_destination_only():
    template=transfer_template(kind='contribution',until=date(2026,1,3))
    expanded=expand_payoff_template(template);cash=compare_payoff(expanded.inputs).results[0].liquidity
    positions={p.account_id:p for p in cash.points[-1].positions}
    assert positions['bills-box'].reserved==300 and positions['checking'].reserved==50
    assert cash.external_income==18000


@pytest.mark.parametrize('changes',[{'destination_account_id':'missing'},{'destination_account_id':'checking'},
    {'debit_days':3,'credit_days':2},{'settlement_days':True},{'amount':'200.001'},
    {'first_date':date(2025,12,3)},{'until':date(2025,12,3)}])
def test_invalid_recurring_transfer_terms_fail(changes):
    with pytest.raises(ValueError):expand_payoff_template(transfer_template(**changes))
