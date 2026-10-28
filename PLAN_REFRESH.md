# Update figures and review payment timing

On plan review choose **Update balances together**. This shorter form lists all
debts and explicitly used bank accounts. Unused savings remain outside the form
and cannot silently fund the plan. If no primary bank has been selected, choose
it in forecast settings first.

Enter only checked balances, reporting dates, cash cushions and other reserved
amounts. Blank remains unknown; explicit0 is a known zero. Bank overdrafts are
allowed as reported facts; negative debt balances and sub-cent cash are rejected.
An invalid row leaves the entire inventory unchanged and keeps typed answers for
correction. Valid updates retain the previous inventory in its history folder.
A stale account or planning context cannot overwrite newer answers.

This form preserves account names, rates, limits, routing, promotions, notes,
minimums, due dates, interest accrual, loan terms and the separate planning answers.
It does not mark payments paid, add received income, advance the common date or
reconcile pending transactions. Use its account/terms links to review unpaid
minimums, due dates and accrued interest after a payment or new statement. A saved
promotional amount cannot exceed a newly reduced balance; review the offer details
when those figures change. Do not replace loan principal with a payoff total.

Every included balance must match the common reconciled starting date before
calculation. Existing saved result snapshots remain unchanged. Download a complete
setup backup to keep the new inventory and retained planning answers together.

## Correct conflicting answers

Required-input review now identifies payment delay order, first-payment/horizon
conflicts, overdue opening payments, statement date and monthly date conflicts,
unpaid-vs-original minimum bounds, nonpositive loan installments and transfer
delay order. Each issue links to the relevant account, terms, settings or cash
event. Partial drafts still save; readiness does not certify contractual accuracy
or budget completeness. The engine still validates the complete input graph and
all expanded calendars before producing results.

## Read the first payment round

Each strategy shows its first supplied round, with debt name, funding account,
initiation time, estimated amount and unfunded requested minimum. No bank payment
has been scheduled. This is the first round in that estimate, not a live
recommendation for today's date. Verify balances, current bills and lender timing
before using an old saved result.

The full dated schedule has separate **Start payment** and **Credited** columns.
Times use each debt's supplied credit timezone; exact initiation, credit, debit
and settlement timestamps remain in the existing downloads. An unfunded requested
minimum is a shortfall in that round, distinct from whether a due-date obligation
was satisfied by later rounds. No rate, allocation or cash-reserve formula changed.

## Verification

867 tests passed in103.81s; final11 balance-form smoke checks passed in1.64s after
copy/link polish. Browser sample balance refresh, conflict correction, preview,
signed save and reload passed. Only the requested sample cash balance/revision
changed; contract and planning records remained identical. Personal financial
records, every engine module, frozen schema and specification stayed unchanged.
