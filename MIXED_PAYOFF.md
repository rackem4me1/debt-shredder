# Cards and loans sharing one budget

`engine.mixed_payoff` combines supported cards and installment loans under ONE
payment target per round and ONE physical cash ledger. It does not add independently
funded schedules together. Existing card-only and loan-only planners remain usable.

At most 10 debts in total, 20 cash accounts and 120 payment rounds are accepted.
Every debt ID must be unique across both classes. Payment sources are either all
primary by default or explicitly complete for every debt. Floors, reserves, future
supplied bills, commitments, holds and transfer settlement stay account-specific.
No cash pooling or rescue transfer is inferred.

Each round first funds the then-unpaid minimums of all debts in account-ID order.
If any minimum cannot be funded, no extra payments are made in that round. Otherwise
extras follow either highest interest first or smallest current balance first.
Card APR and loan contractual NOTE rate determine rate priority; disclosed loan APR
is not substituted for the note rate. IDs resolve ties. Principal-curtailment extras
do not cancel future loan installments. Early partial payments count toward the
current installment; actual due-date compliance is reported separately from whether
every early opportunity funded the full outstanding minimum.

Card replay and loan replay run from their original immutable inputs with explicit
accepted credits. The existing card daily replay and loan fee/interest/principal
waterfall remain authoritative. Loan interest rounds only at a positive payment.
The final common cash ledger includes every accepted debit exactly once and is also
returned with the loan projections. Aggregate scheduled payments, credited amounts
and cash payment plans must reconcile.

A payoff date requires every card's posted AND unposted interest and every loan's
principal, interest and fees to reach zero. Trailing card interest can make that date
later than the final card payment. Results separately expose posted card interest,
loan interest paid, unpaid accrual and loan fees. A strategy winner is shown only
when BOTH plans finish, meet minimum due dates and retain healthy cash. It compares
these two strategies; it is not a global optimizer or servicer payoff quote.

Supported terms remain ordinary single-segment purchase cards, simple daily
interest, lost grace and no promotions; loans must be simple-interest contracts with
principal curtailment and explicit due dates through the horizon. Paid-ahead,
precomputed rebates, new fees/rate changes, new borrowing and bank actions remain
outside this planner. No actual Avant contract terms have been assumed.

## Run and replay

```sh
.venv/bin/python payoff_cli.py --mixed-demo --output-dir a-new-mixed-folder
.venv/bin/python payoff_cli.py --mixed-input a-new-mixed-folder/inputs.json
```

Outputs are exact-input JSON, summary JSON and one dated CSV per strategy. Existing
strict JSON parsing rejects duplicate keys, floats, nonfinite values and unsupported
versions. CSV identifiers remain spreadsheet-safe. The app uses the same engine at
`http://127.0.0.1:8765/mixed-payoff-example`; its target control changes only this
synthetic preview. Downloads use the target currently shown. No personal records
are modified or real payments scheduled.

The sample has $1,500 of cards and a $1,000 loan, one $300 monthly target, $1,200
monthly income and $900 monthly bills. Highest-interest-first pays $2,646.39
including $146.39 interest; smallest-balance-first pays $2,687.25 including $187.25
interest. Both reach zero November 30, 2026, including trailing card interest.
The last loan payment can occur earlier. These figures describe the supplied sample,
not a forecast for the user's accounts.

## Explicit recurring transfers

`PayoffTemplate.transfer_schedules` now accepts declared recurring transfers and
sinking-fund contributions. Each rule requires source/destination, amount, first
date, frequency, local clock, calendar-day debit/credit/settlement delays, explicit
monthly short-month policy when applicable, and optional final initiation date.
A schedule cannot precede the opening balance date. No automatic recurrence or
bank-holiday handling is inferred from old transactions.

Generated transfers continue through the cash horizon. A lifecycle started by the
horizon but settling later is retained: its commitment, transit or hold is still
protected. `pending_transfer_ids` identifies these events. Transfers never increase
external income/outflows; contributions reserve money in the destination account
on settlement. Existing individual cash events are retained and duplicate IDs fail.
This recurrence extension currently applies to card payoff templates. Mixed inputs
accept the same fully dated transfers, but there is no mixed-calendar template or
transfer-entry form yet. Older saved payoff templates/runs still load with empty
transfer rules and unchanged expanded dates.

## Save, reopen and review prepared inputs

The sample screen has a save button. Saved combined runs appear at
`/mixed-payoff-runs` and retain the exact input snapshot under a new ID. Reopening
recomputes the same comparison without changing the original balances or any earlier
run. Downloads include exact inputs, schedules for both strategies and a summary
endpoint. Files are kept locally in `local_scenarios/mixed_payoff_runs/` and are
excluded from source checkpoints.

`/mixed-payoff/import` accepts prepared mixed-input JSON, including inputs exported
by the headless tool. Review calculates before writing; only the signed review's
save button creates a run. Host/Origin/CSRF checks, form/JSON size limits, exact
field checks and signed payload checks apply. Changed reviews fail without saving.
Each run is written atomically to a new filename; it cannot overwrite an earlier
run. A bad local file is kept and reported rather than deleted.

Prepared inputs are labeled supplied estimates. The sample is labeled synthetic.
This is an advanced import path, not yet a simple loan-entry wizard. No contractual
inputs have been filled in from the user's historical payment amounts. Exact-input
exports can be reviewed again to restore a separate local calculation.

Source examples: `mixed_payoff_example/` includes both strategies and exact inputs;
`payoff_transfer_template_example.json` and `payoff_transfer_example/` demonstrate
explicit monthly transfers with delayed arrival. All are synthetic.
