"""Grace-state resolution from explicitly reconciled statement payment history.

This reducer does not infer statement satisfaction from current principal or a
minimum payment. Credits must already be assigned to exactly one statement.
It changes eligibility only; it never erases or posts accrued interest.
"""
from datetime import date, timedelta
from pydantic import Field, model_validator
from SCHEMA import StrictModel, BillingCycle, GracePeriodState, Sourced, ProvenanceSource
from engine.common import Nonnegative, ZERO, CENT, decimal_context, projection_label, MissingTerms


class StatementCredit(StrictModel):
    credit_id: str = Field(min_length=1)
    credited_on: date
    amount: Nonnegative
    provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT


class GraceStatement(StrictModel):
    cycle: BillingCycle
    original_statement_balance: Nonnegative
    balance_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
    credits: tuple[StatementCredit, ...] = ()

    @model_validator(mode='after')
    def reconciled(self):
        if len({c.credit_id for c in self.credits}) != len(self.credits):
            raise ValueError('duplicate statement credit')
        if any(c.credited_on < self.cycle.statement_date for c in self.credits):
            raise ValueError('credit predates statement; reconcile the original balance instead')
        if any(x % CENT for x in (self.original_statement_balance, *(c.amount for c in self.credits))):
            raise ValueError('posted statement amounts must be whole cents')
        return self


class GraceDecision(StrictModel):
    cycle_id: str
    due_date: date
    credited_by_due: Nonnegative
    remaining_at_due: Nonnegative
    paid_in_full: bool
    resulting_state: GracePeriodState
    consecutive_full_statements: int


class GraceResolution(StrictModel):
    state: GracePeriodState
    last_resolved_state: GracePeriodState
    consecutive_full_statements: int
    decisions: tuple[GraceDecision, ...]
    pending_cycle_ids: tuple[str, ...]
    label: str


@decimal_context
def resolve_grace(account_id: str, opening_state: GracePeriodState,
                  restoration_required: Sourced[int], statements: tuple[GraceStatement, ...],
                  as_of: date, *, opening_consecutive_full: int = 0,
                  opening_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT) -> GraceResolution:
    """Resolve due dates through end-of-day as_of; due-date credits count.

    Opening state is the last resolved state immediately before this history.
    A pending opening alone cannot identify a lost-grace restoration streak.
    Input history must be complete and contiguous; completeness before its first
    cycle is the caller's reconciliation responsibility. Future statements are
    rejected; future-dated credits are ignored until their credited date.
    """
    opening_state = GracePeriodState(opening_state)
    if opening_state == GracePeriodState.PENDING:
        raise MissingTerms('supply the last resolved grace state before pending statements')
    required = restoration_required.value
    if isinstance(required, bool) or required not in (1, 2):
        raise ValueError('restoration requires one or two full statement cycles')
    if isinstance(opening_consecutive_full, bool) or not isinstance(opening_consecutive_full, int) or not 0 <= opening_consecutive_full <= required:
        raise ValueError('invalid opening full-statement streak')
    if opening_state == GracePeriodState.LOST_GRACE and opening_consecutive_full >= required:
        raise ValueError('lost grace contradicts completed restoration streak')
    cycles = [s.cycle for s in statements]
    if any(c.account_id != account_id for c in cycles):
        raise ValueError('statement account mismatch')
    if len({c.cycle_id for c in cycles}) != len(cycles):
        raise ValueError('duplicate statement cycle')
    if any(c.statement_date > as_of for c in cycles):
        raise ValueError('statement has not closed as of requested date')
    if any(b.start_date != a.end_date + timedelta(days=1) or b.due_date <= a.due_date
           for a, b in zip(cycles, cycles[1:])):
        raise MissingTerms('statement history must be ordered, contiguous, with increasing due dates')
    ids = [c.credit_id for s in statements for c in s.credits]
    if len(ids) != len(set(ids)):
        raise ValueError('credit reused across statements; reconcile explicit unique allocations first')
    state = opening_state
    streak = opening_consecutive_full
    decisions = []
    pending = []
    sources = [opening_provenance, restoration_required.provenance]
    for statement in statements:
        cycle = statement.cycle
        sources.append(statement.balance_provenance)
        if cycle.due_date > as_of:
            pending.append(cycle.cycle_id)
            continue
        eligible = [c for c in statement.credits if c.credited_on <= cycle.due_date]
        sources.extend(c.provenance for c in eligible)
        credited = sum((c.amount for c in eligible), ZERO)
        remaining = max(ZERO, statement.original_statement_balance - credited)
        full = remaining == ZERO
        if full:
            streak = min(required, streak + 1)
            if state == GracePeriodState.FULL_GRACE or streak >= required:
                state = GracePeriodState.FULL_GRACE
        else:
            streak = 0
            state = GracePeriodState.LOST_GRACE
        decisions.append(GraceDecision(cycle_id=cycle.cycle_id, due_date=cycle.due_date,
            credited_by_due=credited, remaining_at_due=remaining, paid_in_full=full,
            resulting_state=state, consecutive_full_statements=streak))
    return GraceResolution(state=GracePeriodState.PENDING if pending else state,
        last_resolved_state=state, consecutive_full_statements=streak,
        decisions=tuple(decisions), pending_cycle_ids=tuple(pending), label=projection_label(tuple(sources)))


class OpeningGraceAccrual(StrictModel):
    """Unposted contingent purchase charge through the day before replay starts.

    Reconciled history, including any earlier billed-period exposure, belongs in
    this amount. Zero is explicit; it is never inferred from current principal.
    """
    segment_id: str
    through: date
    amount: Nonnegative
    provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT


class GraceReplayTerms(StrictModel):
    statement: GraceStatement
    last_resolved_state: GracePeriodState
    consecutive_full_statements: int = Field(default=0, ge=0, le=2)
    opening_contingent: tuple[OpeningGraceAccrual, ...]
    opening_provenance: ProvenanceSource = ProvenanceSource.ASSUMED_DEFAULT
