# SPEC.md: Core Mathematical Standards & Formulation Engine (v2.4)

---

## 1. System Architecture Principles

1. **Hierarchy of Truth:** Actual lender statements, contractual Truth in Lending disclosures, and cleared/reconciled bank ledger entries are the authoritative financial records. Engine calculations are forward projections and simulations designed to reconcile against those records as new statement cycles close.
2. **Independent Ledger Ownership:** Debt Shredder owns its internal financial ledger, liquidity model, and debt state. It does not depend on Actual Budget or any external budgeting tool for execution. External platforms serve solely as optional, downstream, read-only import/sync adapters.
3. **Deterministic Computation:** All financial state transitions, amortizations, cash-flow projections, and allocation optimizations are strictly deterministic and auditable. Heuristic guessing, unconstrained nonlinear solvers, and LLM-generated arithmetic are strictly forbidden within the computation loop.
4. **Point-in-Time Rolling Execution (Decoupled Horizons):** Rather than attempting to solve a globally optimal multi-month schedule upfront, the engine generates an authoritative, safe action for the **current decision window** using a deterministic forward simulation. The operational cash-flow window is evaluated across a rolling 90-day horizon, while debt constraints, promotional deadlines, and deferred-interest cliff dates are evaluated across their own distinct, full-length contract horizons (which may extend well beyond 90 days).
5. **Parameter Provenance:** Every contractual parameter, interest rate, calculation rule, and balance value must maintain an explicit provenance tag to prevent unverified defaults from masquerading as verified terms.

---

## 2. Arithmetic, Precision, and Ledger Rounding Conventions

### 2.1 Numerical Representation & Context Precision

* **Type System:** All monetary balances, periodic rates, percentages, ratios, and ledger tallies MUST use arbitrary-precision fixed-point decimal arithmetic (`decimal.Decimal` in Python). IEEE 754 floating-point primitives (`float`) are strictly forbidden.
* **Context Precision:** All calculations execute within an explicit `decimal.Context` having a precision of **at least 28 significant digits** (`prec=28`).
* **No Forced Intermediate Quantization:** Intermediate daily compounding, interest accrual accumulators, amortization schedules, and rate derivations MUST NOT be quantized, truncated, or rounded at intermediate steps. They retain full 28-digit context precision until a discrete contractual event occurs.
* **Periodic Rate Derivation:** Periodic rates are derived without pre-rounding:

$$DPR = \frac{\text{Nominal Rate}}{\text{BasisDays}}$$



### 2.2 Event-Driven Rounding Modes

Quantization to standard currency subunits ($0.01) occurs **only upon discrete contractual ledger events** (e.g., statement closing, payment posting, fee assessment, or promissory note accrual capitalization). Daily accrued interest is maintained in an unquantized, full-precision intermediate accumulator.

Supported rounding modes (configured per account / servicer contract):

* `ROUND_HALF_UP` (Standard US commercial rounding: halves round away from zero).
* `ROUND_HALF_EVEN` (Banker's rounding: halves round to nearest even integer).
* `ROUND_TRUNCATE` (Truncation toward zero; maps to `ROUND_DOWN` in Python Decimal).
* `ROUND_FLOOR` (Rounding toward negative infinity).
* `ROUND_CEILING` (Rounding toward positive infinity).

---

## 3. Account Topologies & Balance Segmentation

Credit accounts must not be modeled as single scalar balances. A revolving account consists of one or more **Balance Segments** governed by distinct terms.

### 3.1 Parameter Provenance

Every account and balance segment tracks the source of its parameters via the `ParameterProvenance` enumeration:

* `CONTRACT`: Sourced directly from original signed promissory notes, Truth in Lending disclosures, or formal cardholder agreements.
* `STATEMENT`: Extracted directly from a verified monthly periodic statement.
* `USER_CONFIRMED`: Explicitly validated and entered by the user.
* `ASSUMED_DEFAULT`: System-estimated fallback value. Must be explicitly flagged in all downstream UI and projection reports.

### 3.2 Balance Segment Data Model

Each balance segment $S_k$ tracks:

* `segment_id`: Unique identifier within the account.
* `segment_type`:
* `STANDARD_PURCHASE`
* `PROMOTIONAL_TRUE_ZERO` (0.00% APR through expiration timestamp $T_{\text{promo}}$)
* `PROMOTIONAL_DEFERRED_INTEREST` (0.00% billed APR; retroactively assessed if unpaid at $T_{\text{promo}}$)
* `BALANCE_TRANSFER` (Specific promotional APR, duration, and transaction fee basis)
* `CASH_ADVANCE` (Immediate interest accrual, no grace period)
* `FEES_AND_PENALTIES`


* `principal_balance`: Current outstanding principal ($B_k$).
* `current_apr`: Nominal annual percentage rate applicable during the current cycle.
* `post_promo_apr`: Reversion APR applied automatically if a balance remains post-$T_{\text{promo}}$.
* `post_promo_compounding_method`: Compounding method applied upon expiration.
* `deferred_interest_apr`: Specific contractual APR applied retroactively to deferred-interest balances. Maintained independently from `post_promo_apr`.
* `deferred_interest_calculation_method`: Specific contractual method used to calculate retroactive liability (e.g., `AVERAGE_DAILY_BALANCE_SIMPLE`, `DAILY_COMPOUNDING`, `RETROACTIVE_PURCHASE_SUM`). Retroactive compounding is never universally assumed.
* `compounding_method`: `SIMPLE_DAILY`, `DAILY_COMPOUNDING`, or `MONTHLY_COMPOUNDING`.
* `day_count_convention`: `ACTUAL_365_FIXED`, `ACTUAL_366`, `ACTUAL_ACTUAL`, or `THIRTY_360_US`.
* `accrued_unposted_interest`: Cumulative interest accrued in the active billing cycle (full precision).
* `deferred_interest_to_date`: Historical cumulative unbilled interest liability tracking according to the segment's `deferred_interest_calculation_method`.
* `is_disqualified`: Boolean flag set to `True` if a missed payment or contractual trigger has terminated promotional terms.
* `disqualification_events`: Chronological list of recorded disqualification timestamps.
* `parameter_provenance`: Map of field names to `ParameterProvenance` tags.

### 3.3 Credit Card Grace Period State Machine & Conditional Forecasting

Revolving accounts maintain an explicit grace period state machine. Cash advances and balance transfers are tagged with `grace_eligible = False` and begin accruing daily interest from posting date regardless of account-level grace.

#### State Definitions

* `FULL_GRACE`: Prior billed statement balance was paid in full by its due date. New purchase segments accrue $\$0.00$ interest through the grace period.
* `LOST_GRACE`: Prior billed statement balance was not satisfied in full. Purchases accrue interest immediately from posting date. Trailing/residual interest applies across billing cycles.
* `PENDING_STATEMENT`: Active cycle between statement close and payment due date.

#### Conditional Forecast Model (Non-Branching Core)

Rather than executing a generalized multi-universe branching engine, grace-period uncertainty is modeled strictly as a **dual-state evaluation** for the current billing cycle:

1. **Primary Track ($E_{\text{satisfied}}$):** Projects balances assuming the current statement minimum/full balance is paid on or before the due date.
2. **Contingent Liability ($E_{\text{breach}}$):** Computes the projected contingent finance-charge delta:

$$\Delta I_{\text{grace\_loss}} = \sum_{t \in \text{Cycle}} B_{\text{purchases}}(t) \times DPR$$


* If parameter provenance for grace-period compounding and balance calculation rules evaluates to `CONTRACT` or `STATEMENT`, this metric is reported as a verified projected contingent finance-charge delta.
* If any underlying rule relies on `ASSUMED_DEFAULT`, this charge must be explicitly labeled in the projection engine and UI as an **estimate**.



---

## 4. Installment Loans & Contractual Servicing Rules

Installment loans (personal loans, auto loans, fixed mortgages) do not follow revolving credit CARD Act rules. They must be modeled using distinct contractual debt mechanics.

### 4.1 Contractual Interest Rate vs. Disclosed APR

* **Contractual (Note) Rate:** The actual annual interest rate applied to outstanding principal to calculate periodic finance charges.
* **Disclosed APR (Truth in Lending):** The composite annualized cost reflecting prepaid finance charges, origination fees, and capitalized processing fees.
* **Calculation Standard:** The engine amortization calculations MUST execute exclusively against the **Contractual Note Rate**, never the disclosed APR, to prevent synthetic balance distortions. Disclosed APR is retained solely as an informational reference.

### 4.2 Loan Calculation Typologies

* **Simple-Interest Installment Loans:**
* Interest accrues daily on the outstanding unpaid principal balance:

$$I_t = B_t \times \frac{\text{Contractual Note Rate}}{\text{BasisDays}}$$


* Exact interest depends on the precise calendar day payments clear.


* **Precomputed-Interest Installment Loans:**
* Total finance charges over the loan life are precalculated at origination and added to the principal to form the total note balance.
* Early payoff or principal curtailments are governed by contractual rebate schedules (e.g., Actuarial Method or Rule of 78s where legally permissible).



### 4.3 Payment Application Hierarchy (Accrued Interest First)

Unless governed by an explicit statutory or contractual exception, loan servicers allocate incoming payments using the standard order of operations:

1. **Billed Fees & Late Charges:** Outstanding administrative assessments.
2. **Accrued Unpaid Interest:** Daily interest accrued from the last payment posting date through the current posting date ($t_{\text{credit}}$).
3. **Principal Curtailment:** The remaining portion of the payment reduces outstanding principal.

### 4.4 Prepayment & Pre-Payment Servicing Rules

When an installment payment exceeds the scheduled contractual monthly installment ($P_{\text{applied}} > P_{\text{contract}}$), the excess is categorized according to the loan's contractual servicer rule:

* `PRINCIPAL_ONLY_CURTAILMENT`: The excess dollar amount directly reduces the unpaid principal balance. The scheduled monthly due date does not change. Future interest charges decrease due to the lower principal balance.
* `PAID_AHEAD` (Due-Date Advancement): The excess payment satisfies future installment obligations, advancing the next contractual payment due date (e.g., 30, 60, or 90 days ahead). **Accrual Behavior:** Interest continues to accrue daily on the remaining principal balance; advancing the due date does not freeze daily interest accrual.
* `PRECOMPUTED_REBATE_REDUCTION`: Contractual rebate calculation applied against precomputed interest obligations upon early curtailment.

---

## 5. Payment Allocation & Minimum Payment Modeling

### 5.1 Billing Cycle and Minimum Payment Entity

Minimum payments are bound to discrete `BillingCycle` entities to prevent cycle-straddling errors:

* `cycle_id`: Unique identifier.
* `start_date` / `end_date`: Statement open and close dates.
* `due_date`: Contractual payment due date.
* `statement_minimum_original`: Authoritative dollar minimum printed on the statement.
* `statement_minimum_remaining`: Outstanding minimum required to avoid late fees and delinquency. Satisfied sequentially by incoming payments.

#### Cap Rule on Minimums

The effective remaining minimum payment is strictly capped by the current aggregate balance:


$$\text{EffectiveMinimumRemaining} = \min(M_{\text{billed\_remaining}}, \; \sum B_k)$$

#### Projected Future Minimum Formula

For unbilled cycles in the forward simulation:


$$M_{\text{proj}} = \min\left(\sum B_k, \; \max\left(M_{\text{floor}}, \; \text{Fees} + I_{\text{billed}} + (\alpha \times \sum B_k)\right)\right)$$


*Parameters $M_{\text{floor}}$ and $\alpha$ are configurable per issuer with documented provenance.*

### 5.2 Segment Payment Allocation Hierarchy

Payments applied to revolving credit accounts clear balances in accordance with regulatory mandates (Regulation Z §1026.53) and contract rules:

1. **Required Minimum Periodic Payment Allocation:** The required minimum periodic payment established under the account terms ($M_{\text{billed}}$) is applied across balance segments according to issuer terms (default: lowest APR first, or fees/finance charges first).
2. **Excess Payment Allocation (Regulation Z §1026.53 Rule):** Any payment amount exceeding the required minimum periodic payment must be allocated to the balance segment with the **highest APR** first, cascading downward.
3. **Expiring Promo Window Override (Mandatory Regulatory Rule):** During the final **two (2) complete billing cycles** prior to $T_{\text{promo}}$, excess payments apply first to the expiring promotional/deferred-interest segment.
4. **Consumer-Directed Overrides:** Configurable boolean flag `supports_consumer_allocation_overrides`. If supported by the issuer, allows manual assignment of excess funds to a targeted segment.

---

## 6. Resolution of Promotional & Deferred-Interest Schedules

### 6.1 Decoupled Decision Horizons

The operational cash-flow window operates across a rolling 90-day simulation. However, promotional deadlines ($T_{\text{promo}}$) and deferred-interest cliffs frequently extend beyond 90 days (e.g., 6, 12, or 18 months).

* **Constraint Tracking:** All active promotional and deferred-interest accounts maintain active constraints across their entire remaining lifespan ($T_{\text{promo}} - t_0$).
* **Payment-Date-Driven Amortization Target:** The engine determines the required target amortization rate across all available paydays prior to $(T_{\text{promo}} - \text{BufferDays})$, ensuring long-range deadlines enforce appropriate short-term cash allocations.

### 6.2 Target Payment Resolution: Forward Simulation with Bounded Search

To eliminate circular dependencies between segment allocation rules, future balances, and required payments, the engine uses **deterministic forward simulation with bounded search**.

#### Search Space & Bound Definitions

The search variable is maintained as a single scalar target parameter $P_{\text{cand}}$ (denominated in dollars). Because event-level liquidity limits can vary across different calendar dates, the actual account-level payment simulated on any specific event $p_i \in \{p_1, p_2, \dots, p_n\}$ is derived deterministically as:


$$\text{Payment}(p_i) = \min\left(P_{\text{cand}}, \; \text{MaxFeasiblePayment}(p_i)\right)$$

Where $\text{MaxFeasiblePayment}(p_i)$ is the maximum safe dollar amount that operational cash flow can direct to that credit account on event $p_i$ without triggering a liquidity constraint violation. The payment-allocation simulator then evaluates the account-level payment $\text{Payment}(p_i)$ and calculates the exact portion reaching the target promotional segment.

* **Lower Bound ($P_{\text{low}}$):** $\$0.00$.
* **Upper Bound ($P_{\text{high}}$):** The maximum liquidity-feasible limit across the schedule:

$$P_{\text{high}} = \max_{i} \left( \text{MaxFeasiblePayment}(p_i) \right)$$



#### Monotonicity Requirement & Deterministic Fallbacks

* **Monotonicity Condition:** Standard bisection search requires that increasing $P_{\text{cand}}$ monotonically decreases the remaining target segment balance at $T_{\text{promo}}$.
* **Non-Monotonic Contractual Edge Cases:** Non-monotonicity can occur if an issuer's allocation rules shift dynamically based on tiered payment thresholds, or if a fee triggers at a specific intermediate balance.
* **Algorithm:**
1. Test monotonicity over the interval $[P_{\text{low}}, P_{\text{high}}]$.
2. **Standard Path (Monotonic):** Execute binary search over scalar $P_{\text{cand}}$ evaluating each scheduled payment via $\min(P_{\text{cand}}, \text{MaxFeasiblePayment}(p_i))$ until $B_{\text{promo}}(T_{\text{promo}}) \le \$0.00$, terminating when the interval width $\vert{}P_{\text{high}} - P_{\text{low}}\vert{} \le \$0.01$.
3. **Deterministic Fallback (Non-Monotonic):** If monotonicity is violated, fallback to an adaptive bounded grid search over $P_{\text{cand}}$ with step size $\Delta = \$1.00$, followed by local linear interpolation to isolate the minimum payment that achieves $B_{\text{promo}}(T_{\text{promo}}) = \$0.00$.



If available cash-flow surplus cannot satisfy the required $P_{\text{cand}}$, the target payment is capped at maximum available surplus and the engine flags an explicit **Shortfall Alert** with projected liability:


$$\text{Exposure}_{\text{deferred}} = \text{deferred\_interest\_to\_date} + \text{ProjectedAccrual}(T_{\text{promo}})$$

---

## 7. Liquidity Architecture & Cash-Flow Safety Engine

### 7.1 Multi-Account Topology

The liquidity subsystem tracks liquid capital across distinct accounts without conflating balances:

* `LiquidityAccount`:
* `account_id`: Unique identifier (e.g., Primary Checking, High-Yield Savings).
* `account_type`: `CHECKING`, `SAVINGS`, `MONEY_MARKET`.
* `cleared_balance`: Settled funds verified by bank reconciliation.
* `is_primary_operational`: Boolean (designates the account from which debt payments execute).
* `transfer_eligible_to_operational`: Boolean (designates whether funds in this account can legally and operationally be transferred to the operational checking account to satisfy obligations or debt payments).



### 7.2 Internal Transfers vs. Inflows/Outflows

* `Transfer`: Represents funds movement between two internal `LiquidityAccount` entities.
* **Conservation of Capital Rule:** Internal transfers mutate individual account balances but have a net zero ($\$0.00$) impact on aggregate liquid cash.
* Transfers are explicitly barred from being processed as external income or expense events.

### 7.3 Sinking Fund Allocations: Physical Location & Reserved Balances

Sinking funds model cash restrictions tied directly to the physical account where the capital is stored:

* `SinkingFundAllocation`:
* `fund_id`: Unique identifier.
* `account_id`: The underlying physical account holding the funds.
* `reserved_balance`: **Hard-locked funds**. Capital already accumulated and legally/operationally restricted for a specific future purpose (e.g., $\$1,200$ for auto insurance renewal).
* `target_date`: Expiration or bill-due date.
* `planned_contribution`: Scheduled future periodic transfer into the fund.


* **Physical Account Partitioning:** Reserved sinking fund balances reduce unrestricted liquidity **only within the physical account where the reserved funds reside**. Sinking fund reserves stored in a savings account do not reduce the cleared balance of the operational checking account.
* **Strict Capital Wall Rule:** If cash flow enters a constrained state, **planned future contributions may be throttled or paused**, but **existing reserved balances are immutable** and cannot be appropriated for debt acceleration.

### 7.4 The 4-Stage Transaction Lifecycle (Float & Uncleared Outflows)

To prevent premature assumptions of cash availability or interest reduction, every transaction $X$ transitions through four discrete timestamps:

$$\begin{array}{rcc} \text{Initiation} & (t_{\text{init}}): & \text{Outflow committed/earmarked; deducted immediately from safe surplus} \\ \text{Creditor Credit} & (t_{\text{credit}}): & \text{Debt balance reduced for interest accrual calculation} \\ \text{Bank Debit} & (t_{\text{debit}}): & \text{Checking cleared balance updated} \\ \text{Final Settlement} & (t_{\text{settle}}): & \text{ACH hold window clears; transaction finalized} \end{array}$$

### 7.5 Multi-Account Safe Surplus Derivation

Surplus is derived exclusively from a forward simulation across the rolling 90-day window, accounting for uncleared float, account-specific reserve deductions, and verified transfer eligibility.

#### Committed Uncleared Outflows

For any account $A$, committed uncleared debits are defined as:


$$\text{UnclearedOutflows}_A(t) = \sum_{X \in \text{Debits}(A)} X_{\text{amount}} \quad \forall X \text{ where } t_{\text{init}} \le t < t_{\text{debit}}$$

When a transaction reaches $t_{\text{debit}}$, it decreases $C_{\text{cleared}, A}$ and drops out of $\text{UnclearedOutflows}_A(t)$ simultaneously, completely preventing double counting.

#### Per-Account Unrestricted Liquidity

For each account $A$ on day $d \in [t, \; t + 90]$, the projected unrestricted liquidity $L_A(d)$ is computed strictly within its own boundary:


$$L_A(d) = C_{\text{cleared}, A}(t) - \text{UnclearedOutflows}_A(t) + \sum_{\tau=t}^{d} \text{ScheduledInflows}_A(\tau) - \sum_{\tau=t}^{d} \text{ScheduledOutflows}_A(\tau) - \sum_{k \in \text{Funds}(A)} \text{ReservedBalance}_k(d)$$

*(Where scheduled flows include only future events with $t_{\text{init}} > t$).*

#### Operational Safe Surplus

Let account $O$ be the primary operational account (`is_primary_operational = True`). The available transfer-eligible surplus from secondary liquidity accounts on day $d$ is:


$$T_{\text{avail}}(d) = \sum_{A \neq O, \, \text{transfer\_eligible}_A = \text{True}} \max\left(0, \; L_A(d) - \text{Floor}_{A, \text{min}}\right)$$

The projected net available cash accessible to the operational account on day $d$ is:


$$C_{\text{avail}}(d) = \left( L_O(d) - \text{Floor}_{O, \text{min}} \right) + T_{\text{avail}}(d)$$

The **Maximum Safe Immediate Acceleration Payment** on day $t$ is:


$$\text{SafeSurplus}_t = \max\left(0, \; \min_{d \in [t, \, t + 90]} C_{\text{avail}}(d)\right)$$

*If $\text{SafeSurplus}_t = 0$, extra principal payments are strictly prohibited.*

---

## 8. Insolvency & Constraint-Failure Protocol

### 8.1 Status Classifications

On every calculation cycle, the engine outputs an explicit `CashFlowStatus`:

* `HEALTHY`: All obligations met, sinking funds intact, checking projected to remain $\ge \text{Floor}_{\text{min}}$ across all 90 days.
* `BUFFER_BREACH`: All obligations met, but projected checking balance drops below $\text{Floor}_{\text{min}}$ on at least one day.
* `OBLIGATION_SHORTFALL`: Projected cash is insufficient to meet mandatory living expenses or statement minimum payments without intervention.
* `NEGATIVE_CASH`: Projected checking balance drops below $\$0.00$ (overdraft breach).

### 8.2 Automated Triage Hierarchy

If the simulation detects any status other than `HEALTHY`:

1. **Immediate Acceleration Halt:** All voluntary principal acceleration payments drop to $\$0.00$.
2. **Planned Contribution Pause:** The engine computes the deficit recovery achieved by temporarily setting `planned_contribution = 0` on non-critical sinking funds.
3. **Breach Forensics:** The engine outputs the exact breach date $d_{\text{breach}}$, the peak shortfall magnitude in dollars, and the specific bill or payment that triggers the failure.
4. **Promo Vulnerability Scan:** The engine scans all active promotional deadlines ($T_{\text{promo}}$) across their full contract horizon, outputting the projected retroactive interest exposure incurred if liquidity constraints force a default on required promotional schedules:

$$\text{Exposure}_{\text{deferred}} = \text{deferred\_interest\_to\_date} + \text{ProjectedAccrual}(T_{\text{promo}})$$


* If parameter provenance for the deferred interest calculation rules evaluates to `CONTRACT` or `STATEMENT`, this exposure is reported as a **verified projection**.
* If any underlying parameter relies on `ASSUMED_DEFAULT`, the exposure must be explicitly labeled as an **estimate**.



---

## 9. Issuer-Specific Contractual Rules (Configurable Registry)

The following parameters must never be hardcoded into the calculation core; they must be supplied via an external account configuration schema accompanied by an explicit `ParameterProvenance` tag:

| Parameter Key | Permissible Range / Options | Typical Default | Provenance Requirement |
| --- | --- | --- | --- |
| `day_count_basis` | `ACTUAL_365_FIXED`, `ACTUAL_366`, `30_360_US` | `ACTUAL_365_FIXED` | Contract / Statement |
| `rounding_mode` | `ROUND_HALF_UP`, `ROUND_HALF_EVEN`, `ROUND_TRUNCATE`, `ROUND_FLOOR`, `ROUND_CEILING` | `ROUND_HALF_UP` | Contract / Verified Servicer |
| `grace_restoration_cycles` | 1 or 2 consecutive full-balance statement cycles | 2 billing cycles | Contract / Issuer Disclosure |
| `minimum_payment_floor` | Absolute dollar floor ($M_{\text{floor}}$) | $25.00 to $35.00 | Statement / Contract |
| `minimum_payment_percentage` | Balance percentage ($\alpha$) | 1.0% to 2.0% | Statement / Contract |
| `supports_directed_allocation` | `True` / `False` | `False` | Contract / User Verified |
| `prepayment_servicing_rule` | `PRINCIPAL_ONLY_CURTAILMENT`, `PAID_AHEAD`, `PRECOMPUTED_REBATE_REDUCTION` | `PRINCIPAL_ONLY_CURTAILMENT` | Promissory Note / Contract |
| `deferred_interest_calc_rule` | `AVERAGE_DAILY_BALANCE_SIMPLE`, `DAILY_COMPOUNDING`, `RETROACTIVE_PURCHASE_SUM` | `AVERAGE_DAILY_BALANCE_SIMPLE` | Contract Disclosure |

---

### Architectural Review Status

Section 1 (v2.4) is complete with only the three required corrections applied:

* Scalar bisection search preserved with dynamic event-level payment clipping $\min(P_{\text{cand}}, \text{MaxFeasiblePayment}(p_i))$.
* Physical-account-isolated sinking fund deductions with explicit transfer-eligible aggregation.
* Projected retroactive interest exposure explicitly labeled as a verified projection or estimate based on parameter provenance.

---

## Freeze Record

**Section 1 frozen:** September 23, 2026  
**Frozen version:** v2.4

This section has completed mathematical, architectural, and implementation-feasibility review by Gemini, ChatGPT, and Claude.

Future changes to Section 1 require an explicit specification revision and review before implementation.
