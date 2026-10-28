# Saved accounts to a saved payoff result

The account wizard now connects directly to the existing mixed payoff engine.
From an account setup, choose **Continue to income, bills and payoff**. Home resumes
the latest personal setup with **Continue my payoff plan**; practice setups cannot
displace that shortcut.

The review contains forecast settings, income/living costs/internal transfers,
and per-debt calculation terms. Each small form saves independently, keeps partial
answers, retains previous versions and rejects stale account/planning contexts.
Existing account answers and My Money/bill/paycheck records are not rewritten.

When required fields are filled, **Calculate my payoff preview** converts the saved
inputs into MixedPayoffInputs and calls the existing engine. The result compares
both strategies, shows dated payments and named funding accounts, and uses the
existing signed save flow. Saved results retain account display names and a link
back to their wizard. Exact inputs and both dated CSVs can be downloaded and replayed
through the headless tool. Later setup edits do not change saved result snapshots.

## What must be reviewed

The common balance date represents reconciled balances after that day's included
transactions. The forecast starts at local midnight the following day. Every active
debt and participating bank balance must match that date. Pending debits, holds and
transfers crossing the opening date must be reconciled first. An income or transfer
already included in opening balances is not replayed as new cash.

Only explicitly routed bank accounts participate: the primary account, debt payment
sources, and endpoints of included cash events. An unused savings account stays
outside the estimate; its money is not pooled, counted as income, or available for
payments. Its unknown balance is not converted into zero and does not block a plan
that does not use it. Adding an actual route makes its balance date, floor and
reserve reconciliation mandatory. Reserved funds remain with each physical account.

Credit limits, savings APY and autopay settings are not required to calculate.
Bank APY does not generate assumed income. Every debt needs a confirmed balance;
a known zero balance is excluded from payments while an unknown balance blocks
conversion. Up to 10 active debts, 20 participating cash accounts, 120 complete
payment rounds and 2000 dated cash events are supported.

Cards require ordinary purchase balances with lost grace and no promotional terms,
explicit previous/next statement dates, future monthly close/due rules, original and
unpaid minimums, the supported minimum floor/percentage formula, day count, rounding
and opening accrued interest. The formula is balance-capped maximum of the floor
and balance percentage plus billed finance charges. Future fees/rate changes and
new borrowing are not inferred. Promotions and unknown balance mechanics remain
blocked rather than silently flattened into ordinary-rate debt.

Loans require remaining principal, disclosed APR, contractual NOTE rate, simple
interest with principal curtailment, monthly installment day, explicit opening
accrual/fees, day count and rounding. Paid-ahead, precomputed and other loan contracts
remain unsupported. Extra principal does not cancel future installments. Loan-only
setups and zero-card-balance exclusions work through the same adapter.

Future monthly dates use the selected short-month rule. Payment and transfer delays
are calendar-day estimates with explicit clocks; there is no weekend/holiday guessing.
Ambiguous/nonexistent DST times fail. Partial payment rounds beyond the chosen end
are not generated. Future cash schedules extend through the existing cash horizon,
including its 90-day tail; pending transfers retain ledger holds/commitments/transit.

## Reuse known amounts without guessing their schedules

The personal review can copy existing expected paycheck, bill, food/fuel budget and
standing-transfer amounts for review. Frequency, account routing, availability time
and settlement delays are not inferred. Bill occurrences remain one-time unless the
user declares recurrence. Already-covered/excluded bills remain excluded; unverified
ones remain under review. Debt payments are not imported as living costs, avoiding
double counting the engine's minimums. The same imports do not duplicate by source
ID, overwrite later planning edits, mark bills paid or re-add an already received
paycheck. Practice setups cannot import personal financial records.

A warning remains visible if no recurring living costs are included. Completing a
set of input fields does not prove a household budget is complete. The user must
review forward costs and the stated assumptions before projection. No global optimum,
servicer payoff quote, bank sync, payment execution or rent funding is promised.

## Persistence and checks

Planning inputs live separately at
`local_scenarios/account_wizards/planning/<setup-id>.json`; prior versions are
retained under its history folder. The inventory summary still downloads accounts only. Plan review now also
downloads a complete setup backup containing the planning sidecar, with a signed
preview/restore flow that creates a separate copy. See SETUP_BACKUPS.md. A
calculated run's exact-input download contains the full calculation snapshot. Source checkpoints exclude all private
records, histories, generated personal runs and screenshots.

No engine module, SCHEMA.py or frozen specification changed. Conversion normalizes
percentages and expands declared calendars; authoritative financial calculations
remain in the existing engine. Contract fields supplied in forms use
USER_PROVIDED_ESTIMATE; inferred standard single-segment allocation and explicitly
supported simple-daily behavior retain ASSUMED_DEFAULT provenance. Future date
patterns and constant contract terms remain disclosed estimates.

Validation covers equivalent existing mixed examples with MATCHING account IDs,
separate-account transfer timing, zero/unknown distinction, loan-only cases, duplicate
imports, stale forms, signed save/reopen, unsupported mechanics and original-record
preservation. Account IDs break equal-rate ties; relabeling a card/loan tie can
legitimately change which debt is cleared first and its trailing-interest date.


Verified release: 819 passed in100.09s full suite; final3 smoke checks after wording.
Browser preview/save/reload and production JSON/CSV headless replay passed.

## Updating figures later

The plan review shows saved opening balances and their dates with direct edit
links. Its next-step button follows the first remaining required check. Unused
bank accounts stay in a separate disclosure. Dates matching the forecast start
are only a consistency check, not proof of live bank verification. Changing the
forecast date does not refresh balances or mark bills paid; each included balance
and future cash schedule still needs review. No source facts are changed on GET.

This screen update passed47 focused tests, including three new regressions.

Cash-event summaries now show their saved first date, frequency, stop date and
named account route. Missing dates and routes stay explicitly unknown. These are
schedule inputs, not claims that a transaction has occurred.

## Refresh and review the first round

**Update balances together** edits balances/dates and used bank protections in one
short form, with atomic validation/history and stale-context checks. Existing
contract and planning answers are preserved. See PLAN_REFRESH.md for what is
and is not updated. Conflicting input dates and delays now surface as linked
readiness checks before calculation. Results separate payment initiation from
credit dates and show the first supplied round for each strategy.

October26 validation:867 full-suite tests plus final11 balance smoke checks.
