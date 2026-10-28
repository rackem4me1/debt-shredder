from datetime import date
from decimal import localcontext
from dashboard import setup_plan as plan
from dashboard.mixed_payoff_view import render_saved,results_section
from engine.common import reconstruct
from engine.mixed_payoff import compare_mixed_payoff
from test_setup_plan import complete


def test_first_round_shows_initiation_separately_from_credit_and_named_funding(tmp_path):
    _,w,p=complete(tmp_path)
    p=reconstruct(p,settings=reconstruct(p.settings,first_payment=date(2026,1,18),credit_days=1,debit_days=2,settlement_days=3))
    run=plan.build(w,p);before=run.model_dump_json();html=render_saved(run)
    assert 'First payment round to review' in html
    assert 'Jan 18, 2026 at 12:00 AM UTC' in html
    assert '<td>Jan 18, 2026</td><td>Jan 19, 2026</td>' in html
    assert '<th>Start payment</th><th>Credited</th>' in html
    assert 'Everyday checking' in html and 'Nothing is scheduled with a bank' in html
    assert run.model_dump_json()==before


def test_first_round_shortage_is_visible_without_claiming_it_was_paid(tmp_path):
    _,w,p=complete(tmp_path)
    w=reconstruct(w,accounts=tuple(reconstruct(a,balance='150') if a.kind=='checking' else a for a in w.accounts))
    p=reconstruct(p,flows=())
    run=plan.build(w,p);comparison=compare_mixed_payoff(run.inputs)
    assert all(not r.all_minimums_met for r in comparison.results)
    html=render_saved(run)
    assert 'Unfunded requested minimum' in html and 'Missed minimum' in html
    assert '<td>$0.00</td><td>$100.00</td>' in html
    assert 'Paid from' in html and 'Everyday checking' in html


def test_result_display_is_decimal_context_safe_and_escapes_account_labels(tmp_path):
    _,w,p=complete(tmp_path);run=plan.build(w,p);comparison=compare_mixed_payoff(run.inputs)
    labels={a.account_id:a.name for a in w.accounts}|{'checking-1':'<Private & checking>'}
    expected=results_section(run.inputs,comparison,account_labels=labels)
    with localcontext() as context:
        context.prec=3
        assert results_section(run.inputs,comparison,account_labels=labels)==expected
    assert '&lt;Private &amp; checking&gt;' in expected and '<Private & checking>' not in expected
