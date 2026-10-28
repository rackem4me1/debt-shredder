"""Debt Shredder Phase 2 revision 5. Frozen SPEC.md v2.4 unchanged.
Validated calendar schedules and account-aware custom allocation readiness.
Records remain immutable; reconstruct through validation for updates.
No production calculation engine is included.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from enum import Enum
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T")

_DECIMAL_CTX = Context(prec=28)  # spec §2.1: at least 28 significant digits


# ---------------------------------------------------------------------------
# Shared base & helpers
# ---------------------------------------------------------------------------

class StrictModel(BaseModel):
    """extra="forbid": unknown fields rejected, not dropped. frozen=True:
    records are immutable. Construct a new instance (not model_copy) to
    change a field — that's the only validated update path."""
    model_config = ConfigDict(extra="forbid", frozen=True)


def _reject_float(v):
    if isinstance(v, float):
        raise ValueError(
            "float is not accepted for monetary/rate fields — pass str, int, or Decimal"
        )
    return v


def _require_aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is not None and v.tzinfo is None:
        raise ValueError("datetime fields must be timezone-aware (spec §7.4 lifecycle timing)")
    return v


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class RoundingMode(str, Enum):
    HALF_UP = "ROUND_HALF_UP"
    HALF_EVEN = "ROUND_HALF_EVEN"
    FLOOR = "ROUND_FLOOR"
    CEILING = "ROUND_CEILING"
    TRUNCATE = "ROUND_TRUNCATE"


class CompoundingMethod(str, Enum):
    SIMPLE_DAILY = "simple_daily"
    DAILY_COMPOUNDING = "daily_compounding"
    MONTHLY_COMPOUNDING = "monthly_compounding"


class DayCountConvention(str, Enum):
    ACTUAL_365 = "actual_365_fixed"
    ACTUAL_366 = "actual_366"
    ACTUAL_ACTUAL = "actual_actual"
    THIRTY_360 = "30_360_nasd"


class SegmentType(str, Enum):
    STANDARD_PURCHASE = "standard_purchase"
    PROMOTIONAL_TRUE_ZERO = "promotional_true_zero"
    PROMOTIONAL_DEFERRED_INTEREST = "promotional_deferred_interest"
    BALANCE_TRANSFER = "balance_transfer"
    CASH_ADVANCE = "cash_advance"
    FEES_AND_PENALTIES = "fees_and_penalties"


_PROMO_TYPES = {
    SegmentType.PROMOTIONAL_TRUE_ZERO,
    SegmentType.PROMOTIONAL_DEFERRED_INTEREST,
    SegmentType.BALANCE_TRANSFER,
}

_GRACE_INELIGIBLE_TYPES = {
    SegmentType.CASH_ADVANCE,
    SegmentType.FEES_AND_PENALTIES,
    SegmentType.BALANCE_TRANSFER,
}

_ZERO_BILLED_APR_TYPES = {SegmentType.PROMOTIONAL_TRUE_ZERO, SegmentType.PROMOTIONAL_DEFERRED_INTEREST}


class GracePeriodState(str, Enum):
    PENDING = "pending"
    FULL_GRACE = "full_grace"
    LOST_GRACE = "lost_grace"


class LoanType(str, Enum):
    SIMPLE_INTEREST = "simple_interest"
    PRECOMPUTED = "precomputed"


class RebateMethod(str, Enum):
    RULE_OF_78 = "rule_of_78"
    ACTUARIAL = "actuarial"


class PrepaymentBehavior(str, Enum):
    PRINCIPAL_ONLY_CURTAILMENT = "principal_only_curtailment"
    PAID_AHEAD = "paid_ahead"
    PRECOMPUTED_REBATE_REDUCTION = "precomputed_rebate_reduction"


class DeferredInterestCalculationMethod(str, Enum):
    AVERAGE_DAILY_BALANCE_SIMPLE = "average_daily_balance_simple"
    DAILY_COMPOUNDING = "daily_compounding"
    RETROACTIVE_PURCHASE_SUM = "retroactive_purchase_sum"


class IncomeCadence(str, Enum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMIMONTHLY = "semimonthly"
    MONTHLY = "monthly"
    IRREGULAR = "irregular"


class SemimonthlyShortMonthRule(str, Enum):
    """How a semimonthly schedule's later day resolves in a month too short
    to contain it (e.g. day 31 in February)."""
    CLAMP_TO_LAST_DAY_OF_MONTH = "clamp_to_last_day_of_month"
    ROLL_TO_NEXT_MONTH_FIRST_DAY = "roll_to_next_month_first_day"


class PaymentStatus(str, Enum):
    INITIATED = "initiated"
    CREDITED = "credited"
    DEBITED = "debited"
    SETTLED = "settled"


class TransferStatus(str, Enum):
    INITIATED = "initiated"
    DEBITED_SOURCE = "debited_source"
    CREDITED_DEST = "credited_dest"
    SETTLED = "settled"


class ProvenanceSource(str, Enum):
    ACTUAL_STATEMENT = "actual_statement"
    CONTRACTUAL_DISCLOSURE = "contractual_disclosure"
    USER_CONFIRMED = "user_confirmed"
    USER_PROVIDED_ESTIMATE = "user_provided_estimate"
    ASSUMED_DEFAULT = "assumed_default"


class AllocationRuleType(str, Enum):
    STATUTORY_DEFAULT = "statutory_default"
    LOWEST_APR_FIRST = "lowest_apr_first"
    FEES_FINANCE_CHARGES_FIRST = "fees_finance_charges_first"
    PRO_RATA = "pro_rata"
    ISSUER_SPECIFIC_CONFIGURED = "issuer_specific_configured"  # see AllocationRule.*_rule_configuration
    CONSUMER_DIRECTED = "consumer_directed"


class LiquidityAccountType(str, Enum):
    CHECKING = "checking"
    SAVINGS = "savings"
    MONEY_MARKET = "money_market"


class CashFlowStatus(str, Enum):
    HEALTHY = "healthy"
    BUFFER_BREACH = "buffer_breach"
    OBLIGATION_SHORTFALL = "obligation_shortfall"
    NEGATIVE_CASH = "negative_cash"


_DATES_REQUIRING_CONFIRMATION = {
    ProvenanceSource.ACTUAL_STATEMENT,
    ProvenanceSource.CONTRACTUAL_DISCLOSURE,
    ProvenanceSource.USER_CONFIRMED,
}


def _validate_balance_provenance(provenance: ProvenanceSource, as_of_date: Optional[date], label: str):
    if provenance in _DATES_REQUIRING_CONFIRMATION and as_of_date is None:
        raise ValueError(f"{label}_provenance={provenance} requires {label}_as_of_date")


def _validate_semimonthly_days(days: tuple[int, int], label: str):
    d1, d2 = days
    if not (1 <= d1 <= 31 and 1 <= d2 <= 31):
        raise ValueError(f"{label}: both days must be between 1 and 31")
    if d1 >= d2:
        raise ValueError(f"{label}: days must be distinct and given in ascending order (day1 < day2)")


def semimonthly_occurrences(
    year: int, month: int, days: tuple[int, int], rule: SemimonthlyShortMonthRule
) -> tuple[date, date]:
    """Resolve both nominal events, retaining duplicates if dates coincide.

    Each tuple entry is one scheduled amount. Consumers must not deduplicate
    coincident events; they may aggregate their amounts on the effective date.
    """
    _validate_semimonthly_days(days, "semimonthly_days")
    rule = SemimonthlyShortMonthRule(rule)
    last_day = calendar.monthrange(year, month)[1]
    resolved = []
    for day in days:
        if day <= last_day:
            resolved.append(date(year, month, day))
        elif rule == SemimonthlyShortMonthRule.CLAMP_TO_LAST_DAY_OF_MONTH:
            resolved.append(date(year, month, last_day))
        else:
            if year == 9999 and month == 12:
                raise ValueError("rolled schedule exceeds supported calendar range")
            resolved.append(date(year + (month == 12), month % 12 + 1, 1))
    return tuple(resolved)


def _validate_date_matches_semimonthly(
    d: date, days: tuple[int, int], rule: SemimonthlyShortMonthRule, label: str
):
    occurrences = semimonthly_occurrences(d.year, d.month, days, rule)
    if (d.year, d.month) != (1, 1):
        previous_year = d.year - (d.month == 1)
        previous_month = 12 if d.month == 1 else d.month - 1
        occurrences += semimonthly_occurrences(previous_year, previous_month, days, rule)
    if d not in occurrences:
        raise ValueError(f"{label} date {d} does not match semimonthly schedule {days} under {rule}")


# ---------------------------------------------------------------------------
# Provenance wrapper
# ---------------------------------------------------------------------------

class Sourced(StrictModel, Generic[T]):
    value: T
    provenance: ProvenanceSource
    confirmed_date: Optional[date] = None

    @field_validator("value", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _confirmed_date_required(self) -> "Sourced[T]":
        if self.provenance in _DATES_REQUIRING_CONFIRMATION and self.confirmed_date is None:
            raise ValueError(
                f"provenance={self.provenance} requires confirmed_date "
                f"(only USER_PROVIDED_ESTIMATE / ASSUMED_DEFAULT may omit it)"
            )
        return self


def assumed_default(value: T) -> Sourced[T]:
    return Sourced[type(value)](value=value, provenance=ProvenanceSource.ASSUMED_DEFAULT)


# ---------------------------------------------------------------------------
# Billing cycles
# ---------------------------------------------------------------------------

class BillingCycle(StrictModel):
    cycle_id: str
    account_id: str
    start_date: date
    end_date: date
    statement_date: date
    due_date: date
    is_closed: bool = False

    @model_validator(mode="after")
    def _dates_ordered(self) -> "BillingCycle":
        if not (self.start_date < self.end_date <= self.statement_date <= self.due_date):
            raise ValueError(
                "billing cycle dates must satisfy start_date < end_date <= "
                "statement_date <= due_date"
            )
        return self


# ---------------------------------------------------------------------------
# Balance segments
# ---------------------------------------------------------------------------

class BalanceSegment(StrictModel):
    segment_id: str
    account_id: str
    segment_type: SegmentType
    balance: Decimal = Field(ge=0)
    balance_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    balance_as_of_date: Optional[date] = None

    apr: Sourced[Decimal]
    compounding_method: Sourced[CompoundingMethod]
    day_count_convention: Sourced[DayCountConvention]

    accrued_unposted_interest: Decimal = Decimal("0")
    # Separate from balance_provenance: accrued interest is very often a
    # live projection, not a statement-verified figure, and must be able to
    # say so independently (finding #5).
    accrued_interest_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    accrued_interest_as_of_date: Optional[date] = None

    promo_expiration_date: Optional[date] = None
    post_promo_apr: Optional[Sourced[Decimal]] = None
    post_promo_compounding_method: Optional[Sourced[CompoundingMethod]] = None
    balance_transfer_fee: Optional[Decimal] = None

    deferred_interest_to_date: Decimal = Field(ge=0, default=Decimal("0"))
    projected_deferred_interest_at_expiration: Decimal = Field(ge=0, default=Decimal("0"))
    # Covers both deferred-interest figures above — both are frequently
    # projections, and must never silently inherit balance's provenance.
    deferred_interest_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    deferred_interest_as_of_date: Optional[date] = None
    deferred_interest_apr: Optional[Sourced[Decimal]] = None
    deferred_interest_calculation_method: Optional[Sourced[DeferredInterestCalculationMethod]] = None
    disqualification_events: tuple[date, ...] = Field(default_factory=tuple)
    is_disqualified: bool = False

    @field_validator(
        "balance", "accrued_unposted_interest", "balance_transfer_fee",
        "deferred_interest_to_date", "projected_deferred_interest_at_expiration",
        mode="before",
    )
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _validate_rates(self) -> "BalanceSegment":
        for label, sourced_rate in (
            ("apr", self.apr),
            ("post_promo_apr", self.post_promo_apr),
            ("deferred_interest_apr", self.deferred_interest_apr),
        ):
            if sourced_rate is not None and sourced_rate.value < Decimal("0"):
                raise ValueError(f"{label} must be >= 0")
        if self.segment_type in _ZERO_BILLED_APR_TYPES and self.apr.value != Decimal("0"):
            raise ValueError(
                f"{self.segment_type} segments must carry apr.value == 0 while active"
            )
        return self

    @model_validator(mode="after")
    def _validate_provenance_fields(self) -> "BalanceSegment":
        _validate_balance_provenance(self.balance_provenance, self.balance_as_of_date, "balance")
        _validate_balance_provenance(
            self.accrued_interest_provenance, self.accrued_interest_as_of_date, "accrued_interest"
        )
        _validate_balance_provenance(
            self.deferred_interest_provenance, self.deferred_interest_as_of_date, "deferred_interest"
        )
        return self

    @model_validator(mode="after")
    def _validate_promo_fields(self) -> "BalanceSegment":
        is_deferred = self.segment_type == SegmentType.PROMOTIONAL_DEFERRED_INTEREST

        if self.segment_type in _PROMO_TYPES:
            if self.promo_expiration_date is None:
                raise ValueError(f"{self.segment_type} requires promo_expiration_date")
            if self.post_promo_apr is None:
                raise ValueError(f"{self.segment_type} requires post_promo_apr")
            if self.post_promo_compounding_method is None:
                raise ValueError(f"{self.segment_type} requires post_promo_compounding_method")

        if is_deferred:
            if self.deferred_interest_apr is None:
                raise ValueError("PROMOTIONAL_DEFERRED_INTEREST requires deferred_interest_apr")
            if self.deferred_interest_calculation_method is None:
                raise ValueError(
                    "PROMOTIONAL_DEFERRED_INTEREST requires deferred_interest_calculation_method"
                )
            if self.projected_deferred_interest_at_expiration < self.deferred_interest_to_date:
                raise ValueError(
                    "projected_deferred_interest_at_expiration must be >= deferred_interest_to_date"
                )
        else:
            if (self.deferred_interest_to_date or self.projected_deferred_interest_at_expiration
                    or self.deferred_interest_apr is not None
                    or self.deferred_interest_calculation_method is not None):
                raise ValueError(
                    "deferred interest fields are only valid on PROMOTIONAL_DEFERRED_INTEREST segments"
                )
            if self.disqualification_events or self.is_disqualified:
                raise ValueError(
                    "disqualification fields are only meaningful on deferred-interest segments"
                )
        return self


# ---------------------------------------------------------------------------
# Allocation configuration
# ---------------------------------------------------------------------------

class IssuerAllocationConfiguration(StrictModel):
    """A limited custom waterfall: exhaust types in priority order.

    Within a repeated type, exhaust segments in segment_id_priority_order.
    That optional tuple must list every account segment exactly once when
    supplied, with type groups in the same order as segment_priority_order.
    This configuration represents only that waterfall, not arbitrary issuer
    behavior. Readiness also requires account coverage and explicit resolution.
    Citation is supporting documentation; the sourced rule identifies provenance.
    """
    segment_priority_order: tuple[SegmentType, ...]
    segment_id_priority_order: tuple[str, ...] = ()
    is_resolved: bool = False
    citation: Optional[str] = None  # provenance-only note, carries no semantics

    @model_validator(mode="after")
    def _validate(self) -> "IssuerAllocationConfiguration":
        if not self.segment_priority_order:
            raise ValueError("segment_priority_order must not be empty")
        if len(set(self.segment_priority_order)) != len(self.segment_priority_order):
            raise ValueError("segment_priority_order must not contain duplicate segment types")
        if len(set(self.segment_id_priority_order)) != len(self.segment_id_priority_order):
            raise ValueError("segment_id_priority_order must not contain duplicates")
        return self


class AllocationRule(StrictModel):
    account_id: str
    minimum_payment_allocation_rule: Sourced[AllocationRuleType]
    excess_payment_allocation_rule: Sourced[AllocationRuleType]
    minimum_rule_configuration: Optional[IssuerAllocationConfiguration] = None
    excess_rule_configuration: Optional[IssuerAllocationConfiguration] = None
    consumer_override_supported: Sourced[bool] = Field(default_factory=lambda: assumed_default(False))
    final_two_cycle_deferred_override_applies: Sourced[bool] = Field(
        default_factory=lambda: assumed_default(True)
    )

    @model_validator(mode="after")
    def _validate_issuer_configuration(self) -> "AllocationRule":
        if (self.minimum_payment_allocation_rule.value == AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED
                and self.minimum_rule_configuration is None):
            raise ValueError(
                "minimum_payment_allocation_rule=ISSUER_SPECIFIC_CONFIGURED requires "
                "minimum_rule_configuration"
            )
        if (self.excess_payment_allocation_rule.value == AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED
                and self.excess_rule_configuration is None):
            raise ValueError(
                "excess_payment_allocation_rule=ISSUER_SPECIFIC_CONFIGURED requires "
                "excess_rule_configuration"
            )
        return self

    @property
    def calculation_ready(self) -> bool:
        """Conservative standalone check; custom rules require account context.

        Engine consumers use RevolvingAccount.calculation_ready or
        calculation_ready_for(segments), never a resolution flag alone.
        """
        return all(rule.value != AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED for rule in (
            self.minimum_payment_allocation_rule, self.excess_payment_allocation_rule
        ))

    def calculation_ready_for(self, segments: tuple[BalanceSegment, ...]) -> bool:
        if not segments or any(seg.account_id != self.account_id for seg in segments):
            return False
        ids = tuple(seg.segment_id for seg in segments)
        if len(set(ids)) != len(ids):
            return False
        by_id = {seg.segment_id: seg for seg in segments}
        for rule_type, config in (
            (self.minimum_payment_allocation_rule.value, self.minimum_rule_configuration),
            (self.excess_payment_allocation_rule.value, self.excess_rule_configuration),
        ):
            if rule_type != AllocationRuleType.ISSUER_SPECIFIC_CONFIGURED:
                continue
            if config is None or not config.is_resolved:
                return False
            rank = {kind: index for index, kind in enumerate(config.segment_priority_order)}
            if any(seg.segment_type not in rank for seg in segments):
                return False
            repeated_types = len({seg.segment_type for seg in segments}) < len(segments)
            ordered_ids = config.segment_id_priority_order
            if repeated_types and not ordered_ids:
                return False
            if ordered_ids:
                if set(ordered_ids) != set(ids):
                    return False
                ranks = tuple(rank[by_id[id_].segment_type] for id_ in ordered_ids)
                if ranks != tuple(sorted(ranks)):
                    return False
        return True


class AllocationRequest(StrictModel):
    request_id: str
    account_id: str
    segment_id: str
    payment_id: str
    requested_amount: Decimal = Field(gt=0)

    @field_validator("requested_amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

class RevolvingAccount(StrictModel):
    account_id: str
    issuer: str
    segments: tuple[BalanceSegment, ...]
    allocation_rule: AllocationRule

    current_grace_state: GracePeriodState = GracePeriodState.PENDING
    projected_grace_state: GracePeriodState = GracePeriodState.PENDING
    grace_applies_to_segment_types: tuple[SegmentType, ...] = Field(
        default_factory=lambda: tuple(t for t in SegmentType if t not in _GRACE_INELIGIBLE_TYPES)
    )
    consecutive_statements_paid_in_full: int = Field(ge=0, default=0)
    restoration_statements_required: Sourced[int] = Field(default_factory=lambda: assumed_default(2))

    statement_close_day: int = Field(ge=1, le=31)
    payment_due_day: int = Field(ge=1, le=31)
    minimum_payment_floor: Sourced[Decimal] = Field(
        default_factory=lambda: assumed_default(Decimal("25"))
    )
    minimum_payment_rate: Sourced[Decimal] = Field(
        default_factory=lambda: assumed_default(Decimal("0.02"))
    )
    rounding_mode: Sourced[RoundingMode] = Field(
        default_factory=lambda: assumed_default(RoundingMode.HALF_UP)
    )

    @model_validator(mode="after")
    def _validate_account(self) -> "RevolvingAccount":
        if not self.segments:
            raise ValueError("RevolvingAccount requires at least one BalanceSegment")
        for seg in self.segments:
            if seg.account_id != self.account_id:
                raise ValueError(
                    f"segment {seg.segment_id} has account_id={seg.account_id!r}, "
                    f"expected {self.account_id!r}"
                )
        if len({s.segment_id for s in self.segments}) != len(self.segments):
            raise ValueError("segment_id must be unique within an account (spec §3.2)")
        if self.allocation_rule.account_id != self.account_id:
            raise ValueError(
                f"allocation_rule.account_id={self.allocation_rule.account_id!r} does not "
                f"match account_id={self.account_id!r}"
            )
        if any(t in _GRACE_INELIGIBLE_TYPES for t in self.grace_applies_to_segment_types):
            raise ValueError(
                "grace_applies_to_segment_types must not include CASH_ADVANCE, "
                "FEES_AND_PENALTIES, or BALANCE_TRANSFER"
            )
        if self.restoration_statements_required.value not in (1, 2):
            raise ValueError("restoration_statements_required.value must be 1 or 2")
        if self.minimum_payment_floor.value < 0:
            raise ValueError("minimum_payment_floor.value must be >= 0")
        if not (Decimal("0") <= self.minimum_payment_rate.value <= Decimal("1")):
            raise ValueError("minimum_payment_rate.value must be between 0 and 1")
        return self

    @property
    def calculation_ready(self) -> bool:
        """Allocation configuration is complete for this immutable account.

        This is not a claim of overall liquidity or engine readiness.
        Custom type priorities cascade in order; explicit segment IDs break
        same-type ties. No fallback or tie order is guessed.
        """
        return self.allocation_rule.calculation_ready_for(self.segments)

    def total_balance(self) -> Decimal:
        with localcontext(_DECIMAL_CTX):
            return sum((s.balance for s in self.segments), Decimal("0"))


class InstallmentLoan(StrictModel):
    loan_id: str
    servicer: str
    loan_type: LoanType
    principal_balance: Decimal = Field(ge=0)
    balances_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    balances_as_of_date: Optional[date] = None

    contract_note_rate: Sourced[Decimal]
    disclosed_apr: Sourced[Decimal]
    day_count_convention: Sourced[DayCountConvention]
    contractual_payment_amount: Sourced[Decimal]
    payment_due_day: int = Field(ge=1, le=31)
    next_due_date: date
    accrued_interest: Decimal = Field(ge=0, default=Decimal("0"))
    fees_outstanding: Decimal = Field(ge=0, default=Decimal("0"))
    prepayment_behavior: Sourced[PrepaymentBehavior]
    rebate_method: Optional[Sourced[RebateMethod]] = None
    rounding_mode: Sourced[RoundingMode] = Field(
        default_factory=lambda: assumed_default(RoundingMode.HALF_UP)
    )

    @field_validator("principal_balance", "accrued_interest", "fees_outstanding", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _validate_balances_provenance(self) -> "InstallmentLoan":
        _validate_balance_provenance(self.balances_provenance, self.balances_as_of_date, "balances")
        return self

    @model_validator(mode="after")
    def _validate_rates(self) -> "InstallmentLoan":
        if self.contract_note_rate.value < 0:
            raise ValueError("contract_note_rate must be >= 0")
        if self.disclosed_apr.value < 0:
            raise ValueError("disclosed_apr must be >= 0")
        if self.contractual_payment_amount.value < 0:
            raise ValueError("contractual_payment_amount must be >= 0")
        return self

    @model_validator(mode="after")
    def _validate_loan_type_consistency(self) -> "InstallmentLoan":
        is_precomputed_prepay = (
            self.prepayment_behavior.value == PrepaymentBehavior.PRECOMPUTED_REBATE_REDUCTION
        )
        if self.loan_type == LoanType.PRECOMPUTED:
            if self.rebate_method is None:
                raise ValueError("loan_type=PRECOMPUTED requires rebate_method")
            if not is_precomputed_prepay:
                raise ValueError(
                    "loan_type=PRECOMPUTED requires prepayment_behavior=PRECOMPUTED_REBATE_REDUCTION"
                )
        else:
            if self.rebate_method is not None:
                raise ValueError("rebate_method is only valid when loan_type=PRECOMPUTED")
            if is_precomputed_prepay:
                raise ValueError(
                    "prepayment_behavior=PRECOMPUTED_REBATE_REDUCTION requires loan_type=PRECOMPUTED"
                )
        return self


# ---------------------------------------------------------------------------
# Minimum payment tracking
# ---------------------------------------------------------------------------

class MinimumPaymentSnapshot(StrictModel):
    account_id: str
    billing_cycle_id: str
    statement_minimum_original: Decimal = Field(ge=0)
    statement_minimum_remaining: Decimal = Field(ge=0)
    # Replaces the binary is_actual with the full provenance distinction
    # (finding #5) — a projected future minimum and a billed one need more
    # than True/False to describe their source.
    provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    as_of_date: Optional[date] = None

    @field_validator("statement_minimum_original", "statement_minimum_remaining", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _remaining_cannot_exceed_original(self) -> "MinimumPaymentSnapshot":
        if self.statement_minimum_remaining > self.statement_minimum_original:
            raise ValueError("statement_minimum_remaining cannot exceed statement_minimum_original")
        return self

    @model_validator(mode="after")
    def _validate_provenance(self) -> "MinimumPaymentSnapshot":
        _validate_balance_provenance(self.provenance, self.as_of_date, "minimum_snapshot")
        return self


# ---------------------------------------------------------------------------
# Promotional sinking target — display estimate only
# ---------------------------------------------------------------------------

class PromoSinkingTarget(StrictModel):
    account_id: str
    segment_id: str
    promo_expiration_date: date
    buffer_days: int = Field(ge=5, default=5)
    remaining_payment_dates: tuple[date, ...]
    current_balance: Decimal = Field(ge=0)
    minimums_already_allocated: Decimal = Field(ge=0, default=Decimal("0"))
    is_authoritative: bool = False

    @field_validator("current_balance", "minimums_already_allocated", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @field_validator("is_authoritative")
    @classmethod
    def _forbid_true(cls, v):
        if v is True:
            raise ValueError(
                "PromoSinkingTarget.is_authoritative must be False — this model is never authoritative"
            )
        return v

    @model_validator(mode="after")
    def _validate_dates(self) -> "PromoSinkingTarget":
        if not self.remaining_payment_dates:
            raise ValueError("remaining_payment_dates must contain at least one date")
        if len(set(self.remaining_payment_dates)) != len(self.remaining_payment_dates):
            raise ValueError("remaining_payment_dates must not contain duplicates")
        deadline = self.promo_expiration_date - timedelta(days=self.buffer_days)
        if any(d > deadline for d in self.remaining_payment_dates):
            raise ValueError(
                f"remaining_payment_dates must all fall on or before the buffered deadline {deadline}"
            )
        return self

    @property
    def display_target_per_cycle(self) -> Decimal:
        with localcontext(_DECIMAL_CTX):
            net_target = self.current_balance - self.minimums_already_allocated
            n = len(self.remaining_payment_dates)
            return max(net_target, Decimal("0")) / n


# ---------------------------------------------------------------------------
# Income & obligations
# ---------------------------------------------------------------------------

class IncomeSource(StrictModel):
    source_id: str
    destination_account_id: str
    cadence: IncomeCadence
    amount: Decimal = Field(ge=0)
    anchor_date: date
    weekday: Optional[int] = Field(default=None, ge=0, le=6)
    day_of_month: Optional[int] = Field(default=None, ge=1, le=31)
    semimonthly_days: Optional[tuple[int, int]] = None
    semimonthly_short_month_rule: Optional[SemimonthlyShortMonthRule] = None

    @field_validator("amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _require_cadence_fields(self) -> "IncomeSource":
        if self.cadence in (IncomeCadence.WEEKLY, IncomeCadence.BIWEEKLY) and self.weekday is None:
            raise ValueError(f"{self.cadence} requires weekday")
        if self.cadence == IncomeCadence.MONTHLY and self.day_of_month is None:
            raise ValueError("MONTHLY cadence requires day_of_month")
        if self.cadence == IncomeCadence.SEMIMONTHLY:
            if self.semimonthly_days is None or self.semimonthly_short_month_rule is None:
                raise ValueError(
                    "SEMIMONTHLY cadence requires semimonthly_days and "
                    "semimonthly_short_month_rule — a single anchor_date cannot "
                    "distinguish e.g. 1st/15th from 1st/16th"
                )
            _validate_semimonthly_days(self.semimonthly_days, "IncomeSource.semimonthly_days")
            _validate_date_matches_semimonthly(
                self.anchor_date, self.semimonthly_days, self.semimonthly_short_month_rule,
                "IncomeSource.anchor_date",
            )
        return self


class ScheduledObligation(StrictModel):
    obligation_id: str
    source_account_id: str
    description: str
    amount: Decimal = Field(ge=0)
    due_date: date
    is_discretionary: bool = False

    @field_validator("amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)


# ---------------------------------------------------------------------------
# Payments & transfers
# ---------------------------------------------------------------------------

_PAYMENT_STAGES = ["initiated_at", "credited_at", "debited_at", "settled_at"]
_PAYMENT_STAGE_INDEX = {
    PaymentStatus.INITIATED: 0, PaymentStatus.CREDITED: 1,
    PaymentStatus.DEBITED: 2, PaymentStatus.SETTLED: 3,
}
_TRANSFER_STAGES = ["initiated_at", "debited_source_at", "credited_dest_at", "settled_at"]
_TRANSFER_STAGE_INDEX = {
    TransferStatus.INITIATED: 0, TransferStatus.DEBITED_SOURCE: 1,
    TransferStatus.CREDITED_DEST: 2, TransferStatus.SETTLED: 3,
}


def _validate_stage_consistency(stamps: dict[str, Optional[datetime]], stages: list[str], stage_index: int, kind: str):
    for i, field_name in enumerate(stages):
        present = stamps[field_name] is not None
        should_be_present = i <= stage_index
        if should_be_present and not present:
            raise ValueError(f"{kind} status requires {field_name} to be set")
        if not should_be_present and present:
            raise ValueError(f"{kind} status must not have {field_name} set yet")
    values = [stamps[f] for f in stages if stamps[f] is not None]
    if values != sorted(values):
        raise ValueError(f"{kind} timestamps must be non-decreasing")


class Payment(StrictModel):
    payment_id: str
    account_id: str
    source_liquidity_account_id: str
    segment_id: Optional[str] = None
    amount: Decimal = Field(gt=0)
    status: PaymentStatus
    initiated_at: datetime
    credited_at: Optional[datetime] = None
    debited_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None

    @field_validator("amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @field_validator("initiated_at", "credited_at", "debited_at", "settled_at")
    @classmethod
    def _tz_aware(cls, v):
        return _require_aware(v)

    @model_validator(mode="after")
    def _lifecycle_consistency(self) -> "Payment":
        stamps = {
            "initiated_at": self.initiated_at, "credited_at": self.credited_at,
            "debited_at": self.debited_at, "settled_at": self.settled_at,
        }
        _validate_stage_consistency(stamps, _PAYMENT_STAGES, _PAYMENT_STAGE_INDEX[self.status], "Payment")
        return self


class Transfer(StrictModel):
    transfer_id: str
    source_account_id: str
    dest_account_id: str
    amount: Decimal = Field(gt=0)
    status: TransferStatus
    initiated_at: datetime
    debited_source_at: Optional[datetime] = None
    credited_dest_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None

    @field_validator("amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @field_validator("initiated_at", "debited_source_at", "credited_dest_at", "settled_at")
    @classmethod
    def _tz_aware(cls, v):
        return _require_aware(v)

    @model_validator(mode="after")
    def _validate_transfer(self) -> "Transfer":
        if self.source_account_id == self.dest_account_id:
            raise ValueError("Transfer source_account_id and dest_account_id must differ")
        stamps = {
            "initiated_at": self.initiated_at, "debited_source_at": self.debited_source_at,
            "credited_dest_at": self.credited_dest_at, "settled_at": self.settled_at,
        }
        _validate_stage_consistency(stamps, _TRANSFER_STAGES, _TRANSFER_STAGE_INDEX[self.status], "Transfer")
        return self


class TransferTimingPolicy(StrictModel):
    source_account_id: str
    dest_account_id: str
    expected_business_days: Sourced[int]

    @model_validator(mode="after")
    def _validate(self) -> "TransferTimingPolicy":
        if self.source_account_id == self.dest_account_id:
            raise ValueError("TransferTimingPolicy source_account_id and dest_account_id must differ")
        if self.expected_business_days.value < 0:
            raise ValueError("expected_business_days.value must be >= 0")
        return self


# ---------------------------------------------------------------------------
# Liquidity accounts, floors, sinking funds
# ---------------------------------------------------------------------------

class LiquidityAccount(StrictModel):
    account_id: str
    institution: str
    account_type: LiquidityAccountType
    cleared_balance: Decimal
    pending_credits: Decimal = Decimal("0")
    pending_debits: Decimal = Decimal("0")
    is_primary: bool = False
    transfer_eligible_to_operational: bool = False
    balance_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    balance_as_of_date: Optional[date] = None

    @field_validator("cleared_balance", "pending_credits", "pending_debits", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @field_validator("pending_credits", "pending_debits")
    @classmethod
    def _non_negative(cls, v):
        if v < 0:
            raise ValueError("pending_credits and pending_debits must be non-negative")
        return v

    @model_validator(mode="after")
    def _validate_balance_provenance(self) -> "LiquidityAccount":
        _validate_balance_provenance(self.balance_provenance, self.balance_as_of_date, "balance")
        return self


class AccountLiquidityFloor(StrictModel):
    account_id: str
    minimum_balance: Decimal = Field(ge=0)
    provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT

    @field_validator("minimum_balance", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)


class SinkingFundAllocation(StrictModel):
    allocation_id: str
    account_id: str
    purpose: str
    reserved_amount: Decimal = Field(ge=0)
    reserved_amount_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    reserved_amount_as_of_date: Optional[date] = None

    planned_contribution_amount: Decimal = Field(ge=0, default=Decimal("0"))
    planned_contribution_cadence: Optional[IncomeCadence] = None
    planned_contribution_source_account_id: Optional[str] = None
    planned_contribution_next_date: Optional[date] = None
    planned_contribution_semimonthly_days: Optional[tuple[int, int]] = None
    planned_contribution_semimonthly_short_month_rule: Optional[SemimonthlyShortMonthRule] = None
    planned_contribution_suspended: bool = False
    target_date: Optional[date] = None

    @field_validator("reserved_amount", "planned_contribution_amount", mode="before")
    @classmethod
    def _no_float(cls, v):
        return _reject_float(v)

    @model_validator(mode="after")
    def _validate_reserved_provenance(self) -> "SinkingFundAllocation":
        _validate_balance_provenance(
            self.reserved_amount_provenance, self.reserved_amount_as_of_date, "reserved_amount"
        )
        return self

    @model_validator(mode="after")
    def _validate_planned_contribution(self) -> "SinkingFundAllocation":
        if self.planned_contribution_amount > 0:
            missing = [
                name for name, val in (
                    ("planned_contribution_cadence", self.planned_contribution_cadence),
                    ("planned_contribution_source_account_id", self.planned_contribution_source_account_id),
                    ("planned_contribution_next_date", self.planned_contribution_next_date),
                ) if val is None
            ]
            if missing:
                raise ValueError(f"planned_contribution_amount > 0 requires {', '.join(missing)}")
            if self.planned_contribution_cadence == IncomeCadence.SEMIMONTHLY:
                if (self.planned_contribution_semimonthly_days is None
                        or self.planned_contribution_semimonthly_short_month_rule is None):
                    raise ValueError(
                        "SEMIMONTHLY planned_contribution_cadence requires "
                        "planned_contribution_semimonthly_days and "
                        "planned_contribution_semimonthly_short_month_rule"
                    )
                _validate_semimonthly_days(
                    self.planned_contribution_semimonthly_days,
                    "SinkingFundAllocation.planned_contribution_semimonthly_days",
                )
                _validate_date_matches_semimonthly(
                    self.planned_contribution_next_date,
                    self.planned_contribution_semimonthly_days,
                    self.planned_contribution_semimonthly_short_month_rule,
                    "SinkingFundAllocation.planned_contribution_next_date",
                )
        return self


# ---------------------------------------------------------------------------
# Aggregate snapshot — cross-model reference validation
# ---------------------------------------------------------------------------

class FinancialSnapshot(StrictModel):
    liquidity_accounts: tuple[LiquidityAccount, ...] = Field(default_factory=tuple)
    liquidity_floors: tuple[AccountLiquidityFloor, ...] = Field(default_factory=tuple)
    revolving_accounts: tuple[RevolvingAccount, ...] = Field(default_factory=tuple)
    installment_loans: tuple[InstallmentLoan, ...] = Field(default_factory=tuple)
    billing_cycles: tuple[BillingCycle, ...] = Field(default_factory=tuple)
    minimum_payment_snapshots: tuple[MinimumPaymentSnapshot, ...] = Field(default_factory=tuple)
    sinking_funds: tuple[SinkingFundAllocation, ...] = Field(default_factory=tuple)
    income_sources: tuple[IncomeSource, ...] = Field(default_factory=tuple)
    obligations: tuple[ScheduledObligation, ...] = Field(default_factory=tuple)
    payments: tuple[Payment, ...] = Field(default_factory=tuple)
    transfers: tuple[Transfer, ...] = Field(default_factory=tuple)
    allocation_requests: tuple[AllocationRequest, ...] = Field(default_factory=tuple)
    transfer_timing_policies: tuple[TransferTimingPolicy, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _cross_validate(self) -> "FinancialSnapshot":
        # --- Liquidity accounts ---
        liquidity_ids = {a.account_id for a in self.liquidity_accounts}
        if len(liquidity_ids) != len(self.liquidity_accounts):
            raise ValueError("LiquidityAccount.account_id must be unique across the snapshot")
        if self.liquidity_accounts:
            primaries = [a for a in self.liquidity_accounts if a.is_primary]
            if len(primaries) != 1:
                raise ValueError(
                    f"exactly one LiquidityAccount must have is_primary=True (found {len(primaries)})"
                )

        # --- Debt accounts ---
        revolving_id_list = [a.account_id for a in self.revolving_accounts]
        if len(set(revolving_id_list)) != len(revolving_id_list):
            raise ValueError("RevolvingAccount.account_id must be unique across the snapshot")
        loan_id_list = [l.loan_id for l in self.installment_loans]
        if len(set(loan_id_list)) != len(loan_id_list):
            raise ValueError("InstallmentLoan.loan_id must be unique across the snapshot")
        revolving_ids = set(revolving_id_list)
        loan_ids = set(loan_id_list)
        if revolving_ids & loan_ids:
            raise ValueError(f"account_id/loan_id collision across debt types: {revolving_ids & loan_ids}")
        debt_ids = revolving_ids | loan_ids

        segment_owner_keys = {
            (acct.account_id, seg.segment_id)
            for acct in self.revolving_accounts for seg in acct.segments
        }

        # --- Floors ---
        floor_account_list = [f.account_id for f in self.liquidity_floors]
        if len(set(floor_account_list)) != len(floor_account_list):
            raise ValueError("at most one AccountLiquidityFloor is allowed per account_id")
        for floor in self.liquidity_floors:
            if floor.account_id not in liquidity_ids:
                raise ValueError(f"AccountLiquidityFloor references unknown account_id {floor.account_id!r}")

        # --- Sinking funds ---
        sf_id_list = [sf.allocation_id for sf in self.sinking_funds]
        if len(set(sf_id_list)) != len(sf_id_list):
            raise ValueError("SinkingFundAllocation.allocation_id must be unique")
        for sf in self.sinking_funds:
            if sf.account_id not in liquidity_ids:
                raise ValueError(f"SinkingFundAllocation references unknown account_id {sf.account_id!r}")
            if (sf.planned_contribution_amount > 0
                    and sf.planned_contribution_source_account_id not in liquidity_ids):
                raise ValueError(
                    f"SinkingFundAllocation planned_contribution_source_account_id "
                    f"{sf.planned_contribution_source_account_id!r} is unknown"
                )

        # --- Billing cycles ---
        cycle_id_list = [c.cycle_id for c in self.billing_cycles]
        if len(set(cycle_id_list)) != len(cycle_id_list):
            raise ValueError("BillingCycle.cycle_id must be unique")
        for c in self.billing_cycles:
            if c.account_id not in debt_ids:
                raise ValueError(f"BillingCycle references unknown debt account_id {c.account_id!r}")
        cycle_by_id = {c.cycle_id: c for c in self.billing_cycles}

        # --- Minimum payment snapshots: unconditional + exactly one per cycle ---
        min_snapshot_cycle_list = [s.billing_cycle_id for s in self.minimum_payment_snapshots]
        if len(set(min_snapshot_cycle_list)) != len(min_snapshot_cycle_list):
            raise ValueError(
                "at most one MinimumPaymentSnapshot is allowed per billing_cycle_id "
                "(two contradictory remaining-minimum figures for one cycle is invalid)"
            )
        for snap in self.minimum_payment_snapshots:
            cycle = cycle_by_id.get(snap.billing_cycle_id)
            if cycle is None:
                raise ValueError(
                    f"MinimumPaymentSnapshot references unknown billing_cycle_id {snap.billing_cycle_id!r}"
                )
            if cycle.account_id != snap.account_id:
                raise ValueError(
                    f"MinimumPaymentSnapshot.account_id {snap.account_id!r} does not match "
                    f"billing cycle {snap.billing_cycle_id!r}'s account_id {cycle.account_id!r}"
                )

        # --- Income / obligations: unconditional routing + unique IDs ---
        income_id_list = [i.source_id for i in self.income_sources]
        if len(set(income_id_list)) != len(income_id_list):
            raise ValueError("IncomeSource.source_id must be unique")
        for inc in self.income_sources:
            if inc.destination_account_id not in liquidity_ids:
                raise ValueError(
                    f"IncomeSource references unknown destination_account_id {inc.destination_account_id!r}"
                )
        obligation_id_list = [o.obligation_id for o in self.obligations]
        if len(set(obligation_id_list)) != len(obligation_id_list):
            raise ValueError("ScheduledObligation.obligation_id must be unique")
        for ob in self.obligations:
            if ob.source_account_id not in liquidity_ids:
                raise ValueError(f"ScheduledObligation references unknown source_account_id {ob.source_account_id!r}")

        # --- Payments ---
        payment_id_list = [p.payment_id for p in self.payments]
        if len(set(payment_id_list)) != len(payment_id_list):
            raise ValueError("Payment.payment_id must be unique")
        payment_by_id = {p.payment_id: p for p in self.payments}
        for pay in self.payments:
            if pay.account_id not in debt_ids:
                raise ValueError(f"Payment references unknown debt account_id {pay.account_id!r}")
            if pay.segment_id is not None and (pay.account_id, pay.segment_id) not in segment_owner_keys:
                raise ValueError(
                    f"Payment.segment_id {pay.segment_id!r} does not belong to account {pay.account_id!r}"
                )
            if pay.source_liquidity_account_id not in liquidity_ids:
                raise ValueError(
                    f"Payment references unknown source_liquidity_account_id "
                    f"{pay.source_liquidity_account_id!r}"
                )

        # --- Allocation requests: ownership + aggregate-per-payment limit ---
        req_id_list = [r.request_id for r in self.allocation_requests]
        if len(set(req_id_list)) != len(req_id_list):
            raise ValueError("AllocationRequest.request_id must be unique")
        allocation_rule_by_account = {
            r.allocation_rule.account_id: r.allocation_rule for r in self.revolving_accounts
        }
        for req in self.allocation_requests:
            rule = allocation_rule_by_account.get(req.account_id)
            if rule is None:
                raise ValueError(f"AllocationRequest references unknown account_id {req.account_id!r}")
            if not rule.consumer_override_supported.value:
                raise ValueError(
                    f"account {req.account_id!r} does not support consumer-directed allocation"
                )
            if (req.account_id, req.segment_id) not in segment_owner_keys:
                raise ValueError(
                    f"AllocationRequest.segment_id {req.segment_id!r} does not belong to "
                    f"account {req.account_id!r}"
                )
            payment = payment_by_id.get(req.payment_id)
            if payment is None:
                raise ValueError(f"AllocationRequest references unknown payment_id {req.payment_id!r}")
            if payment.account_id != req.account_id:
                raise ValueError(
                    f"AllocationRequest.account_id {req.account_id!r} does not match "
                    f"payment {req.payment_id!r}'s debt account {payment.account_id!r}"
                )
            if req.requested_amount > payment.amount:
                raise ValueError(
                    f"AllocationRequest.requested_amount {req.requested_amount} exceeds "
                    f"payment {req.payment_id!r}'s total amount {payment.amount}"
                )
        with localcontext(_DECIMAL_CTX):
            totals_by_payment: dict[str, Decimal] = {}
            for req in self.allocation_requests:
                totals_by_payment[req.payment_id] = (
                    totals_by_payment.get(req.payment_id, Decimal("0")) + req.requested_amount
                )
            for payment_id, total in totals_by_payment.items():
                payment = payment_by_id[payment_id]
                if total > payment.amount:
                    raise ValueError(
                        f"AllocationRequests for payment {payment_id!r} sum to {total}, "
                        f"exceeding its amount {payment.amount}"
                    )

        # --- Transfers ---
        transfer_id_list = [t.transfer_id for t in self.transfers]
        if len(set(transfer_id_list)) != len(transfer_id_list):
            raise ValueError("Transfer.transfer_id must be unique")
        for transfer in self.transfers:
            if transfer.source_account_id not in liquidity_ids:
                raise ValueError(f"Transfer references unknown source_account_id {transfer.source_account_id!r}")
            if transfer.dest_account_id not in liquidity_ids:
                raise ValueError(f"Transfer references unknown dest_account_id {transfer.dest_account_id!r}")

        # --- Timing policies: unconditional route check + unique routes ---
        route_list = [(p.source_account_id, p.dest_account_id) for p in self.transfer_timing_policies]
        if len(set(route_list)) != len(route_list):
            raise ValueError(
                "at most one TransferTimingPolicy is allowed per (source_account_id, "
                "dest_account_id) route"
            )
        for policy in self.transfer_timing_policies:
            if policy.source_account_id not in liquidity_ids:
                raise ValueError(
                    f"TransferTimingPolicy references unknown source_account_id {policy.source_account_id!r}"
                )
            if policy.dest_account_id not in liquidity_ids:
                raise ValueError(
                    f"TransferTimingPolicy references unknown dest_account_id {policy.dest_account_id!r}"
                )

        return self

    def unrestricted_cash(self, account_id: str) -> Decimal:
        """NOT authoritative. Requires an explicit AccountLiquidityFloor —
        no silent $0 fallback."""
        with localcontext(_DECIMAL_CTX):
            acct = next((a for a in self.liquidity_accounts if a.account_id == account_id), None)
            if acct is None:
                raise KeyError(f"no LiquidityAccount with account_id {account_id!r}")
            floor_row = next((f for f in self.liquidity_floors if f.account_id == account_id), None)
            if floor_row is None:
                raise KeyError(
                    f"no AccountLiquidityFloor defined for account_id {account_id!r} — "
                    f"supply one explicitly (even $0, with provenance)"
                )
            reserved = sum(
                (sf.reserved_amount for sf in self.sinking_funds if sf.account_id == account_id),
                Decimal("0"),
            )
            return (
                acct.cleared_balance + acct.pending_credits - acct.pending_debits
                - reserved - floor_row.minimum_balance
            )
