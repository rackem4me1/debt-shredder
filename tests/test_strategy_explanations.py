from dashboard.strategies import render_strategies, strategy_example
from engine.common import reconstruct
from test_multi_manual import scenario, card


def takeaways(s):
    return render_strategies(s).split('<h2>What to notice</h2>',1)[1].split('</section>',1)[0]


def test_explains_unfunded_budget_without_hiding_card_differences():
    html=takeaways(strategy_example())
    assert html.count('$120.00 applied of $400.00 requested')==3
    assert html.count('$280.00 of the requested payments is not funded')==3
    assert 'different amounts to individual cards' in html
    assert 'Minimum due dates are missed' not in html


def test_identical_results_are_not_presented_as_improvements():
    html=takeaways(scenario(card()))
    assert 'All three options apply the same amount to each card' in html
    assert 'different amounts to individual cards' not in html


def test_shortfalls_and_escaped_missed_card_name_are_prominent():
    s=reconstruct(scenario(card(),cash='100'),card_names=('First','<Late>'))
    html=takeaways(s)
    assert html.count('Minimum due dates are missed for &lt;Late&gt; (card-2)')==3
    assert 'Review missed minimums before using an interest difference' in html
    assert '<Late>' not in html


def test_fully_funded_comparison_does_not_claim_a_shortfall():
    html=takeaways(scenario(card(),cash='1000'))
    assert 'is not funded' not in html
    assert html.count('$400.00 applied of $400.00 requested')==3
