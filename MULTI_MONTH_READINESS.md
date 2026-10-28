
## October 16: shared-cash future minimum coordinator

Added engine.portfolio_minimum_forecast with immutable CardMinimumSchedule and
PortfolioMinimumForecast models. One to 20 ordinary simple-daily cards, each with
explicit matching minimum terms and 1–24 explicit payment slots, share one physical
cash account. Supports the same <=366-day debt horizon and extended cash checks as
the one-card forecast. No extra payments, automatic dates, transfers, active grace,
promotions or multiple cash sources are inferred. Cross-card lifecycles must settle
before the next initiation. Simultaneous initiation requires explicit distinct
priorities. Slot IDs are globally unique and debt accounts cannot repeat.

Each chronological slot replays that card from original terms and prior accepted
credits, reads the current unpaid minimum, then clips against shared cash through
the full cash horizon. Final replay uses accepted credits only. This avoids the
older request coordinator's opening-balance ceiling, allowing later posted interest
to be repaid. Whole-window unhealthy cash conservatively blocks payments. Results
include desired/accepted/unmet amounts, per-card missed dues and cash ledger.
Cash/credit payment totals reconcile. Zero-minimum slots generate no positive request.

The original one-card forecast now shares its extracted validation helper; its
behavior and tests remain unchanged. Frozen SCHEMA/spec and every other pre-existing
engine module are byte-identical to the Dashboard Overview checkpoint.

13 new tests cover independent two-card arithmetic, limited shared cash and explicit
priority independent of tuple order, future paycheck timing, future bill/reserve
protection, one-card equivalence, low Decimal precision, invalid IDs/priorities/
overlapping lifecycles/terms, repayment beyond opening debt and zero-minimum slots.
This is backend-only; no UI or saved user scenarios changed. Next: a clearly labeled
synthetic multi-card forecast view, then explicit contract input integration. Do not
claim full payoff optimization or complete household coverage from this component.

# Multi-month forecasting readiness — October 11, 2026

This is an implementation assessment, not a newly approved calculation rule.
Frozen SPEC v2.4 remains authoritative, especially the current decision window and
separate rolling 90-day cash horizon. A long forecast must not imply a globally
optimal future schedule or an instruction to execute hypothetical payments.

## Existing foundation

- simulation.simulate_revolving replays supplied billing cycles, posts interest,
  tracks cycle minimums and reports missed due dates. projected_minimum uses explicit
  balance, floor, percentage, fees and finance charges under Decimal arithmetic.
- DebtCheckpoint/resume_revolving preserve debt replay state. Liquidity checkpoints
  exist separately. This is not yet an atomic portfolio restart.
- portfolio.coordinate_payments reserves supplied minimum requests before extras,
  checks the shared cash horizon and replays accepted amounts through debt accounts.
  Its explicit scope says it does not invent new minimum requests.
- The current manual UI intentionally stops before the next statement closes; its
  placeholder future minimum terms must not silently become authoritative forecasts.

## Next bounded engine implementation

First add independently checked fixtures spanning two statement closes using explicit
cycle dates, minimum formula inputs, rounding terms, income/bills and payment timing.
Verify interest posting and minimum creation against hand-calculated expected results.
Then introduce an explicit future-request policy, separate from actual payments,
that reads newly generated minimum state and coordinates requests against shared cash.
It must preserve already committed payments and not count future income before it clears.

Required acceptance cases: insufficient cash; different due dates; a statement close
and credit on the same day; a payoff leaving residual interest; two cards competing for
cash; a cycle outside the cash window; pause/resume without duplicate debit or interest;
and reconciliation of requested, accepted, credited and bank-debited amounts.

Do not expand the manual date limit until those contracts and tests exist. Keep future
forecast estimates distinct from the current-window actionable result. No automated
money movement is added. Actual import remains optional future integration.

## Inputs to collect later

For each card: current statement balance/date, unpaid minimum and due date, rate and
interest/day-count convention, statement schedule, minimum formula and rounding terms,
plus any promotional or grace rules. Also collect actual available cash, protected
reserves, upcoming income/bills and payment settlement timing. Unknown terms retain
explicit assumed provenance or stop the affected calculation; they are not guessed.

## October 14: three-statement fixtures and generated minimum-only forecast

Completed independent arithmetic fixtures, a read-only multi-statement example, and
engine.minimum_forecast for one ordinary card. Existing engine modules and frozen
schema/spec are unchanged; minimum_forecast.py is a new bounded engine component.

The fixture uses 1000 opening balance, .365 APR / 365 daily, no grace, 25 minimum floor
and .01 statement-balance fraction plus billed interest. Fixed 100 payments on each
20th yield postings 29.80,25.13,25.30; balances929.80,854.93,780.23 and new minimums
39.10,33.68,33.10. Tests give independent day-count arithmetic, close-day credit,
residual-interest payoff, shortage and exact serialized resume equality over closes.

forecast_minimums requires explicit matching floor/rate, supplied full cycles and
1–24 explicit aware payment slots. It supports one simple-daily standard-purchase
segment in LOST_GRACE, one cash account and ordinary income/expense plans. Slots
must be ordered on distinct creditor-local credit dates, with settlement before the
next initiation. Debt horizon <=366 days; settlement <=90 days after debt end.
Posted balance/minimum/floor must be whole cents. It rejects active grace/promos,
other cash event types and term mismatches. Existing contract provenance is retained.

At each credit event, use current unpaid minimum capped by posted debt; project cash
from the explicit initiation through the full cash horizon with prior accepted
payments, then clip to cents while preserving floors/reserves/future supplied bills.
Future income does not fund earlier initiation. Desired/accepted/unmet requests and
missed dues remain visible. Credited total reconciles to accepted amounts; bank cash
uses the existing lifecycle model. Requests may exceed the original opening balance
across months because later posted interest is real projected debt capacity.

This is a hypothetical minimum-only forecast, not a multi-card coordinator, optimizer,
actual ledger or automatic payment-date scheduler. No extra-payment policy, purchase
stream, combined portfolio checkpoint or personal-form integration was added. Unknown
future other-card minimums are not reserved; do not use this component to imply a
complete household payment plan. Do not pass its generated schedule blindly through
the older portfolio coordinator's opening-balance cap.

Read-only /multimonth-example, linked from home, shows fixed payments and a separate
minimum-only forecast (25,40.76,37.72 paid; ending debt985.33; cash296.52). Different
budgets are explicitly identified. April minimum is displayed while debt ends March31;
separate cash horizon is June18. No user scenario files written.

Verification: full suite527 passed in42.47s, then13 minimum-forecast tests passed
including4 added rejection cases (531 total cases across final test files). Browser
DOM and full-page layout checked. Previous tests remain unchanged except new modules.
Next: expand explicit contract-input UI and independently checked multi-card future
minimum coordination. Preserve forecast/current-action separation and do not promise
full payoff optimization from this slice. No automation or reset used.
