# Weekly system check

Open `/weekly-check` or **Open weekly system check** on home when a private
planning reference has been prepared. This is the first decision-support screen:
a read-only comparison of reported weekly allocations against historical net-pay
scenarios. It is not a dated liquidity forecast, bank-balance refresh, payoff
calculation or a safe-extra recommendation.

## What can be compared

Try a flexible savings contribution, optional housing savings and bill-account
funding. GET parameters `pool`, `rent` and `bills` change only the displayed mix.
`back` models a one-time transfer to checking; `spend` models direct spending from
the fund. Their sum cannot exceed its current reported balance. `weeks` changes
the assumed remaining contribution count (1–520). Optional `pay` adds an alternative
net-pay scenario; it does not record received income or change pay history.
Reported values and historical pay cases remain unchanged. No bank transfer,
payroll instruction, saved budget, account inventory or result is edited.

The table shows unassigned weekly pay after the listed allocations. A negative
number identifies an allocation gap; it is not a predicted overdraft. A positive
number is before unlisted spending, cash cushions, pending items and transaction
timing. Historical pay is not a guaranteed future minimum.

A goal-only weekly rate is the remaining target divided by assumed contribution
opportunities, rounded UP to cents. Its balance stays assigned to the goal rather
than being spent on other bills. The projection assumes the entire reported fund
balance is eligible, every contribution arrives, and no withdrawals beyond the entered trials occur. Earlier
spending, a closer deadline or other trips/activities changes the required rate.
The count does not establish an exact dated payment calendar.

Bill-account funding is annualized over52 weekly deposits for a separate budget
comparison. This never proves funds will be present before a draft. Loan and bill
withdrawals are not deducted again after the same weekly funding earmarks.
Internal transfers are allocations between accounts, not extra household expense.

## One-time support and retained comparisons

A transfer back reduces the fund once and supports checking once for one chosen
week, conditional on access and settlement. Direct fund spending reduces the fund
without supporting checking. Neither changes recurring allocations or creates
income. Every table row represents an alternative scenario. Goal rate and projected
balance are recomputed after both draws. Existing balances are not silently reused
as weekly income. Invalid trials retain entries for correction without calculating
or saving results.

The signed save creates a separate immutable local comparison under
`local_scenarios/weekly_comparisons/`, not an actual transaction or a changed report.
`/weekly-checks` lists them. Saved comparisons retain dated inputs, trial parameters
and the assumed contribution count. They never refresh automatically; use the
current report for a new trial. JSON preserves exact inputs; CSV summarizes each
alternative with formula-safe labels and exact Decimal amounts. Saves reject
changed source inputs, modified signatures, unexpected fields, foreign origins and
missing CSRF tokens. Damaged snapshots are retained and reported, not repaired or
replaced silently. Snapshot size is capped at96 KiB; sources remain64 KiB.

## Source and limits

Input is private `local_scenarios/weekly_system_check.json`, format
`debt-shredder-weekly-check`, integer version1, max64 KiB. It stores dated planning
references, amounts, reported/estimated/intended status, historical scenarios and
unresolved items. Amounts use exact decimal strings and whole cents. Labels are
escaped. Unknown formats/fields, floats, nonfinite amounts, invalid queries,
repeated query fields and out-of-range inputs are rejected. A missing or corrupt
reference is kept and reported; a sample is never substituted silently.

Home links to the report only when its reference exists. Earlier My Money and
saved forecasts still retain their original facts. Future dated stress tests must
reuse the existing liquidity engine once account balance basis, protections,
pending lifecycles and payment dates are reconciled. This weekly diagnostic does
not alter the frozen schema/spec or engine modules and does not invent unknown
loan or promotional-card mechanics. No bank syncing or payment execution.

## Verification

Tests use synthetic inputs only and cover funding arithmetic, goal rounding,
negative cases, current/tested separation, Decimal context, HTML escaping, strict
reference parsing, local Host protection and read-only GET comparisons. Private
reported figures and screenshots are excluded from source checkpoints.

Verified release:925 passed in107.12s full suite. Browser correction, signed save,
reopen and JSON/CSV equivalence verified. Tests also cover independent cent-based
goal rounding, one-time versus recurring amounts, strict saved-input parsing,
source-change rejection, export escaping and existing liquidity engine conservation
and settlement gates. All48 pre-existing private JSON records and engine/schema/
spec hashes unchanged. Private figures and screenshots are excluded from source
checkpoints.
