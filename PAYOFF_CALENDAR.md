# Repeating payoff calendars and saved runs

The payoff engine can now start from a small set of known statements and expand
explicit repeating assumptions into a complete, reviewable calendar. The result
still goes through the same `engine.payoff` calculation.

In an existing saved plan, open **Repeat a longer payoff calendar**. Supply the
payment target, first initiation, end date, weekly/biweekly/monthly cadence,
short-month policy and lifecycle delays. Future statement closes/due dates use
the saved account days, with the due date in the following month. Known cycles
are retained. The form stops when those assumptions conflict with the latest
known statement dates or when a statement lag would have to be guessed.

Payment initiation is explicitly noon in the shared card timezone. Lifecycle
delays are calendar days; no weekend or bank holiday shift is inferred. Monthly
short dates can clamp to month-end or roll to the next month's first day. Only
complete lifecycles within the end date are included, and excluded initiation
dates are reported. Ambiguous/nonexistent DST clock times fail explicitly.

Only saved declared cash schedules repeat. Existing stop dates stay in effect;
one-time entries remain one-time. When no repeat rules exist, the existing dated
cash events remain in place and the result warns that no future income or living
costs have been invented. Cash schedules expand through the required 90-day tail
beyond payment initiations. No transfer or savings account is converted into cash
income. Payoff funding now supports explicit per-debt routes across separate physical accounts; no funds are pooled automatically.

Generated statement dates and unchanged future rates/minimum terms are estimates,
not verified future contracts. Promos, active grace, mixed card/loan scheduling and overlapping lifecycles
remain outside this card payoff path.
A separate simple-interest loan payoff path is now available, while mixed card/loan scheduling remains pending. Transfers are modeled as internal movements, never external income. There is no new bank access or real payment scheduling.

After previewing, **Save this payoff run** keeps the original source snapshot,
template and expanded explicit inputs together in an immutable local record.
The source must still match the reviewed copy when saving. Later source edits do
not affect a saved run. Saved runs are available from the existing home page and
at `/payoff-runs`. A corrupt or inconsistent file is retained and not silently
recalculated into a different calendar.

Saved runs offer both dated payment schedules as CSV and both forms of exact JSON
inputs. The explicit JSON runs without calendar generation; the template JSON
regenerates dates from the recorded rules. Downloads contain financial inputs and
remain local. CSV identifiers are emitted as text to avoid spreadsheet formulas.

For the headless command:

```sh
.venv/bin/python payoff_cli.py --template payoff_template_example.json --output-dir a-new-payoff-folder
.venv/bin/python payoff_cli.py --input a-new-payoff-folder/inputs.json
```

The supplied template is synthetic. It uses the same $1,500 example and reproduces
$74.18 / $93.43 interest for the two strategies. Export folders also retain the
original template, generated cycle IDs, and any excluded payment initiations.

Runtime limits remain explicit: up to 10 ordinary cards, 120 payment rounds,
3660 days, and 2000 expanded cash events. For example, a long weekly schedule may
exceed 120 rounds before reaching ten years; it fails instead of truncating.
Calculation time grows with accounts, rounds and horizon. Saved dates and contract
inputs are not refreshed from a bank. A sample's successful payoff does not make
an incomplete personal bill budget complete.


Explicit transfer/contribution recurrence is now available through
`transfer_schedules`; see MIXED_PAYOFF.md and
`payoff_transfer_template_example.json`. Source/destination, cadence, calendar-day
lifecycle delays, short-month policy and stop date are declared. Transfers pending
at the cash horizon retain protected commitments/transit/holds and appear in
`pending_transfer_ids`. Transfer principal is never external income or spending.
Older templates default to no recurring transfers.
