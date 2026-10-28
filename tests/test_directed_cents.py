from datetime import date
from decimal import Decimal as D

import pytest

from SCHEMA import AllocationRule, AllocationRuleType, assumed_default
from engine import allocation
from engine.common import reconstruct
from test_SCHEMA import _account, _segment
from test_arithmetic_allocation import minimum


def account():
    rule = AllocationRule(account_id='a1',
        minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
        excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT),
        consumer_override_supported=assumed_default(True))
    return _account(segments=(
        _segment(segment_id='low', balance='100', apr=assumed_default(D('.1')),
                 accrued_unposted_interest='0.0001234567890123456789'),
        _segment(segment_id='high', balance='100', apr=assumed_default(D('.3')))),
        allocation_rule=rule)


@pytest.mark.parametrize('amount', ['0.005', '0.001', '0.999', '1.001', '0.0100001'])
def test_fractional_direction_rejected_before_any_allocation(amount, monkeypatch):
    value = account()
    before = value.model_dump_json()
    def allocation_started(*args, **kwargs):
        pytest.fail('Allocation started before directed cents were validated')
    monkeypatch.setattr(allocation, 'expiring_priority', allocation_started)
    with pytest.raises(ValueError, match='directed.*whole.cent'):
        allocation.allocate_payment(value, D('2'), minimum('0'), date(2026, 1, 1),
            directed=(allocation.DirectedAmount(segment_id='low', amount=amount),))
    assert value.model_dump_json() == before


def test_invalid_direction_cannot_poison_subsequent_valid_payments_or_accrual():
    value = account()
    before = value.model_dump_json()
    with pytest.raises(ValueError, match='directed.*whole.cent'):
        allocation.allocate_payment(value, D('1'), minimum('0'), date(2026, 1, 1),
            directed=(allocation.DirectedAmount(segment_id='low', amount='0.005'),))
    assert value.model_dump_json() == before
    for day, directed_amount in ((1, '0.0100'), (2, '0.02')):
        result = allocation.allocate_payment(value, D('1.00'), minimum('0'), date(2026, 1, day),
            directed=(allocation.DirectedAmount(segment_id='low', amount=directed_amount),))
        assert result.applied == D('1') and result.unapplied == 0
        assert all(line.amount % D('.01') == 0 for line in result.lines)
        balances = {row.segment_id: row.amount for row in result.remaining_balances}
        assert all(amount % D('.01') == 0 for amount in balances.values())
        value = reconstruct(value, segments=tuple(reconstruct(s, balance=balances[s.segment_id]) for s in value.segments))
    assert {s.segment_id: s.balance for s in value.segments} == {'low': D('99.97'), 'high': D('98.03')}
    assert value.segments[0].accrued_unposted_interest == D('0.0001234567890123456789')
