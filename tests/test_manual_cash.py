from decimal import Decimal
import pytest
from dashboard.manual import ManualScenario, editable_inputs
from dashboard.input_review import render_inputs
from dashboard.scenarios import load_scenario
from test_dashboard_manual import fields, web, post, token, call


def event(kind='expense', amount='40', day='2026-02-01', label='Utility bill'):
    return dict(kind=kind, amount=amount, date=day, label=label)


def scenario(*events, **updates):
    return ManualScenario.model_validate(fields() | updates | {'cash_events': events}).scenario()


def test_later_bill_limits_payment_even_outside_debt_window():
    result = scenario(event()).project()
    assert result.decisions[0].accepted == Decimal('80')
    assert result.liquidity.points[-1].positions[0].cleared == Decimal('30')


def test_income_must_arrive_before_payment_to_fund_it():
    early = scenario(event('income', '100', '2026-01-01')).project()
    late = scenario(event('income', '100', '2026-01-06')).project()
    assert early.decisions[0].accepted == 200
    assert late.decisions[0].accepted == 120
    assert late.liquidity.points[-1].positions[0].cleared == 130


def test_income_after_bill_cannot_hide_earlier_cash_shortfall():
    result = scenario(event(amount='200'), event('income','300','2026-02-02')).project()
    assert result.decisions[0].accepted == 0
    assert result.liquidity.first_breach_at is not None


@pytest.mark.parametrize('changes', [dict(amount='0'),dict(amount='-1'),dict(amount='0.001'),
    dict(amount=1.5),dict(amount='NaN'),dict(date='2025-12-31'),dict(date='2026-04-03'),
    dict(label='   '),dict(kind='transfer')])
def test_invalid_cash_events_rejected(changes):
    with pytest.raises(ValueError): scenario(event() | changes)


def test_horizon_boundary_and_zero_payment_boundary():
    scenario(event(day='2026-04-02'))  # initiation + 90 days
    with pytest.raises(ValueError): scenario(event(day='2026-04-02'),payment_amount='0')
    scenario(event(day='2026-04-01'),payment_amount='0')


def test_cash_event_limit():
    with pytest.raises(ValueError): scenario(*(event() for _ in range(7)))


def test_roundtrip_preserves_cash_records_and_escapes_labels():
    original = scenario(event(label='<script>bill</script>'),event('income','50','2026-01-10','Paycheck'))
    recovered = editable_inputs(original)
    assert ManualScenario.model_validate(recovered).scenario() == original
    html = render_inputs(original)
    assert '&lt;script&gt;bill&lt;/script&gt;' in html
    assert '<script>bill</script>' not in html
    assert 'Paycheck' in html and 'Jan 10, 2026' in html


def test_http_all_six_rows_save_review_and_copy(web):
    values = fields() | {'token': token(web)}
    for i in range(6):
        values.update({f'cash_{i}_{k}':v for k,v in event(amount='1',label=f'Bill {i}').items()})
    status, headers, _ = post(web, values)
    assert status == 303
    id_ = headers['Location'].rsplit('/',1)[1]
    saved = load_scenario(web[1]/f'{id_}.json')
    assert len(saved.cash_plans) == 6
    assert saved.project().decisions[0].accepted == 114
    for path in [f'/inputs/{id_}', f'/edit/{id_}', f'/timeline/{id_}']:
        status, _, html = call(web,'GET',path)
        assert status == 200 and 'Bill 5' in html
    assert len(list(web[1].glob('*.json'))) == 1


def test_partial_row_is_retained_and_does_not_save(web):
    status, _, html = post(web,fields() | {'token':token(web), 'cash_3_label':'Rent'})
    assert status == 422 and 'row 4' in html and 'value="Rent"' in html
    assert not list(web[1].glob('*.json'))


def test_blank_rows_remain_compatible_with_existing_scenarios():
    blank = {f'cash_{i}_{k}':'' for i in range(6) for k in ('kind','label','amount','date')}
    assert ManualScenario.model_validate(fields() | blank).scenario() == scenario()
