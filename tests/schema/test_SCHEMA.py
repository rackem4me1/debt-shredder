"""
test_SCHEMA.py — validation suite for SCHEMA.py revision 4 (SPEC.md v2.4)

Fixes the one failing test the last review found: `_account()` now derives
its default segment's and allocation_rule's account_id from whatever
account_id is passed in, instead of hardcoding "a1" independent of an
account_id override. This was a fixture defect, confirmed by the review's
own diagnostic patch — fixed generally here rather than special-cased for
the one test that happened to expose it.

Also restores regression coverage that revision 3's full rewrite dropped
(float rejection, billing-cycle ordering, promo-term requirements,
precomputed loan/rebate combinations, minimum-remaining bounds), adapted to
the sourced/immutable/tuple representations, plus new tests for revision
4's five fixes.

NOT executed in this sandbox — no network access to install
pydantic/pytest. Run `pip install pydantic pytest && pytest
test_SCHEMA.py` on the Mac mini and report actual pass/fail counts and
installed versions before treating this as verified.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext

import pytest
from pydantic import ValidationError

from SCHEMA import (
    AccountLiquidityFloor,
    AllocationRequest,
    AllocationRule,
    AllocationRuleType,
    BalanceSegment,
    BillingCycle,
    CompoundingMethod,
    DayCountConvention,
    DeferredInterestCalculationMethod,
    FinancialSnapshot,
    IncomeCadence,
    IncomeSource,
    InstallmentLoan,
    IssuerAllocationConfiguration,
    LiquidityAccount,
    LiquidityAccountType,
    LoanType,
    MinimumPaymentSnapshot,
    Payment,
    PaymentStatus,
    PrepaymentBehavior,
    PromoSinkingTarget,
    ProvenanceSource,
    RebateMethod,
    RevolvingAccount,
    ScheduledObligation,
    SegmentType,
    SemimonthlyShortMonthRule,
    SinkingFundAllocation,
    Sourced,
    Transfer,
    TransferStatus,
    TransferTimingPolicy,
    assumed_default,
)

T0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)


def sourced(value, provenance=ProvenanceSource.ASSUMED_DEFAULT, confirmed_date=None):
    return Sourced(value=value, provenance=provenance, confirmed_date=confirmed_date)


def _allocation_rule(account_id="a1", consumer_override=False):
    return AllocationRule(
        account_id=account_id,
        minimum_payment_allocation_rule=sourced(AllocationRuleType.STATUTORY_DEFAULT),
        excess_payment_allocation_rule=sourced(AllocationRuleType.STATUTORY_DEFAULT),
        consumer_override_supported=sourced(consumer_override),
    )


def _segment(**overrides):
    defaults = dict(
        segment_id="s1",
        account_id="a1",
        segment_type=SegmentType.STANDARD_PURCHASE,
        balance=Decimal("500"),
        apr=sourced(Decimal("0.2499")),
        compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
        day_count_convention=sourced(DayCountConvention.ACTUAL_365),
    )
    defaults.update(overrides)
    return BalanceSegment(**defaults)


def _account(**overrides):
    # Fixed per the last review: the default segment and allocation_rule
    # now derive their account_id from whatever account_id is passed, so
    # `_account(account_id="X")` alone produces an internally-consistent
    # account instead of failing on a mismatched child record before the
    # test's actual assertion is ever reached.
    account_id = overrides.get("account_id", "a1")
    defaults = dict(
        account_id=account_id,
        issuer="Test Bank",
        segments=(_segment(account_id=account_id),),
        allocation_rule=_allocation_rule(account_id=account_id),
        statement_close_day=15,
        payment_due_day=10,
    )
    defaults.update(overrides)
    return RevolvingAccount(**defaults)


def _liquidity_account(**overrides):
    defaults = dict(
        account_id="chk1", institution="Capital One",
        account_type=LiquidityAccountType.CHECKING,
        cleared_balance=Decimal("1000"), is_primary=True,
    )
    defaults.update(overrides)
    return LiquidityAccount(**defaults)


def _loan(**overrides):
    defaults = dict(
        loan_id="l1", servicer="Test Servicer", loan_type=LoanType.SIMPLE_INTEREST,
        principal_balance=Decimal("12000"),
        contract_note_rate=sourced(Decimal("0.089"), ProvenanceSource.CONTRACTUAL_DISCLOSURE, date(2026, 1, 1)),
        disclosed_apr=sourced(Decimal("0.091"), ProvenanceSource.CONTRACTUAL_DISCLOSURE, date(2026, 1, 1)),
        day_count_convention=assumed_default(DayCountConvention.ACTUAL_365),
        contractual_payment_amount=assumed_default(Decimal("350.00")),
        payment_due_day=5, next_due_date=date(2026, 2, 5),
        prepayment_behavior=assumed_default(PrepaymentBehavior.PRINCIPAL_ONLY_CURTAILMENT),
    )
    defaults.update(overrides)
    return InstallmentLoan(**defaults)


# ============================================================
# 0. The fixed fixture bug from the last review
# ============================================================

def test_revolving_and_loan_id_collision_rejected():
    acct = _account(account_id="shared")
    loan = _loan(loan_id="shared")
    with pytest.raises(ValidationError, match="collision"):
        FinancialSnapshot(revolving_accounts=(acct,), installment_loans=(loan,))


def test_account_override_cascades_to_child_records():
    acct = _account(account_id="custom")
    assert acct.segments[0].account_id == "custom"
    assert acct.allocation_rule.account_id == "custom"


# ============================================================
# 1. Restored: float rejection
# ============================================================

def test_float_balance_rejected():
    with pytest.raises(ValidationError):
        _segment(balance=499.99)


def test_float_apr_value_rejected_inside_sourced():
    with pytest.raises(ValidationError):
        sourced(0.2499)


def test_str_and_int_accepted_for_decimal_fields():
    seg = _segment(balance="500.00")
    assert seg.balance == Decimal("500.00")


def test_installment_loan_rejects_float_principal():
    with pytest.raises(ValidationError):
        _loan(principal_balance=12000.00)


# ============================================================
# 2. Restored: billing-cycle ordering
# ============================================================

def test_billing_cycle_valid_ordering():
    cycle = BillingCycle(
        cycle_id="c1", account_id="a1",
        start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
        statement_date=date(2026, 1, 31), due_date=date(2026, 2, 20),
    )
    assert cycle.is_closed is False


def test_billing_cycle_rejects_due_date_before_statement_date():
    with pytest.raises(ValidationError):
        BillingCycle(
            cycle_id="c1", account_id="a1",
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
            statement_date=date(2026, 1, 31), due_date=date(2026, 1, 15),
        )


def test_billing_cycle_rejects_end_before_start():
    with pytest.raises(ValidationError):
        BillingCycle(
            cycle_id="c1", account_id="a1",
            start_date=date(2026, 1, 31), end_date=date(2026, 1, 1),
            statement_date=date(2026, 1, 31), due_date=date(2026, 2, 20),
        )


# ============================================================
# 3. Restored: required promo terms
# ============================================================

def test_promo_segment_requires_expiration_date():
    with pytest.raises(ValidationError):
        _segment(
            segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO, apr=sourced(Decimal("0")),
            post_promo_apr=sourced(Decimal("0.2699")),
            post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
        )


def test_promo_segment_requires_post_promo_apr():
    with pytest.raises(ValidationError):
        _segment(
            segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO, apr=sourced(Decimal("0")),
            promo_expiration_date=date(2027, 1, 1),
            post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
        )


def test_promo_segment_requires_post_promo_compounding_method():
    with pytest.raises(ValidationError):
        _segment(
            segment_type=SegmentType.PROMOTIONAL_TRUE_ZERO, apr=sourced(Decimal("0")),
            promo_expiration_date=date(2027, 1, 1), post_promo_apr=sourced(Decimal("0.2699")),
        )


def test_deferred_segment_requires_deferred_interest_apr_and_method():
    with pytest.raises(ValidationError):
        _segment(
            segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST, apr=sourced(Decimal("0")),
            promo_expiration_date=date(2027, 1, 1), post_promo_apr=sourced(Decimal("0.2699")),
            post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
            deferred_interest_to_date=Decimal("180"),
            projected_deferred_interest_at_expiration=Decimal("200"),
        )


def test_active_deferred_interest_segment_rejects_nonzero_billed_apr():
    with pytest.raises(ValidationError, match="apr.value == 0"):
        _segment(
            segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST, apr=sourced(Decimal("0.25")),
            promo_expiration_date=date(2027, 1, 1), post_promo_apr=sourced(Decimal("0.2699")),
            post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
            deferred_interest_apr=sourced(Decimal("0.2999")),
            deferred_interest_calculation_method=sourced(
                DeferredInterestCalculationMethod.AVERAGE_DAILY_BALANCE_SIMPLE
            ),
        )


@pytest.mark.parametrize("method", list(DeferredInterestCalculationMethod))
def test_each_spec_defined_deferred_method_constructs_and_serializes(method):
    seg = _segment(
        segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST, apr=sourced(Decimal("0")),
        promo_expiration_date=date(2027, 1, 1), post_promo_apr=sourced(Decimal("0.2699")),
        post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
        deferred_interest_to_date=Decimal("180"),
        projected_deferred_interest_at_expiration=Decimal("200"),
        deferred_interest_apr=sourced(Decimal("0.2999")),
        deferred_interest_calculation_method=sourced(method),
    )
    restored = BalanceSegment.model_validate(seg.model_dump())
    assert restored.deferred_interest_calculation_method.value == method


# ============================================================
# 4. Restored: precomputed loan/rebate combinations
# ============================================================

def test_precomputed_loan_requires_rebate_method():
    with pytest.raises(ValidationError):
        _loan(loan_type=LoanType.PRECOMPUTED,
              prepayment_behavior=assumed_default(PrepaymentBehavior.PRECOMPUTED_REBATE_REDUCTION))


def test_precomputed_loan_requires_matching_prepayment_behavior():
    with pytest.raises(ValidationError):
        _loan(loan_type=LoanType.PRECOMPUTED, rebate_method=assumed_default(RebateMethod.RULE_OF_78))


def test_precomputed_loan_valid_with_matching_terms():
    loan = _loan(
        loan_type=LoanType.PRECOMPUTED, rebate_method=assumed_default(RebateMethod.RULE_OF_78),
        prepayment_behavior=assumed_default(PrepaymentBehavior.PRECOMPUTED_REBATE_REDUCTION),
    )
    assert loan.rebate_method.value == RebateMethod.RULE_OF_78


def test_simple_interest_loan_rejects_rebate_method():
    with pytest.raises(ValidationError):
        _loan(rebate_method=assumed_default(RebateMethod.ACTUARIAL))


def test_installment_loan_rejects_negative_note_rate():
    with pytest.raises(ValidationError, match="contract_note_rate"):
        _loan(contract_note_rate=assumed_default(Decimal("-0.01")))


def test_installment_loan_allows_rate_above_100_percent_no_invented_ceiling():
    loan = _loan(contract_note_rate=assumed_default(Decimal("1.5")))
    assert loan.contract_note_rate.value == Decimal("1.5")


# ============================================================
# 5. Restored: minimum-remaining bounds
# ============================================================

def test_minimum_payment_snapshot_remaining_cannot_exceed_original():
    with pytest.raises(ValidationError):
        MinimumPaymentSnapshot(
            account_id="a1", billing_cycle_id="c1",
            statement_minimum_original=Decimal("125"), statement_minimum_remaining=Decimal("200"),
        )


def test_minimum_payment_snapshot_tracks_partial_credit_correctly():
    snap = MinimumPaymentSnapshot(
        account_id="a1", billing_cycle_id="c1",
        statement_minimum_original=Decimal("125"), statement_minimum_remaining=Decimal("50"),
    )
    assert snap.statement_minimum_remaining == Decimal("50")


def test_minimum_payment_snapshot_provenance_replaces_binary_is_actual():
    snap = MinimumPaymentSnapshot(
        account_id="a1", billing_cycle_id="c1",
        statement_minimum_original=Decimal("125"), statement_minimum_remaining=Decimal("125"),
        provenance=ProvenanceSource.ACTUAL_STATEMENT, as_of_date=date(2026, 1, 15),
    )
    assert snap.provenance == ProvenanceSource.ACTUAL_STATEMENT


def test_minimum_payment_snapshot_actual_statement_requires_date():
    with pytest.raises(ValidationError):
        MinimumPaymentSnapshot(
            account_id="a1", billing_cycle_id="c1",
            statement_minimum_original=Decimal("125"), statement_minimum_remaining=Decimal("125"),
            provenance=ProvenanceSource.ACTUAL_STATEMENT,
        )


# ============================================================
# New — Finding #1: allocation-request ownership & aggregate limits
# ============================================================

def test_allocation_request_rejects_payment_from_different_account():
    acct1 = _account(account_id="a1", allocation_rule=_allocation_rule(account_id="a1", consumer_override=True))
    acct2 = _account(account_id="a2", allocation_rule=_allocation_rule(account_id="a2", consumer_override=True))
    payment = Payment(payment_id="p1", account_id="a2", source_liquidity_account_id="chk1",
                       amount=Decimal("100"), status=PaymentStatus.INITIATED, initiated_at=T0)
    req = AllocationRequest(request_id="r1", account_id="a1", segment_id="s1",
                             payment_id="p1", requested_amount=Decimal("50"))
    with pytest.raises(ValidationError, match="does not match"):
        FinancialSnapshot(
            revolving_accounts=(acct1, acct2), liquidity_accounts=(_liquidity_account(),),
            payments=(payment,), allocation_requests=(req,),
        )


def test_allocation_requests_sum_rejected_when_exceeding_payment_total():
    acct = _account(allocation_rule=_allocation_rule(consumer_override=True))
    payment = Payment(payment_id="p1", account_id="a1", source_liquidity_account_id="chk1",
                       amount=Decimal("100"), status=PaymentStatus.INITIATED, initiated_at=T0)
    req1 = AllocationRequest(request_id="r1", account_id="a1", segment_id="s1",
                              payment_id="p1", requested_amount=Decimal("60"))
    req2 = AllocationRequest(request_id="r2", account_id="a1", segment_id="s1",
                              payment_id="p1", requested_amount=Decimal("60"))
    with pytest.raises(ValidationError, match="sum to"):
        FinancialSnapshot(
            revolving_accounts=(acct,), liquidity_accounts=(_liquidity_account(),),
            payments=(payment,), allocation_requests=(req1, req2),
        )


def test_allocation_requests_valid_multiple_within_payment_total():
    acct = _account(allocation_rule=_allocation_rule(consumer_override=True))
    payment = Payment(payment_id="p1", account_id="a1", source_liquidity_account_id="chk1",
                       amount=Decimal("100"), status=PaymentStatus.INITIATED, initiated_at=T0)
    req1 = AllocationRequest(request_id="r1", account_id="a1", segment_id="s1",
                              payment_id="p1", requested_amount=Decimal("40"))
    req2 = AllocationRequest(request_id="r2", account_id="a1", segment_id="s1",
                              payment_id="p1", requested_amount=Decimal("60"))
    snapshot = FinancialSnapshot(
        revolving_accounts=(acct,), liquidity_accounts=(_liquidity_account(),),
        payments=(payment,), allocation_requests=(req1, req2),
    )
    assert len(snapshot.allocation_requests) == 2


# ============================================================
# New — Finding #2: resolvable issuer allocation configuration
# ============================================================

def test_issuer_specific_configured_requires_structured_configuration_not_citation_alone():
    with pytest.raises(ValidationError, match="minimum_rule_configuration"):
        AllocationRule(
            account_id="a1",
            minimum_payment_allocation_rule=sourced(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),
            excess_payment_allocation_rule=sourced(AllocationRuleType.STATUTORY_DEFAULT),
        )


def test_issuer_configuration_rejects_empty_priority_order():
    with pytest.raises(ValidationError):
        IssuerAllocationConfiguration(segment_priority_order=())


def test_issuer_configuration_rejects_duplicate_segment_types():
    with pytest.raises(ValidationError):
        IssuerAllocationConfiguration(
            segment_priority_order=(SegmentType.CASH_ADVANCE, SegmentType.CASH_ADVANCE)
        )


def test_allocation_rule_calculation_ready_false_when_unresolved():
    rule = AllocationRule(
        account_id="a1",
        minimum_payment_allocation_rule=sourced(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),
        excess_payment_allocation_rule=sourced(AllocationRuleType.STATUTORY_DEFAULT),
        minimum_rule_configuration=IssuerAllocationConfiguration(
            segment_priority_order=(SegmentType.CASH_ADVANCE, SegmentType.STANDARD_PURCHASE),
            is_resolved=False, citation="Cardholder Agreement §4.2",
        ),
    )
    assert rule.calculation_ready is False


def test_resolved_custom_rule_requires_account_context_for_readiness():
    rule = AllocationRule(
        account_id="a1",
        minimum_payment_allocation_rule=sourced(AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED),
        excess_payment_allocation_rule=sourced(AllocationRuleType.STATUTORY_DEFAULT),
        minimum_rule_configuration=IssuerAllocationConfiguration(
            segment_priority_order=(SegmentType.CASH_ADVANCE, SegmentType.STANDARD_PURCHASE),
            is_resolved=True,
        ),
    )
    assert rule.calculation_ready is False
    assert _account(allocation_rule=rule).calculation_ready is True


def test_allocation_rule_calculation_ready_true_for_concrete_statutory_default():
    assert _allocation_rule().calculation_ready is True


# ============================================================
# New — Finding #3: semimonthly schedule validation
# ============================================================

def test_semimonthly_days_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        SinkingFundAllocation(
            allocation_id="sf1", account_id="sav1", purpose="x",
            reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
            planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
            planned_contribution_source_account_id="chk1",
            planned_contribution_next_date=date(2026, 1, 15),
            planned_contribution_semimonthly_days=(0, 99),
            planned_contribution_semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
        )


def test_semimonthly_days_rejects_equal_values():
    with pytest.raises(ValidationError):
        SinkingFundAllocation(
            allocation_id="sf1", account_id="sav1", purpose="x",
            reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
            planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
            planned_contribution_source_account_id="chk1",
            planned_contribution_next_date=date(2026, 1, 15),
            planned_contribution_semimonthly_days=(15, 15),
            planned_contribution_semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
        )


def test_semimonthly_requires_short_month_rule():
    with pytest.raises(ValidationError, match="SEMIMONTHLY"):
        SinkingFundAllocation(
            allocation_id="sf1", account_id="sav1", purpose="x",
            reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
            planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
            planned_contribution_source_account_id="chk1",
            planned_contribution_next_date=date(2026, 1, 15),
            planned_contribution_semimonthly_days=(1, 15),
        )


def test_semimonthly_next_date_must_match_schedule():
    with pytest.raises(ValidationError, match="does not match"):
        SinkingFundAllocation(
            allocation_id="sf1", account_id="sav1", purpose="x",
            reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
            planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
            planned_contribution_source_account_id="chk1",
            planned_contribution_next_date=date(2026, 1, 20),  # not 1 or 15
            planned_contribution_semimonthly_days=(1, 15),
            planned_contribution_semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
        )


def test_semimonthly_short_month_clamp_accepts_last_day_of_february():
    allocation = SinkingFundAllocation(
        allocation_id="sf1", account_id="sav1", purpose="x",
        reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
        planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
        planned_contribution_source_account_id="chk1",
        planned_contribution_next_date=date(2026, 2, 28),  # Feb 2026 has 28 days; day 31 clamps here
        planned_contribution_semimonthly_days=(15, 31),
        planned_contribution_semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
    )
    assert allocation.planned_contribution_next_date == date(2026, 2, 28)


def test_semimonthly_short_month_roll_rejects_clamped_date():
    # Under ROLL_TO_NEXT_MONTH_FIRST_DAY, day 31 simply doesn't occur in
    # February at all — Feb 28 is NOT a valid date under this rule.
    with pytest.raises(ValidationError, match="does not match"):
        SinkingFundAllocation(
            allocation_id="sf1", account_id="sav1", purpose="x",
            reserved_amount=Decimal("0"), planned_contribution_amount=Decimal("50"),
            planned_contribution_cadence=IncomeCadence.SEMIMONTHLY,
            planned_contribution_source_account_id="chk1",
            planned_contribution_next_date=date(2026, 2, 28),
            planned_contribution_semimonthly_days=(15, 31),
            planned_contribution_semimonthly_short_month_rule=SemimonthlyShortMonthRule.ROLL_TO_NEXT_MONTH_FIRST_DAY,
        )


def test_income_source_semimonthly_requires_two_day_schedule():
    with pytest.raises(ValidationError, match="SEMIMONTHLY"):
        IncomeSource(
            source_id="i1", destination_account_id="chk1", cadence=IncomeCadence.SEMIMONTHLY,
            amount=Decimal("1000"), anchor_date=date(2026, 1, 15),
        )


def test_income_source_semimonthly_valid_with_full_schedule():
    inc = IncomeSource(
        source_id="i1", destination_account_id="chk1", cadence=IncomeCadence.SEMIMONTHLY,
        amount=Decimal("1000"), anchor_date=date(2026, 1, 15),
        semimonthly_days=(1, 15),
        semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
    )
    assert inc.semimonthly_days == (1, 15)


def test_income_source_semimonthly_rejects_anchor_date_off_schedule():
    with pytest.raises(ValidationError, match="does not match"):
        IncomeSource(
            source_id="i1", destination_account_id="chk1", cadence=IncomeCadence.SEMIMONTHLY,
            amount=Decimal("1000"), anchor_date=date(2026, 1, 16),  # schedule is 1/15, not 1/16
            semimonthly_days=(1, 15),
            semimonthly_short_month_rule=SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH,
        )


# ============================================================
# New — Finding #4: timing-policy routes, income/obligation IDs, one minimum per cycle
# ============================================================

def test_duplicate_timing_policy_route_rejected():
    with pytest.raises(ValidationError, match="at most one TransferTimingPolicy"):
        FinancialSnapshot(
            liquidity_accounts=(
                _liquidity_account(account_id="chk1"),
                LiquidityAccount(account_id="sav1", institution="Capital One",
                                  account_type=LiquidityAccountType.SAVINGS, cleared_balance=Decimal("500")),
            ),
            transfer_timing_policies=(
                TransferTimingPolicy(source_account_id="chk1", dest_account_id="sav1",
                                      expected_business_days=sourced(0)),
                TransferTimingPolicy(source_account_id="chk1", dest_account_id="sav1",
                                      expected_business_days=sourced(3)),
            ),
        )


def test_timing_policy_rejects_self_route():
    with pytest.raises(ValidationError, match="must differ"):
        TransferTimingPolicy(source_account_id="chk1", dest_account_id="chk1",
                              expected_business_days=sourced(1))


def test_duplicate_income_source_id_rejected():
    with pytest.raises(ValidationError, match="IncomeSource.source_id must be unique"):
        FinancialSnapshot(
            liquidity_accounts=(_liquidity_account(),),
            income_sources=(
                IncomeSource(source_id="dup", destination_account_id="chk1",
                              cadence=IncomeCadence.WEEKLY, amount=Decimal("800"),
                              anchor_date=date(2026, 1, 2), weekday=4),
                IncomeSource(source_id="dup", destination_account_id="chk1",
                              cadence=IncomeCadence.WEEKLY, amount=Decimal("800"),
                              anchor_date=date(2026, 1, 9), weekday=4),
            ),
        )


def test_duplicate_obligation_id_rejected():
    with pytest.raises(ValidationError, match="obligation_id must be unique"):
        FinancialSnapshot(
            liquidity_accounts=(_liquidity_account(),),
            obligations=(
                ScheduledObligation(obligation_id="dup", source_account_id="chk1",
                                     description="rent", amount=Decimal("1200"), due_date=date(2026, 2, 1)),
                ScheduledObligation(obligation_id="dup", source_account_id="chk1",
                                     description="rent again", amount=Decimal("1200"), due_date=date(2026, 3, 1)),
            ),
        )


def test_two_minimum_snapshots_for_same_cycle_rejected():
    cycle = BillingCycle(cycle_id="c1", account_id="a1",
                          start_date=date(2026, 1, 1), end_date=date(2026, 1, 31),
                          statement_date=date(2026, 1, 31), due_date=date(2026, 2, 20))
    with pytest.raises(ValidationError, match="at most one MinimumPaymentSnapshot"):
        FinancialSnapshot(
            revolving_accounts=(_account(),), billing_cycles=(cycle,),
            minimum_payment_snapshots=(
                MinimumPaymentSnapshot(account_id="a1", billing_cycle_id="c1",
                                        statement_minimum_original=Decimal("125"),
                                        statement_minimum_remaining=Decimal("125")),
                MinimumPaymentSnapshot(account_id="a1", billing_cycle_id="c1",
                                        statement_minimum_original=Decimal("125"),
                                        statement_minimum_remaining=Decimal("50")),
            ),
        )


# ============================================================
# New — Finding #5: split provenance for accrued/deferred interest
# ============================================================

def test_accrued_interest_provenance_independent_of_balance_provenance():
    seg = _segment(
        balance_provenance=ProvenanceSource.ACTUAL_STATEMENT, balance_as_of_date=date(2026, 1, 1),
        accrued_unposted_interest=Decimal("4.21"),
        accrued_interest_provenance=ProvenanceSource.ASSUMED_DEFAULT,  # a live projection, not statement-verified
    )
    assert seg.balance_provenance == ProvenanceSource.ACTUAL_STATEMENT
    assert seg.accrued_interest_provenance == ProvenanceSource.ASSUMED_DEFAULT


def test_accrued_interest_actual_statement_requires_its_own_date():
    with pytest.raises(ValidationError, match="accrued_interest_as_of_date"):
        _segment(accrued_interest_provenance=ProvenanceSource.ACTUAL_STATEMENT)


def test_deferred_interest_provenance_independent_and_dated():
    seg = _segment(
        segment_type=SegmentType.PROMOTIONAL_DEFERRED_INTEREST, apr=sourced(Decimal("0")),
        promo_expiration_date=date(2027, 1, 1), post_promo_apr=sourced(Decimal("0.2699")),
        post_promo_compounding_method=sourced(CompoundingMethod.SIMPLE_DAILY),
        deferred_interest_to_date=Decimal("180"),
        projected_deferred_interest_at_expiration=Decimal("200"),
        deferred_interest_apr=sourced(Decimal("0.2999")),
        deferred_interest_calculation_method=sourced(
            DeferredInterestCalculationMethod.RETROACTIVE_PURCHASE_SUM
        ),
        deferred_interest_provenance=ProvenanceSource.USER_CONFIRMED,
        deferred_interest_as_of_date=date(2026, 1, 1),
    )
    assert seg.deferred_interest_provenance == ProvenanceSource.USER_CONFIRMED


# ============================================================
# Immutability, snapshot basics, remaining coverage
# ============================================================

def test_segment_is_frozen_rejects_any_field_assignment():
    seg = _segment()
    with pytest.raises(ValidationError):
        seg.balance = Decimal("999")


def test_sourced_nested_value_is_frozen_rejects_assignment():
    seg = _segment()
    with pytest.raises(ValidationError):
        seg.apr.value = Decimal("-1")


def test_segments_tuple_has_no_append_method():
    acct = _account()
    assert not hasattr(acct.segments, "append")


def test_blank_snapshot_is_valid():
    assert FinancialSnapshot().liquidity_accounts == ()


def test_sinking_fund_reserve_does_not_reduce_a_different_accounts_cash():
    snapshot = FinancialSnapshot(
        liquidity_accounts=(
            _liquidity_account(account_id="chk1", cleared_balance=Decimal("1000")),
            LiquidityAccount(account_id="sav1", institution="Capital One",
                              account_type=LiquidityAccountType.SAVINGS, cleared_balance=Decimal("1500")),
        ),
        liquidity_floors=(
            AccountLiquidityFloor(account_id="chk1", minimum_balance=Decimal("0")),
            AccountLiquidityFloor(account_id="sav1", minimum_balance=Decimal("0")),
        ),
        sinking_funds=(
            SinkingFundAllocation(allocation_id="sf1", account_id="sav1",
                                   purpose="emergency fund", reserved_amount=Decimal("1200")),
        ),
    )
    assert snapshot.unrestricted_cash("chk1") == Decimal("1000")
    assert snapshot.unrestricted_cash("sav1") == Decimal("300")


def test_unrestricted_cash_requires_explicit_floor():
    snapshot = FinancialSnapshot(liquidity_accounts=(_liquidity_account(),))
    with pytest.raises(KeyError, match="no AccountLiquidityFloor"):
        snapshot.unrestricted_cash("chk1")


def test_total_balance_independent_of_a_low_ambient_decimal_context():
    seg1 = _segment(segment_id="s1", balance=Decimal("1234567890123456789.123456789"))
    seg2 = _segment(segment_id="s2", balance=Decimal("9876543210987654321.987654321"))
    acct = _account(segments=(seg1, seg2))
    expected = Decimal("1234567890123456789.123456789") + Decimal("9876543210987654321.987654321")
    with localcontext(Context(prec=6)):
        result = acct.total_balance()
    assert result == expected


def test_transfer_valid_full_lifecycle():
    transfer = Transfer(
        transfer_id="t1", source_account_id="chk1", dest_account_id="sav1",
        amount=Decimal("500"), status=TransferStatus.SETTLED, initiated_at=T0,
        debited_source_at=T0 + timedelta(hours=1),
        credited_dest_at=T0 + timedelta(days=1),
        settled_at=T0 + timedelta(days=3),
    )
    assert transfer.status == TransferStatus.SETTLED


def test_initiated_status_rejects_settled_at_populated():
    with pytest.raises(ValidationError, match="must not have settled_at set"):
        Payment(
            payment_id="p1", account_id="a1", source_liquidity_account_id="chk1",
            amount=Decimal("100"), status=PaymentStatus.INITIATED, initiated_at=T0,
            settled_at=T0 + timedelta(days=3),
        )
