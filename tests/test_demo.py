from demo import run

def test_demo_is_reproducible_and_expected_values():
    result=run()
    assert result==run()
    assert result['liquidity']['safe_immediate_payment']=='650'
    assert result['liquidity']['external_income']=='800'
    assert result['liquidity']['external_outflows']=='1350'
    assert result['candidate_search']['candidate']=='110.00'
    assert result['payment_allocation']['applied']=='125'
