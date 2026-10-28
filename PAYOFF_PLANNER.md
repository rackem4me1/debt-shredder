# Standalone payoff planner

This milestone answers: which account gets each payment, on what date, how much
interest is posted, and when all modeled debt (including residual interest) reaches
zero. It runs without a web server, browser, account connection, or LLM.

Run the synthetic example from this folder:

```sh
.venv/bin/python payoff_cli.py --demo
```

Export exact inputs, a comparison JSON, and one dated CSV per strategy into a new
folder (existing output folders are never overwritten by the command):

```sh
.venv/bin/python payoff_cli.py --demo --output-dir my-payoff-example --example-input my-payoff-input.json
.venv/bin/python payoff_cli.py --input my-payoff-input.json --output-dir another-payoff-run
```

Money and rates in input JSON must be decimal strings; APR uses a fraction ("0.24"
means 24%). Input has explicit billing cycles, opening statement minimums, payment
lifecycles, income, bills, cash floor and reserves. The exported inputs reproduce the
result. No income, bill date, transfer, holiday adjustment or loan term is inferred.

Both strategies use the same total target per supplied payment round. Required
minimums get funded first. Under a minimum shortage, ascending account ID is the
explicit tie rule; extra payments wait until minimum allocations are complete.
Then extra follows highest APR or smallest current posted balance; account ID
breaks equal ranks. Unused capacity on a paid account moves to the next account in
that round. No automatic increase in the shared target or future catch-up budget.

Every payment is clipped to available cash after floor, held money and reserves,
using the existing cash ledger. The cash horizon extends through the debt end and
at least 90 days after every initiation. Supply external cash events through that
entire horizon. This first planner conservatively protects all supplied future
bills in that horizon, rather than claiming an optimal rolling cash policy. Later
income cannot cover an earlier shortfall. The reported cash balance is for the
separate cash horizon, not necessarily the debt payoff day.

Existing daily replay calculates interest, statement posting/rounding and future
minimums. Principal zero alone is insufficient: unposted interest must also clear.
Tiny residuals may round to zero only at a later statement close; that later close
is the debt-free date. If supplied dates end first, status is horizon_exhausted with
remaining posted/unposted amounts and no invented payoff date. Missing minimums
and cash breaches remain visible; no comparison winner is claimed in those cases.

The comparison selects the lowest posted interest only among these two completed,
minimum-compliant, cash-safe scenarios. It is not proof of a globally best plan.
Results depend on supplied terms and cash-event completeness. Labels remain estimates.

Current supported scope: 1–10 ordinary revolving cards, each with one simple-daily
purchase segment, lost grace, fixed supplied terms, contiguous explicit cycles,
up to 120 shared payment rounds, and a horizon up to 3660 days. Opening day must be
midnight in each card timezone. Each card has a distinct credit day per round;
rounds settle before the next initiation. Debt replay includes the full ending
local calendar day; cash reporting ends at its stated timestamp. Payments are
capped at posted balances, so accrued interest is settled after statement posting.
No purchases, fees, promos, active grace, installment loans or variable
future contract changes are generated. Explicit internal transfer plans and multiple cash accounts are now supported; see PAYOFF_FUNDING_AND_LOANS.md. Unsupported terms fail explicitly.
Unpaid scenarios do not invent late fees or penalty APRs; they are diagnostic,
not compliant payment recommendations. Previously overdue history is not inferred.

This sample is independent of private user balances. The existing app calls the
same planner; it does not duplicate financial calculations in the UI. Complete
personal plans still require reconciled current inputs. Supported joint card/loan
budgets now use engine.mixed_payoff; see MIXED_PAYOFF.md.

## Existing app integration

Saved-plan pages now call this same engine through a read-only payoff target form.
The adapter preserves exact saved contract/cash inputs and lifecycle dates; it does
not extend calendars. Results appear before the original saved-payment details,
with dated schedules and any unfinished debt, minimum or cash warnings. A source
fingerprint protects against stale previews. No saved scenario is changed.

## Repeating calendar inputs

Use `--template` for explicit recurring payment, statement and cash assumptions.
The calendar layer expands to the same PayoffInputs accepted by `--input`; exported
templates and expanded inputs reproduce the same result. Known statement cycles
are retained. Saved app runs keep both representations, and provide the same CSVs.
See PAYOFF_CALENDAR.md for controls, stop dates and supported limits.
