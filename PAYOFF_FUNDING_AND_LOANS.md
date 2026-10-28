# Separate funding accounts and simple-interest loans

The ordinary-card payoff planner now supports up to 20 physical cash accounts.
`opening` is the sole primary account; `additional_openings` contains the others.
Each keeps its own floor, reserve, held and committed money. No account is combined
with checking just because it exists or is eligible for transfers.

Optional `payment_sources` names one cash account for every debt. When omitted,
all debts use the primary account, preserving older single-account inputs. Routes
must be complete, unique and reference known accounts. The app adapter retains the
funding sources in saved payment requests. If one debt changes funding accounts
between dates, this first static-route adapter refuses to guess a single route.

Cash plans can contain explicitly timed internal transfers/contributions and reserve
changes. The existing ledger handles debit, in-transit, credit, hold and settlement.
A transfer is never external income or expense; protected balances remain attached
to the physical account. No transfer is generated automatically to rescue a payment.
Declared transfers appear alongside payment schedules, including their arrival times.

A shared payment target is first allocated to minimums, within each named funding
account's capacity. If a required minimum cannot be funded, no extra is allocated
from another account in that round. Extra funds never jump account boundaries.
All declared cash events are protected through the full cash horizon, including the
90-day tail. The plan can be more conservative than a global routing optimizer.

Payment rows and CSVs now identify the funding account. JSON includes all ending
cash accounts, reserves and amounts above floors. The legacy `ending_checking`
field looks up an account actually named `checking`; it is null if absent. It no
longer assumes the first sorted account is checking. `primary_cash_account_id`
identifies the actual primary account independently of display order.

Minimum compliance now checks contractual due dates. Smaller weekly payments can
add up to a required minimum before its due date. The separate
`all_minimum_requests_funded` flag records whether every individual opportunity
could fund the entire then-outstanding minimum; it is not itself a late-payment
verdict. Missed dates remain visible after later catch-up payments.

## Supported installment calculation

`engine.loan_payoff.plan_loan_payoff` is a separate, headless calculation for a
simple-interest installment loan using principal curtailment. It reuses the
existing `accrue_loan` and `pay_loan` functions and the same multi-account funding
checks. Inputs require the note rate, opening principal/accrual/fees, contractual
payment, explicit due dates through the horizon, payment lifecycles and cash events.
The disclosed APR does not replace the note rate.

Accrual runs from opening to each credit date as [start, credit); interest is rounded
only when an actual payment is applied. A zero-funded opportunity does not post or
discard unpaid fractional interest. The end-of-horizon residual includes the ending
day. Payments follow fees, then rounded accrued interest, then principal. Principal
curtailment does not pre-satisfy future installment periods. Regular payments within
the current supplied installment period can satisfy its minimum before the due date.

The result reconciles payment/principal/fee totals, reports unposted interest and
missed dates, and returns no payoff date for an unfinished or non-amortizing balance.
Paid-ahead and precomputed-interest contracts fail explicitly; their real servicer
schedules/rebates are required. New fees, penalty rates and contractual changes are
not inferred. This is an estimate, not a servicer payoff quote.

```sh
.venv/bin/python payoff_cli.py --loan-demo --output-dir a-new-loan-folder
.venv/bin/python payoff_cli.py --loan-input a-new-loan-folder/inputs.json
```

The loan sample starts at $1,000, 12% note rate, $100 contractual installments and a
$150 payment target. It pays $35.81 interest, $1,035.81 total, and finishes July 20,
2026. The disclosed APR is deliberately different. The app sample is available at
`/loan-payoff-example`, with exact-input and dated-payment downloads.

Standalone card and loan schedules must not be added together against the same cash.
Use the new `engine.mixed_payoff` planner for joint scheduling under one shared
budget; see `MIXED_PAYOFF.md`. No assumption has been made that the user's Avant
loan is the supported loan type. All source examples are synthetic.
