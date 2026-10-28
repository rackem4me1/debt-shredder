import json
from decimal import Decimal as D
import pytest
from demo_portfolio import scenario
from dashboard.scenarios import save_scenario, load_scenario, parse_scenario
from dashboard.report import summary, render
from engine.common import reconstruct


def test_round_trip_preserves_exact_inputs_and_results(tmp_path):
    original = scenario()
    path = save_scenario(original, tmp_path / 'scenario.json')
    restored = load_scenario(path)
    assert restored == original
    assert restored.project() == original.project()
    assert restored.openings[0].cleared == D('500')
    with pytest.raises(FileExistsError):
        save_scenario(original, path)
    assert load_scenario(path) == original


def test_explicit_overwrite_and_no_temporary_files_left(tmp_path):
    first = scenario()
    path = save_scenario(first, tmp_path / 'scenario.json')
    second = reconstruct(first, name='Another scenario')
    save_scenario(second, path, overwrite=True)
    assert load_scenario(path) == second
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize('change', ['float', 'unknown_account', 'extra', 'version', 'wrong_format', 'bool_version'])
def test_invalid_imports_fail_before_presentation(change):
    data = scenario().model_dump(mode='json')
    if change == 'float': data['openings'][0]['cleared'] = 500.0
    elif change == 'unknown_account': data['requests'][0]['source_account_id'] = 'missing'
    elif change == 'extra': data['unknown'] = 'field'
    elif change == 'version': data['version'] = 2
    elif change == 'wrong_format': data['format'] = 'debt-shredder-debt-checkpoint'
    else: data['version'] = True
    with pytest.raises(ValueError):
        parse_scenario(json.dumps(data).encode())


def test_duplicate_keys_and_oversize_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        parse_scenario(b'{"version":1,"version":1}')
    with pytest.raises(ValueError, match='4 MiB'):
        parse_scenario(b' ' * (4 * 1024 * 1024 + 1))


def test_report_agrees_with_shared_cash_regression():
    result = summary(scenario())
    assert result['cash'][0]['cleared'] == '100.00'
    assert result['cash'][0]['floor'] == '100'
    assert [D(row['accepted']) for row in result['decisions']] == [300, 50, 50]
    assert [D(row['posted_balance']) for row in result['debts']] == [150, 450]
    assert not result['missed_minimum_account_ids']
    assert result['cash_end'] > result['debt_end']


def test_shortfall_and_missing_request_remain_visible():
    base = scenario()
    short = reconstruct(base, openings=(reconstruct(base.openings[0], cleared='120'),))
    result = summary(short)
    assert not result['all_minimum_requests_funded']
    assert set(result['missed_minimum_account_ids']) == {'card-a', 'card-b'}
    empty = summary(reconstruct(base, requests=()))
    assert empty['all_minimum_requests_funded']
    assert set(empty['missed_minimum_account_ids']) == {'card-a', 'card-b'}


def test_names_are_escaped_in_html_and_origin_is_explicit():
    html = render(reconstruct(scenario(), name='<script>alert("bad")</script>'))
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert 'Synthetic example' in html
    assert 'Unposted interest' in html
    assert 'not an actual ledger' in html


def overview_html(value):
    return render(value).split('id="overview-title">', 1)[1].split('</section>', 1)[0]


def test_overview_counts_shared_cash_once_and_shows_actual_shortfall():
    html = overview_html(scenario())
    assert '<strong>$400.00</strong>' in html
    assert 'Of $600.00 requested' in html
    assert '<strong>$100.00</strong>' in html
    assert '<strong>$600.00</strong>' in html
    assert '$200.00 of requested payments cannot be applied' in html
    assert 'Cash needs attention' not in html
    assert 'not available spending money' in html
    assert 'Cash checks through' in html
    assert 'future minimum payments are not included automatically' in html


def test_overview_missing_requests_does_not_imply_minimums_are_met():
    html = overview_html(reconstruct(scenario(), requests=()))
    assert 'No payments are planned' in html
    assert 'Minimum payments are missed' in html
    assert 'Forecast checks' not in html


def test_overview_flags_cash_breach_even_without_payment_requests():
    base = scenario()
    value = reconstruct(base, requests=(), openings=(reconstruct(base.openings[0], cleared='90'),))
    html = overview_html(value)
    assert 'Cash needs attention somewhere in the cash window: buffer breach' in html
    assert 'ending balance alone does not show earlier shortages' in html
