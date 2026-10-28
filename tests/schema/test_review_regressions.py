"""Independent acceptance regressions. Expected to expose remaining revision-4 gaps."""
from datetime import date
from SCHEMA import *
from test_SCHEMA import _account, _segment


def test_roll_forward_accepts_march_first_for_february_31_payday():
    income = IncomeSource(
        source_id='pay', destination_account_id='checking', cadence=IncomeCadence.SEMIMONTHLY,
        amount='100', anchor_date=date(2026, 3, 1), semimonthly_days=(15, 31),
        semimonthly_short_month_rule=SemimonthlyShortMonthRule.ROLL_TO_NEXT_MONTH_FIRST_DAY,
    )
    assert income.anchor_date == date(2026, 3, 1)


def test_custom_rule_cannot_be_ready_with_unhandled_account_segment_type():
    rule = AllocationRule(
        account_id='a1',
        minimum_payment_allocation_rule=assumed_default(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),
        excess_payment_allocation_rule=assumed_default(AllocationRuleType.STATUTORY_DEFAULT),
        minimum_rule_configuration=IssuerAllocationConfiguration(
            segment_priority_order=(SegmentType.CASH_ADVANCE,), is_resolved=True,
        ),
    )
    account = _account(segments=(_segment(segment_type=SegmentType.STANDARD_PURCHASE),),allocation_rule=rule)
    FinancialSnapshot(revolving_accounts=(account,))
    assert not account.allocation_rule.calculation_ready
