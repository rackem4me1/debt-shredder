from datetime import date
import pytest
from pydantic import ValidationError
from SCHEMA import (
    semimonthly_occurrences, SemimonthlyShortMonthRule as Rule,
    IncomeSource, SinkingFundAllocation, IssuerAllocationConfiguration,
    AllocationRuleType, SegmentType, AllocationRule, assumed_default,
)
from test_SCHEMA import _account, _segment


@pytest.mark.parametrize('year,month,days,rule,expected', [
    (2026,2,(15,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY,(date(2026,2,15),date(2026,3,1))),
    (2024,2,(15,31),Rule.CLAMP_TO_LAST_DAY_OF_MONTH,(date(2024,2,15),date(2024,2,29))),
    (2026,2,(15,31),Rule.CLAMP_TO_LAST_DAY_OF_MONTH,(date(2026,2,15),date(2026,2,28))),
    (2026,4,(15,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY,(date(2026,4,15),date(2026,5,1))),
    (2026,12,(15,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY,(date(2026,12,15),date(2026,12,31))),
    (2026,2,(30,31),Rule.CLAMP_TO_LAST_DAY_OF_MONTH,(date(2026,2,28),date(2026,2,28))),
    (2026,2,(30,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY,(date(2026,3,1),date(2026,3,1))),
])
def test_resolved_events_preserve_both_nominal_amounts(year,month,days,rule,expected):
    assert semimonthly_occurrences(year,month,days,rule) == expected


@pytest.mark.parametrize('effective,days,rule', [
    (date(2026,3,1),(15,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY),
    (date(2024,3,1),(15,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY),
    (date(2026,2,28),(30,31),Rule.CLAMP_TO_LAST_DAY_OF_MONTH),
    (date(2026,3,1),(30,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY),
    (date(2027,1,1),(1,31),Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY),
    (date(1,1,15),(15,31),Rule.CLAMP_TO_LAST_DAY_OF_MONTH),
])
def test_both_schedule_consumers_accept_effective_dates(effective,days,rule):
    IncomeSource(source_id='i',destination_account_id='a',cadence='semimonthly',amount='50',
                 anchor_date=effective,semimonthly_days=days,semimonthly_short_month_rule=rule)
    SinkingFundAllocation(allocation_id='sf',account_id='b',purpose='bill',reserved_amount='0',
        planned_contribution_amount='50',planned_contribution_source_account_id='a',
        planned_contribution_cadence='semimonthly',planned_contribution_next_date=effective,
        planned_contribution_semimonthly_days=days,planned_contribution_semimonthly_short_month_rule=rule)


@pytest.mark.parametrize('effective', [date(2026,4,1),date(2027,1,1),date(2026,3,2)])
def test_no_phantom_spillover_from_full_month(effective):
    with pytest.raises(ValidationError,match='does not match'):
        IncomeSource(source_id='i',destination_account_id='a',cadence='semimonthly',amount='50',
            anchor_date=effective,semimonthly_days=(15,31),
            semimonthly_short_month_rule=Rule.ROLL_TO_NEXT_MONTH_FIRST_DAY)


def custom(*, types=(SegmentType.STANDARD_PURCHASE,), ids=(), resolved=True, excess=False):
    config=IssuerAllocationConfiguration(segment_priority_order=types,
        segment_id_priority_order=ids,is_resolved=resolved)
    fields=dict(account_id='a1',
        minimum_payment_allocation_rule=assumed_default(AllocationRuleType.LOWEST_APR_FIRST),
        excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT))
    prefix='excess' if excess else 'minimum'
    fields[prefix+'_payment_allocation_rule']=assumed_default(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED)
    fields[prefix+'_rule_configuration']=config
    return AllocationRule(**fields)


@pytest.mark.parametrize('excess',[False,True])
def test_missing_type_and_unresolved_configuration_block_account_readiness(excess):
    assert not _account(allocation_rule=custom(types=(SegmentType.CASH_ADVANCE,),excess=excess)).calculation_ready
    assert not _account(allocation_rule=custom(resolved=False,excess=excess)).calculation_ready
    assert _account(allocation_rule=custom(excess=excess)).calculation_ready


@pytest.mark.parametrize('ids,expected',[((),False),(('s1',),False),(('s1','ghost'),False),
    (('s1','s2'),True),(('s2','s1'),True)])
def test_same_type_segments_need_explicit_complete_order(ids,expected):
    account=_account(segments=(_segment(segment_id='s1'),_segment(segment_id='s2')),
                     allocation_rule=custom(ids=ids))
    assert account.calculation_ready is expected


def test_id_order_cannot_contradict_type_priority():
    account=_account(segments=(_segment(segment_id='p'),_segment(segment_id='c',segment_type=SegmentType.CASH_ADVANCE)),
        allocation_rule=custom(types=(SegmentType.CASH_ADVANCE,SegmentType.STANDARD_PURCHASE),ids=('p','c')))
    assert not account.calculation_ready
    rule=custom(types=(SegmentType.CASH_ADVANCE,SegmentType.STANDARD_PURCHASE),ids=('c','p'))
    assert rule.calculation_ready_for(account.segments)


def test_duplicate_explicit_ids_rejected():
    with pytest.raises(ValidationError,match='must not contain duplicates'):
        custom(ids=('s1','s1'))


def test_account_change_requires_fresh_readiness_check():
    original=_account(allocation_rule=custom())
    assert original.calculation_ready
    changed=_account(allocation_rule=original.allocation_rule,segments=(
        _segment(),_segment(segment_id='cash',segment_type=SegmentType.CASH_ADVANCE)))
    assert not changed.calculation_ready
    assert original.calculation_ready


def test_context_cannot_use_foreign_account_segments():
    assert not custom().calculation_ready_for((_segment(account_id='foreign'),))
