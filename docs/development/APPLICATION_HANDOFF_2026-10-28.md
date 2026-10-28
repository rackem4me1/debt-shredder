## October28: one-time fund support and saved weekly comparisons

User prefers retaining the existing automatic goal contribution and testing a
transfer back during a tight week. Exact personal amounts and the saved illustrative
comparison remain private in local_scenarios; do not interpret a saved trial as an
executed transaction or overwrite the reported input balance.

Added one-time transfer-back and direct-fund-spending trials, remaining contribution
count, and optional net-pay scenario. Recurring allocations stay separate; each
scenario is an alternative, not another simultaneous transfer. Combined withdrawals
cannot exceed the reported fund balance, and goal funding rounds upward to cents.
Invalid trials retain safely escaped entries for correction without calculating or
saving a result. Future deposits are not available today.

Comparisons can be saved separately, reopened and downloaded as exact JSON or CSV.
Signed saves reject tampering, CSRF and changed source references. Retained reports
keep their original input date/count; they do not refresh with time. Home links to
saved comparisons. No existing financial record, bank instruction, frozen schema,
spec or engine module was changed.

Validation:925 passed in107.12s full suite. Browser excessive-withdrawal correction,
signed save, reload and JSON/CSV equivalence verified. All48 pre-existing private
JSON files preserved by hash. Existing liquidity engine conservation and settlement
gates also exercised with synthetic tests. Local app PID64422 on8765.
Source checkpoint:Debt_Shredder_Fund_Support_Batch.zip.

Next: dated liquidity coverage after account balance basis, pending lifecycles,
protected cash and draft/settlement dates are reconciled. Weekly unassigned amounts
remain a diagnostic, not verified spare cash. Do not guess unknown contract terms.

## October28: first weekly decision-support screen

User clarified cash/pay history, paused housing with no catch-up, reasonable
food/fuel estimates and a flexible goal fund with a deadline and surplus intent.
Those reported figures are private in local_scenarios/weekly_system_check.json.
Earlier reference receipts remain under decision_baseline_2026-10-28. Do not
reuse old balances or treat partial confirmations as settled bank transactions.

Added /weekly-check: read-only weekly allocation comparison over net-pay scenarios,
with adjustable flexible-goal, optional housing and bill-funding amounts. All
financial calculations use Decimal/context isolation. Goal rate rounds up to cents
and assumes the reported balance is eligible, no withdrawals and the declared
number of contributions. It is not an exact dated funding calendar. Existing goal
balance stays assigned; internal transfers are allocations, not extra expenses.

Monthly loan/bill withdrawals are not deducted again after their weekly earmarks.
The bill annual-average check is separate and is not proof of draft-date coverage.
No safe-extra or overdraft conclusion is made. Date, pending-item, balance-basis,
protection and residual-interest gaps stay visible. This implements a first weekly
diagnostic; the dated liquidity report is still next, using existing engine code
when its inputs are reconciled. Loan/promo payoff mechanics remain unsupported
where unknown. No public subscription or broad framework was built.

Home links to the report when its private reference exists. Earlier My Money
entries are labeled as historical on home. GET comparisons never save or activate
choices. Unknown/corrupt reports fail rather than substituting a sample.

Validation:884 passed in104.28s full suite; final17 weekly-report smoke checks
passed after home copy polish. Browser current -> trial contribution/bill funding
comparison verified correct remaining pay and goal balance. All pre-existing
private financial JSON records unchanged by hash. Every engine module, frozen
schema and spec unchanged. Server PID63735 on8765. Source checkpoint:
Debt_Shredder_Weekly_System_Check_Batch.zip. See WEEKLY_SYSTEM_CHECK.md.

## October28: user-approved change to decision support

Start with DECISION_TOOL_NEXT.md. The user supplied an updated automated financial
system and asked where to begin. A separate private reported baseline was saved
under local_scenarios/decision_baseline_2026-10-28/ (original notes, structured
reference and readiness assessment). All existing financial JSON records were
hash-verified unchanged. Do not blend old saved forecasts with the new narrative.

Next milestone: one cash-system coverage/lower-net-pay stress report over existing
liquidity primitives, followed later by promo deadline and extra-loan comparisons
when contract inputs are known. Gross pay, missing housing funding and unverified
automation cannot become assumed net cash or completed transactions.

This step added reference documents, not runtime code or a new dashboard. No
new tests were required; the last runtime verification remains867 full-suite plus
11 final balance smoke checks. Engine/schema/spec unchanged. No bank actions,
reminders, payroll changes, account updates or subscription build were performed.

## October 26: three rounds of plan workflow work

User asked for multiple rounds without interaction. Completed balance refresh,
actionable readiness checks and first-round result guidance, followed by a full
browser walkthrough and regression run. No personal financial entries changed.

Round 1: /setup/<id>/plan/balances edits dated balances and bank protections
together. It changes only those fields plus the account inventory revision; names,
rates, unpaid minimums, accrued interest, contract terms, routing, notes, reviewed
IDs and planning sidecar stay intact. Partial blanks remain unknown and explicit
zero stays zero. Used banks and all debts are included; unused banks are omitted.
All rows validate before one atomic inventory write with history. Combined
account/planning fingerprint guards stale saves. Form supports the full 60-account
inventory (162 submitted fields) without relaxing unrelated form limits. Links
lead to full account and accrued-interest/repayment review; no payment status or
common date is updated automatically.

Round 2: readiness catches conflicting payment delays, first-payment/horizon dates,
overdue opening obligations, statement/date rules, minimum bounds, monthly loan
due rules and transfer delays before offering Calculate. Each issue links to its
source answer. Engine validation remains final. Valid rolled short-month loan
anchors are preserved by the existing schedule helper. No formulas changed.

Round 3: result tables distinguish initiation and creditor credit dates. Each
strategy shows its first supplied round's named debt/funding account, initiation
time, planned amount and unfunded requested minimum. This is an estimate, not a
bank schedule. A round shortage is distinct from the full due-date verdict.
Financial display arithmetic is isolated from ambient Decimal precision.

Verification: 867 passed in103.81s full suite; final11 balance checks passed in1.64s
after links/copy polish. Browser sample updated only the requested cash balance,
retained original terms/planning, exposed and corrected a timing conflict, then
calculated, saved and reloaded. Saved engine inputs match the updated sample.
Original personal financial JSON files unchanged by hash; every engine module,
frozen schema/spec byte-identical to Setup_Recovery checkpoint. Server PID36119
on8765. Source checkpoint: Debt_Shredder_Plan_Refresh_Batch.zip.

The personal plan still needs refreshed facts when the user is ready. No payoff
date was fabricated. Keep work on this existing path; no new planning framework,
bank syncing or broad redesign is required.

## October 25: complete setup recovery and clearer cash schedules

User authorized an unattended batch while personal figures are changing. Added
complete setup backup/preview/restore plus visible cash-event dates, frequencies,
stop dates and named routes. No financial entries or engine modules were edited.

Plan review downloads one strict versioned snapshot containing account inventory,
partial planning settings, repayment terms and cash events. Restore validates and
previews all fields before a signed save. A fresh setup ID is always used; unknown
values, origin, review states and dates survive unchanged. Existing setups, legacy
records, histories, calculated runs and real transactions are not overwritten or
implicitly included. Inventory-only backups remain a separate download.

Restore publishes the inventory last and cleans up a failed unpublished sidecar;
collisions fail instead of overwriting. Host/Origin/CSRF, exact form fields, size,
strict JSON, nested integer versions and payload-signature checks are covered.
The existing local file picker is reused with the format-specific 1 MiB limit.
Cash summaries show saved occurrence dates, not inferred upcoming dates.

Verification: 839 passed in100.83s full suite. Browser sample restore created a
separate copy with identical account/planning records; its engine input JSON is
byte-identical to the original. Original financial JSON records unchanged by hash.
Engine, SCHEMA.py and frozen spec unchanged. Production server PID29425 on8765.
Source-only checkpoint: Debt_Shredder_Setup_Recovery_Batch.zip.

Personal plan still requires refreshed facts when the user is ready. Do not infer
balances, completed autopays, pending items or loan/card contract terms. Stay on
the existing input-to-payoff workflow rather than starting new dashboards/sync.

## October 25: clearer balance updates and next step

User authorized continued work while personal financial figures are changing; no
new facts requested and no personal records edited. Plan review now shows saved
balances, their reporting dates and direct account edit links. Unknown balances
remain unknown; known zero debts and unrouted cash accounts remain distinct.
Mismatched dates prompt reconciliation. Changing forecast dates never refreshes
account balances or marks cash events paid. The first remaining required check
provides a clear next-step link without exposing the entire missing-facts list.

Validation: 47 focused wizard/planning checks passed in10.36s, including three new
regressions for date changes, escaping/unknown-vs-zero display and read-only GETs.
Browser layout verified. All local financial JSON records unchanged by hash.
Engine modules, frozen schema and specification unchanged from prior checkpoint.
The prior full-suite result remains819; this presentation update was validated
with focused checks, not a new full-suite run. Server PID28330 on8765.
Checkpoint: Debt_Shredder_Balance_Review_Batch.zip (source only).

## October 25: wizard-to-payoff path connected

Validation: 819 passed in100.09s full suite; final3 focused smoke checks passed in3.58s after plain-language copy adjustment. Browser wizard preview -> signed save -> reload verified. Production exact-input JSON replayed identically through CLI; both dated CSVs match. Original personal setup and legacy financial records unchanged by hash. All engine modules, SCHEMA.py and frozen specification unchanged. Final local server PID28089 on8765. Source-only checkpoint: Debt_Shredder_Wizard_to_Payoff_Batch.zip.

Existing account setups now link to /setup/<id>/plan. Planning settings, cash events
and calculation terms are saved separately, with history and stale-context checks,
without rewriting the account inventory or legacy My Money/bill/paycheck records.
When required inputs are complete the adapter calls the existing mixed payoff
engine and existing signed save/reopen/download flow. This is a working end-to-end
path, not another standalone sample screen. The user's current setup still has
missing facts; no personal payoff result was fabricated.

Settings use a reconciled balance date; projection starts the following morning.
Included prior cash cannot be replayed. Pending opening items must be reconciled.
Only primary/routed cash accounts participate; unused banks stay outside the estimate
and cannot fund payments. Every active debt and participating bank needs aligned
balances. Limits/APY/autopay are optional. Unknown promotions or unsupported loans
block conversion rather than becoming ordinary cards/simple loans. Zero debt balances
can be skipped, unknown debt balances cannot. Date/interest/minimum rules remain
explicit; authoritative math stays in existing engine modules (all unchanged).

Personal cash import reuses stored expected pay, bills, spending and transfer AMOUNTS
for review without guessing recurrence/routing/timing or marking autopays paid. It
excludes debt payments as living costs and does not duplicate imports. Practice
setups cannot import personal records. Home resumes the latest PERSONAL setup;
practice test records never displace it. Saved results keep human account labels
and the link back to the originating wizard. Old saved runs remain compatible.

New modules: dashboard/setup_plan.py, dashboard/setup_plan_view.py and
 tests/test_setup_plan.py. See WIZARD_TO_PAYOFF.md for supported conversion and
assumptions. The next work should stay on obtaining/reviewing necessary personal
facts through this path. Do not add another broad planning framework or promise a
personal payoff date while required balances/terms remain unknown.

Private labeled practice setup/run references are stored under local_scenarios.
A complete practice wizard was calculated, saved and reloaded in the browser.
The actual personal setup was opened read-only and its progress retained.

## October 25: scope correction — first useful personal plan

User expressed concern about elapsed time and asked whether an easier route existed.
Acknowledge that supporting screens/features grew ahead of proving the real-input
path. Narrow the next implementation to existing wizard -> necessary reviewed facts
-> existing engine -> one dated plan and payoff estimate. Do not start a broader
planning framework, new dashboards, syncing, or unrelated feature batches merely
because tools/usage are available. Reuse current work; no redesign or restart.

A personal wizard already exists and has user-entered progress. Never overwrite it
with practice data or restart account entry. Consult account_wizards and private
readiness notes before requesting facts. Several active-debt balances/terms remain
unconfirmed; software cannot manufacture those. Surface only the necessary missing
items in context. Do not require every optional credit-limit/APY field to calculate.
Keep unsupported promotions/loan mechanics explicit rather than silently substituting
ordinary card/simple-loan behavior. Preserve original dated money and receipt facts.

No new runtime feature was added during this scope review. Frozen engine/spec remain
unchanged. Previous wizard checkpoint remains the tested release.

## October 25: resumable account wizard requested by user

User specifically asked for an account-count wizard: bank/checking/savings counts,
credit card/loan counts, then important account questions including balances,
interest, limits and promotions. Implemented /setup with separate count questions,
one account per page, save/next/back/later, persistent resume summary and add-account
buttons. Home now links to setup and saved setups. No JavaScript required.

New dashboard/payoff_setup.py inventory models preserve optional/unknown vs zero,
reporting dates, bank cushions/reserves/APY, card APR/limit/minimum/due/funding/autopay
and promotional amount/rate/end/post-rate, and loan APR/note rate/principal-vs-total,
interest type and extra-payment behavior. 0% vs deferred vs other promotions stay
separate. Unsupported promotions/loan terms are retained and flagged, never turned
into a payoff estimate. Only nicknames are required on account pages. Counts are
bounded; the inventory can exceed engine debt limits without claiming support.

Private data stays under local_scenarios/account_wizards, with atomic writes,
previous-version history, stale-fingerprint checks and a per-server lock. Unknown
routes, inconsistent promo details, nonfinite/float amounts and sub-cent money fail.
Host/Origin/CSRF/exact-fields are enforced. Optional reuse copies matching historical
My Money facts with original dates; historical card balance date stays unknown.
Original personal snapshot/bill/paycheck/budget hashes are unchanged. Practice setup
is separate/labeled and uses no private figures. Download is backup only; this new
format does not yet have a restore UI.

Scope: this wizard currently collects account inventory. It does not yet convert
the inventory into a complete personal payoff plan. Next add income/bill review and
supported contract/statement questions plus explicit conversion into existing
engine schemas. Do not imply the wizard computes payoff merely because details are
saved. Do not invent promo segmentation or assume actual loan mechanics. Preserve
all already supplied financial facts and avoid requesting them again unnecessarily.

Verification: 789 passed in91.79s full suite, followed by14 focused account-wizard
checks after optional bank APY and final wording. Browser practice bank/card/promo/
loan questions and save/later path verified. Every engine module, SCHEMA.py and
frozen spec byte-identical to Combined_Payoff checkpoint. No personal balances or
bills changed. Local server restarted with tested code; PID26848 on8765.
Source-only checkpoint: Debt_Shredder_Account_Wizard_Batch.zip.
Private practice setup: /setup/2b8ff8d6220b49b996960c2597bbd504.
See ACCOUNT_SETUP.md for behavior and limits.

## October 21: shared card/loan payoff, explicit recurring transfers and saved runs

Validation: 775 passed in89.78s full suite. Browser save/reload, production exported-input CLI replay and both dated CSVs verified. Private original records unchanged. Source checkpoint: Debt_Shredder_Combined_Payoff_Batch.zip (source/examples only).

The new engine/mixed_payoff.py coordinates up to 10 total supported cards/loans
under ONE per-round target and ONE physical-account cash ledger. Minimums across
both debt classes precede extras; short minimums block extras. Rate ordering uses
card APR and loan NOTE rate, not disclosed APR. Smallest-balance ordering uses
current posted card debt and loan payoff amount. ID tie order is explicit. Static
funding routes and each account's floor/reserve/commitments remain separate.

Loan arithmetic was extracted into replay_loan_payoff with validated explicit
accepted credits; the standalone planner wraps it with its existing funding rule.
Accrual, payment rounding, fees/interest/principal waterfall and due-period semantics
are unchanged. Card replay, engine/loans.py, engine/liquidity.py, SCHEMA.py and frozen
SPEC_v2.4_reference.md remain byte-identical to the prior funding/loan checkpoint.
Card-only and loan-only parity tests compare all financial points/audit stages
while allowing different generated payment IDs. Independent Fraction loan oracle
and hand-calculated zero-interest mixed/weekly-minimum cases remain covered.

Joint results reconcile schedule totals, credited debt payments and cash debits.
Payoff requires zero posted/unposted card debt and zero loan principal/interest/fees.
Results expose card posted interest, loan paid interest, unpaid accrual and fees;
no winner is claimed unless BOTH strategies finish with minimum compliance and
healthy cash. Mixed plans currently support ordinary purchase cards with lost grace
and simple daily interest, plus simple-interest principal-curtailment loans only.
Paid-ahead, precomputed rebate schedules, promotions, purchases and new contract
changes remain unsupported. Never infer the user's Avant mechanics.

CLI --mixed-demo / --mixed-input provides exact JSON and dated CSVs. The app at
/mixed-payoff-example uses the same engine and a read-only sample target control.
It can save an immutable local run; /mixed-payoff-runs reopens them. Advanced
/mixed-payoff/import previews prepared mixed JSON before a signed save. CSRF,
Host/Origin, strict field/size/JSON checks and signed-payload checks are enforced.
Each atomic save uses a new ID; prior runs and personal balances are unchanged.
The view separates sample/supplied estimates, shows actual missed due dates, named
funding accounts, loan breakdowns and ending physical cash. No payments are sent.

PayoffTemplate.transfer_schedules now expands ONLY declared transfer/contribution
rules: source/destination, amount, first date, frequency, local clock, delays,
monthly short-month policy and optional stop date. Debit <= credit <= settlement.
Pre-opening rules fail. Initiations through the cash horizon are retained even if
settlement is later; pending_transfer_ids identifies them and ledger commitments,
transit and holds keep that money protected. Contributions reserve at destination;
internal transfers never enter external income/outflows. This template extension
currently applies to card plans; mixed inputs can use explicit dated transfers.
There is no automatic inference from transaction history or bank-holiday calendar.
Old saved payoff runs still load with empty default transfer rules.

Sample combined $2,500 debt / $300 monthly target: high-interest $146.39 interest,
$2,646.39 total; smallest-balance $187.25 interest, $2,687.25 total. Both pay off
Nov30,2026 including trailing card interest. Recurring transfer example matches the
prior explicitly dated checking/Bills Box example ($74.96 high-rate interest).
Saved production SAMPLE: /mixed-payoff-run/8cbb885ff139461883f43b791a960712.
Screenshot and run ID reference are private under local_scenarios.

Next: simplify entry/review of supported contractual loan/card inputs, and connect a
properly reconciled personal snapshot only after actual terms are available. Mixed
recurrence templates, paid-ahead/rebate mechanics and automatic bank syncing are
not implemented. Do not combine independent standalone schedules against one cash
balance. Keep existing personal receipt/transfer snapshots unchanged; consult the private
readiness note before requesting information. No autopays are inferred paid. A date
advancing does not make an old balance a new reconciliation.

## October 20: autonomous two-part batch — physical account funding and loan payoff

Card payoff now accepts additional_openings and explicit PaymentFunding routes.
Old single-primary inputs remain valid. Each account retains its own floor,
reserve, holds and commitments. Named routes are validated complete/unique and
funded independently; savings is not pooled into primary cash. Explicit transfer,
contribution and reserve cash plans use the existing ledger. No automatic transfer
is generated to rescue a payment. Minimums are allocated first; if any required
minimum cannot be funded in a round, extras are blocked even where another account
has cash. Delayed transfer arrival cannot fund an earlier payment. Transfers remain
internal, excluded from external income/outflows. Scheduled rows/CSV identify paid-
from account; result shows separate cash balances and declared transfer timing.

PayoffTemplate carries the same funding records; recurring external cash can name
its physical account. Source adapters preserve per-card request routing and primary
identity independent of tuple ordering. Changing routes across dates or a missing
route in a multi-account source fail rather than being guessed. Saved source/run
validation now compares all physical openings. No frozen source schema edits.
Legacy ending_checking JSON looks up the actual checking ID, not sorted position0;
primary_cash_account_id and ending_cash_accounts remove ordering ambiguity.

Corrected minimum compliance to evaluate due-date misses. Weekly partial payments
can satisfy an installment/card minimum before its deadline. Separate
all_minimum_requests_funded records opportunity-level full funding without calling
a partial early payment a late minimum. Existing minimum tie rules remain explicit.

New engine/loan_payoff.py supports a separate simple-interest principal-curtailment
loan plan with explicit complete due dates, lifecycle slots and the same physical
funding protections. Reuses accrue_loan/pay_loan: note rate, fees -> interest ->
principal, posting only at actual payment, final unpaid interval through end-of-day.
Zero-funded opportunities do not round away unpaid fractions. Principal/fees/paid
totals reconcile. Unpaid interest and missed dates remain visible, no fake payoff
for non-amortizing payments. Paid-ahead/precomputed contracts, ambiguous sub-cent
opening quotes and incomplete due calendars fail. No inferred future late fees,
rebates or contractual changes. No assumption about the user's Avant contract.

CLI --loan-demo / --loan-input exports exact JSON plus a loan CSV waterfall. App
/loan-payoff-example renders the same engine and downloads inputs/schedule. Its
sample pays1000 principal plus35.81 interest, total1035.81, finalJuly20. Loan and
card plans are explicitly separate: joint optimization/shared budget is NOT yet
implemented and their proposed payments must not be added together.

Validation: clean full run732 passed in78.08s after correcting a test-only missing
web-fixture import (initial run731 plus1 fixture error). Final93 focused payoff,
calendar, funding, persistence, loan, CLI and HTTP cases passed in28.58s after the
physical-report-label guard, unfunded-interest and missing-source-route cases.
Independent Fraction loan oracle, note-vs-APR, fee waterfall, weekly due compliance,
zero-funded fractional preservation, below-interest payments, physical reserves,
late transfers, conservation and strict inputs covered. Native browser checked
multi-account paid-from rows/transfer timeline and the seven-payment loan result.
Fresh production app exports replayed identically through both CLI paths. Original
personal balances, receipt and conservative paycheck estimate verified unchanged.

Synthetic examples/readme: PAYOFF_FUNDING_AND_LOANS.md, payoff_multiaccount_example/
and loan_payoff_example/. Private source/run IDs and screenshots remain excluded
from source archives. SCHEMA/spec, loans.py, liquidity.py and all other pre-existing
engine modules except payoff.py/payoff_calendar.py remain byte-identical to prior
checkpoint. Changes extend the supported planner; no frozen architecture redesign.

Next: combine supported cards and loans under ONE chronological cash/payment
budget, then add explicit repeat-transfer rules and personal account-entry support.
Do not sum independent card/loan schedules or invent the missing Avant terms.
Reconciled autopay statuses and complete current debt facts are still needed for
a complete personal plan. See private readiness note before asking repeated questions.

## October 20: autonomous batch — recurring payoff calendars, durable runs and exports

New engine/payoff_calendar.py expands immutable PayoffTemplate rules into exact
PayoffInputs, reusing scheduled_dates and the existing payoff engine. Supports
weekly/biweekly/monthly payment rounds, explicit calendar-day credit/debit/settle
delays, monthly short-date clamp/roll, fixed future statement patterns and declared
income/bill recurrence. Known cycles are preserved; future generated IDs and end-
clipped initiations are retained for audit. Explicit stop dates and one-time cash
entries stay one-time. Cash covers at least90days after every payment initiation.
Ambiguous/nonexistent DST times, overlapping rounds, count/horizon overflows and
unsupported routes fail; no silent truncation or invented income. New monthly
occurrence helper is public within the new module. Frozen schema/spec and prior
engine modules are unchanged.

CLI now accepts --template, exports both template and expanded JSON, assumptions,
generated IDs and excluded initiations. Shared payoff_exports.py formats dated CSVs
for both CLI and app, preserving Decimal strings and text-safe identifiers. Example
payoff_template_example.json plus payoff_repeating_example/ contain synthetic data.

Existing plan page has a collapsed repeating-calendar form. Source account calendar
fields are shown; generated dates/constant future terms are explicitly assumptions.
Saved dates that conflict with the repeating pattern or contain a statement lag
block the form rather than being overwritten. Saved manual cash schedules reexpand
once with stop dates. Sources lacking repeat rules retain dated cash only and show
an incomplete-forward-cash warning. No source scenarios or real money records change.

Read-only repeat preview -> signed save -> immutable payoff_runs/<uuid>.json with
source snapshot and exact expanded calendar. GET /payoff-runs library; /payoff-run/id
reopens captured data independently of later source edits. Downloads: inputs.json,
template.json and both strategy CSVs. CSRF/Origin/Host, strict fields, signed review,
stale-source detection, size caps, deep JSON/float/duplicate-key rejection, atomic
no-overwrite save, canonical template/expanded equality, no-store exports and escaped
names. Saved payoff runs are linked from the existing home page.

705 full-suite tests passed in73.41s after final source-calendar contradiction
guards. Earlier62 targeted planner/calendar/view/persistence checks passed. New34
cases include leap/short/rolled dates, DST, cash stop/one-off protection, delayed
settlement clipping, exact manual-vs-generated parity, saved source independence,
signed/tampered/stale saves, invalid input retention, CSV/JSON export replay, and
known-statement contradiction rejection. Browser filled a two-year sample, computed
both strategies, saved/reloaded its run and verified downloads. Production exported
explicit inputs AND template both replayed through standalone CLI to identical
interest/payoff results. New sample IDs/screenshots and private readiness note are
under local_scenarios, excluded from source checkpoint. Actual personal balances,
received paycheck and conservative next-paycheck estimate remain unchanged.

Next personal-use gaps remain explicit: complete current debt/contract inputs,
reconciled outstanding bills, installment-loan payoff integration and routing across
physical accounts. Do not model Avant as a credit card, use savings as checking, or
infer cleared autopays. The private readiness note retains what the user already
provided so no repeated bills-list interrogation is needed. Continue core work
without cosmetic redesign; ask only for missing facts when starting a personal plan.

## October 20: existing saved plans now call the headless payoff planner

Added dashboard/payoff_view.py. GET /plan/<id> offers one shared target; read-only
POST /payoff-preview/<id> calls engine.payoff.compare_payoff. The result appears
inside the existing saved-plan page, with debt-free dates, interest, paid amounts,
minimum/cash checks, remaining posted/unposted debt and each dated schedule. Original
saved payments are collapsed on the preview to avoid confusing them with generated
strategy payments. No new calculation logic in the UI; no save or bank actions.

Adapter preserves debts, sourced terms, opening cash/reserves, all external cash
events, start/end and exact request lifecycle dates. Requests sharing one identical
lifecycle become one shared payment round. The old requested amounts/priorities
are explicitly replaced only in this preview. No calendar extension, inferred
recurrence or current-balance refresh. Unsupported multiple cash accounts,
promos/grace, missing dates, same-initiation/different lifecycle and overlapping
credit dates fail explicitly. Short scenarios can remain unfinished; no winner or
false payoff date is shown. Actual user balances/receipt/bill statuses are untouched.

Form uses existing CSRF/local-origin protections, strict field set and whole cents,
source fingerprint/stale detection, retained invalid target, escaped account labels
and no-store responses. Source files unchanged on previews. Schedule uses readable
credit dates; exact credit/debit/settlement timestamps remain available in details.
CLI demo/input modules and console entrypoint are now included in package metadata.
engine.payoff validation helper was exposed as validate_payoff_inputs without
changing calculation policy. Frozen schema/spec and earlier engine modules unchanged.

Validation: 671 tests passed in56.57s. Final14 payoff-view/simple-view tests passed
after readable-date formatting; earlier33 planner/view/simple tests also passed.
Adapter parity with standalone comparison, no source writes, unsupported terms,
unfinished plans, stale forms, bad token/origin, invalid money and missing source
covered. Native browser entered250, calculated both strategies, expanded the dated
schedule and confirmed sample74.18/93.43 interest and Aug31/Sep30 payoff dates.
Synthetic sample is available in the existing saved-plan library. Private sample
ID/screenshots stay under local_scenarios and are excluded from source checkpoint.

Next: build explicit repeat schedules/statement assumptions for longer real inputs
using the same engine; collect only missing contract/account data. Do not infer a
complete personal payoff plan from current partial bill/payment statuses.

## October 20: first complete headless payoff planner

New engine/payoff.py uses existing revolving replay and cash protection to choose
minimums first, then highest-APR or smallest-balance extras under a shared per-round
target. Explicit cycles, payment lifecycles, cash events and reserves; no personal
inputs inferred. Up to 10 ordinary simple-daily purchase cards (lost grace), 120
shared rounds, 3660 days. Unsupported promos/grace/loans/transfers fail explicitly.
Residual posted and unposted interest count toward payoff; zero-cent statement
rounding can move the final debt-free date later than the last payment. Horizon
exhaustion, unpaid minimums and cash breaches do not become a guessed payoff date
or comparison winner. Shared minimum shortage ties use ascending account ID.
Cash is conservatively protected through the full supplied cash horizon, at least
90 days after every payment initiation. This is not a global optimizer or a change
to the frozen promo bounded-search architecture.

payoff_cli.py accepts strict versioned JSON or --demo, exports exact inputs,
summary JSON and dated CSVs in a new directory. demo_payoff.py is entirely synthetic.
PAYOFF_FIRST_RESULT.md is the readable verified example; PAYOFF_PLANNER.md describes
scope, commands and assumptions. No new app screens; existing app remains unchanged.
Sample: $1500 debt, shared $250 target; highest-rate-first $74.18 posted interest,
paid off August 31 2026; smallest-balance-first $93.43, September 30. Both meet
minimums and preserve protected cash. These figures are not a personal plan.

Validation: 660 full-suite tests passed in53.57s, including19 payoff cases. Final19
payoff cases passed after minimum-floor validation and CSV zero-row filtering.
Independent Fraction day-ledger oracle, hand-calculated zero-rate case, 20-month
payoff, trailing interest, late cash, future bill/reserve protection, shortages,
invalid inputs, strict JSON and exact export/replay covered. SCHEMA/spec and all
pre-existing engine modules are unchanged relative to the Paycheck Week checkpoint.

Next: integrate this same calculation with existing scenario entry/results, keeping
unsupported personal terms explicit; gather only missing account terms when needed.
Do not add cosmetic screens or promise a full personal plan from partial bills.

## October 20: record a received paycheck without replaying it

Added an optional immutable ReceivedPaycheck record to dashboard My Money (not the
frozen SCHEMA). It retains the actual amount/date, superseded expected payday,
completed-transfer confirmation and separate purpose-account balances. Current
My Money, week and before-payday screens show a receipt summary while the next
payday is unknown. Both calculators and draft-save paths reject reuse of that
superseded payday, preventing duplicate income/transfers. A later explicitly
confirmed expected payday resumes the existing estimate workflow. Individual bills
remain unconfirmed; saved historical drafts retain their original inputs. No
calculation engine, frozen schema or spec changes. Private account values and
receipt screenshot are confined to local_scenarios and its histories.

Validation: 641 tests passed in 50.23s, including six receipt regression cases.
Production three-route HTTP checks and native browser balance-page check passed.
Next: confirm next payday and expected amount, then check outstanding autopays.
Do not infer paid bills from net balance differences. Separate saved-account
balances must not become checking liquidity. No extra-payment recommendation.


## October 20: one paycheck and the following week

Added dashboard.paycheck_week with /paycheck-week, settings, saved-draft library,
POST settings-save/save and /week-draft/<id>. Links from My Money and before-payday
cash view. One expected paycheck only; window starts at reported balances and ends
local23:59:59.999999 six days after payday (seven payday-through-week days). Existing
opening snapshots and what-if scenarios are unchanged. Existing engine/schema/spec
are byte-identical to Before Payday checkpoint.

PaycheckSettings holds explicit estimated Bills Box/KC amounts, arrival delays0..14
calendar days, optional KC opening plus date, and post-payday food/fuel cushions.
Unknown KC balance stays unknown: its proposed transfer is a checking RESERVE, not a
fake zero opening account or expense. Known KC balance requires same reported date as
My Money before true internal transfer simulation is enabled. Actual transfer routes
use CashKind.TRANSFER, deposit is the sole INCOME. Delays are assumed calendar days,
not verified business-day/holiday bank terms. Transit stays separate until arrival.

Pre-payday cushion remains held; post-payday food/fuel is additionally reserved after
deposit. Neither is actual recorded spending; no prior cushion release is inferred.
Drafts compare two explicit orderings: deposit09, transfers10, bills11 versus payday
bills07, deposit09, transfers10. These hours encode illustrative order only. Daily
closing table does not hide whole-period intraday breaches. Non-payday same-day order
and actual settlement times remain unverified. No extra-payment recommendation.

Cash bills on/before starting date, undated or requiring unresolved checking-from-
savings routes remain unresolved. Card charges in window remain separately listed,
never checking expenses or silent additions to authoritative debt. Debt-payment kinds
use bank PAYMENT lifecycle only; no loan/card interest engine is invoked here.

Immutable WeekInputs retain base snapshot/billbook/prepay cushions plus settings.
Private settings history and atomic non-overwriting saved drafts. CSRF, digest of all
sources, ordered money/bills/cash locks, retained invalid values, calculate/validate
before save. Saved views route to current picture before editing. Initial real draft
saved from existing estimates; known transfers/spending initialized privately, no real
bank data in source fixtures. Private history/drafts/screenshots excluded from archive.

635 full-suite tests passed in50.26s. Final14 week tests passed after form wording
clarification. New14 cases include independent cash conservation, real internal transfer
classification, unknown KC hold, same ending balances despite intraday shortage,
delayed arrival and transit, excluded card charges/opening-date bills, exact save/reopen,
Decimal precision, invalid settings and stale dated KC balance rejection, HTTP save/edit
and source digest protections. Browser sample delayed-transfer/cushion edit and save
verified. Final real cash screen read/visual verified; app remains127.0.0.1:8765.

Next: reconcile actual deposit, dated balances, bill status and bank transfer timing
before relying on a personal payment amount. KC opening remains optional/unknown until
provided; do not ask to re-enter known inputs. This is a useful paycheck-to-week draft,
not complete household coverage, actual transaction replay or a full payoff adviser.


## October 18: before-payday cash picture, cushions and saved drafts

Added dashboard.payday_cash and /cash-until-payday, budget editor, saved-draft library,
POST budget-save/save and /cash-draft/<id>. Links from My Money and bills. Reuses the
existing project_liquidity engine; no engine or frozen schema/spec changes.

Window is from reported balance date through23:59:59.999999 local day before expected
payday (America/Chicago), limited1..60days. Expected income/automatic paycheck transfers
and same-day payday bills are explicitly outside scope. Bills on the balance date,
prior dates, unknown dates, card charges or checking-from-BillsBox transfer routes
remain unresolved rather than silently deducted. Covered/excluded entries omitted.
Direct dated cash bills in window become explicit same-date/midnight CashPlans.
Bills now have optional backwards-compatible cash_kind (bill/debt_payment). Existing
loan/card-minimum imported rows classified as debt_payment; these use PAYMENT cash
lifecycle, not ordinary expense. No loan/card balance or interest projection here.

Checking and Bills Box remain separate. Savings ineligible for primary payment cash;
zero additional savings floor is an explicit modeling assumption for its own bills.
Food/fuel cushions are additional checking reserves, held in full for entire period;
not actual spending or weekly repeats. Real settings initialized from estimates already
provided in conversation; no source-code personal fixtures. Snapshot and balances not
modified. Initial private cash draft saved so it can be reopened without re-entry.
Conditional/unresolved alerts retained; safe_immediate_payment is never presented as
a personal extra-payment recommendation. User still needs real data reconciliation.

EverydayBudget exact nonnegative cents, history/atomic replacement. Saved DraftInputs
retain full immutable snapshot, billbook and budget, versioned and recalculated on open.
Save writes atomically to a unique UUID path. Source digest checked with money/bill/cash
locks and CSRF; stale edits rejected. Budget form retains invalid input. Saved views
route to current picture before edits, avoiding implication archived inputs can mutate.
Private budget/history/drafts/screenshots excluded from source checkpoints.

621 full-suite tests passed in49.67s. Final40 targeted cash/bills/MyMoney cases passed
after ordering, conditional labels and saved/current navigation adjustments. New18 cash
cases include independent account arithmetic/conservation, no future-income funding,
reserves/floors, debt payment lifecycle, no card-charge/transfer expense misclassification,
zero bills, balance-day/payday boundaries, DST fall-back and save/reopen immutability,
malformed cushions, stale balances/bills/budget checks. Browser sample save->edit current
cushion->reopen saved draft confirmed original inputs retained. Final real cash screen
read/visual verified at8765. Unknown quarterly dates remain visible; no real bank actions.

Next: extend beyond payday only after explicit income/transfer timing representation;
resolve bill uncertainty/reconcile balances before personal payment advice. Do not infer
KC opening balance, treat internal transfers as expenses, or duplicate card subscriptions
as cash withdrawals. Preserve dated source inputs and this bounded current cash view.


## October 17: bills connected to the starting picture

Added private BillBook/Bill draft occurrence models and /bills, /bills/edit/<id>,
POST /bills/save. Existing user list imported into21 private rows; all historical
amounts/status remain estimates. Nearest monthly occurrences after the source date
are tentative dates, not verified due obligations. Unknown quarterly dates remain
undated and outside totals. Old zero-payment rows excluded. No rent obligation is
inferred. Quicksilver statement minimum/due always reflects current My Money,
retaining unverified payment status; use My Money to change that linked figure.

Separate totals for Bills Box-funded bills (including checking payments funded by
Bills Box), directly checking-funded bills, and card charges. Transfers are not
another expense and card subscriptions are not counted as checking withdrawals.
Totals cover listed dated occurrences, not a monthly budget. First5 cash items shown;
remaining cash/card/undated/covered/excluded groups collapsible. Before-payday totals
include only active dated cash occurrences from balance date through day before
expected payday; same-day paycheck/bill order remains unknown. Transfers and everyday
spending have NOT been modeled in a cash projection. No safe extra payment or running
bank balance claimed. This completes organization/review, not full cashflow wiring.

User can edit one occurrence, including estimated/included/already-reflected/excluded
status. This is a draft status, not an actual payment record. No automatic recurrence
rollover or bank balance mutation. Valid finite whole cents, date+route required for
included rows, immutable unique IDs. CSRF, fingerprint, server lock, retained invalid
values, atomic replace and content-hash input history. Snapshot/scenario files stay
unchanged. Private bill book/history/screenshots excluded from source checkpoints.

602 full-suite tests passed in48.60s, then13 bill tests passed after final grouped
layout/before-payday addition (603 final collected cases; final full suite not rerun).
Browser My Money->bills verified real imported routing, labels and conditional totals;
no real bill status edited. Engine/schema/spec unchanged. Existing app remains8765.
Next: cash-flow projection must explicitly resolve tentative bills, transfer timing,
expected income and everyday spending. Do not mistake this bill calendar for a fully
funded personal plan, or ask user to re-enter the list already saved privately.


## October 17: dated My Money starting picture

Added /my-money and /my-money/edit, plus a home banner when the local record exists.
User authorized reuse of last night's information after being asked redundantly.
Dated user figures and existing bills/transfer notes are now in the private local
money_snapshot.json, separate from hypothetical Scenario inputs. Do not ask for the
same information again; consult this private record when needed. It records partial
historical inputs, not a live balance or complete bill forecast. Card minimum is a
statement amount; paid/unpaid status is not verified. Paycheck explicitly estimated.
Checking and Bills Box displayed separately; no extra-payment amount inferred.

MoneySnapshot enforces finite Decimal whole cents; negative cash allowed but cushion,
card and paycheck nonnegative. User edits preserve notes. Save is under server lock,
checks source fingerprint + CSRF, preserves prior record by content hash in private
money_history, and atomically replaces the current record. Invalid fields retained;
stale/corrupt records fail without replacement. Fixed file has no32hexID and is
excluded from scenario library/compare/backup routes. Existing scenarios untouched.

590 full-suite tests passed in47.55s.9 new cases exercise history, decimal checks,
separate-account/estimate labels, escaping, stale/invalid edits and missing/corrupt
records. Browser real starting picture inspected at local8765; no real edits made
through browser. Private screenshot under local_scenarios, excluded from checkpoint.
Engine/frozen schema/spec unchanged. No external sync or bank action. Next: connect
already-recorded bills to dated cash flow, preserving unknown payment status and
credit-card-vs-cash routing. User should not need to re-enter known data.


## October 17: simple payment adjustment and review

Payment editor/review now use the simple green dashboard theme. Step1 shows named
card/payment portions, initiation/credit dates in creditor timezone, editable amounts
and version name. Invalid entries remain filled in for correction, while stale or
corrupt source files fail safely. Original fingerprint, exact field set, immutable
copy construction and signed save validation remain enforced.
Step2 shows requested vs applied totals, before/after amounts per request, unfunded
amounts, each physical cash account before/after with protection settings, posted/
unposted debt and missed minimum dates. Whole-window cash alerts remain explicit.
Technical payment-order detail is collapsed. Dates are rendered in shared creditor
timezone, or UTC for mixed-zone portfolios. Only /payment-save redirects to /plan/<id>;
other saves retain existing behavior. Simple summary cash wording now describes
protection settings without claiming an underfunded account actually holds them.

581 full-suite tests passed in46.35s;13 payment tests passed after final readable-date
formatting. New checks cover retained invalid inputs, original preservation, corrupt
source recovery and visible missed dates/cash/interest. Existing save test asserts
simple-summary redirect. Browser sample adjustment25 -> warning -> copy save -> simple
summary verified in isolated temp data. Sample screenshot saved outside source tree.
No real saved data changed. Engine/schema/spec byte-identical to Simple App checkpoint.
Verified old server identity and restarted it; normal8765 address responds. Next work
should continue simple everyday workflows, preserving all warnings and source dates.


## October 16: user-facing usability pass

User explicitly wanted a working understandable app rather than more technical
screens. Home now has a single primary walkthrough action, saved plans beneath,
and advanced examples/search collapsed. New /walkthrough and /walkthrough-shortage
use actual practice_forecast engine results with plain-language monthly payment
cards, protected money, bill and ending cash/debt. No input required. Clearly labeled
sample money and minimum-only scope, assumptions available in collapsed details.
New /plan/<id> is the library destination: plain payment/cash summary, missed-minimum,
missing-request, unmet-payment and whole-window cash warnings preserved. Unposted
interest separate; physical accounts separate; details and advanced tools collapsed.
Full old /scenario/<id> remains available and links to the simple view.

Local app now runs at127.0.0.1:8765. START_APP.py and Open Debt Shredder.command
reuse that running server or start a detached local one with the existing venv and
local_scenarios directory, then open the browser. Closing launcher leaves server
running. Missing environment / busy port errors are explicit. No installs, no bank
connections. Launcher health detection verified against running app; cold-start
branch not separately exercised in this batch. Archive excludes runtime log.

578 full-suite tests passed in45.59s. Browser home->walkthrough->shortage checked,
full desktop screenshot and390px mobile screenshot reviewed, viewport reset; sample
walkthrough left visible as deliverable. No saved user data or engine/schema/spec
changes. Next priority: user comprehension and fewer steps, not another list of
technical phases. Remaining forecasting limits/persistence documented previously.


## October 16: personal multi-month minimum preview

Saved reports link to /personal-forecast/<id>; POST /personal-forecast-preview uses
CSRF/Host/Origin protection and an original-scenario fingerprint. Read-only: no save,
no original mutation. Scope:1–3 ordinary simple-daily cards without grace/promos,
one cash account, shared timezone, explicit non-assumed minimum floor/rate/rounding
(estimates remain allowed and labeled). Two additional complete cycles and three
payment lifecycle slots per card are entered explicitly with per-card priorities.
Cycles must append without gaps, cover end, and horizon cannot shorten original or
exceed366days. Engine retains lifecycle-overlap and same-day priority guards.
Date-only slots use local midnight; user sees this timing restriction before entry.

Existing requested payments, including extras, are replaced only in preview by
minimum-only generation. Original opening date/balances remain unchanged. Saved
recurring cash schedules expand to the new cash horizon (stop dates preserved),
while one-time/raw events are not invented or repeated. Expanded events capped500.
Preview shows every generated request/lifecycle, cash events, final posted/unposted
debt, missed dues, cash status, floors/reserves, sourced minimum terms and separate
cash/debt horizon. Empty rows and unsupported-card early rejection are explicit.
Validation errors retain entered form fields. No payoff optimization or extra policy.

575 full-suite tests passed in45.00s; final targeted11 passed after early eligibility
and empty-table/timezone display changes. Tests cover independent math, dual-card
shared cash, future-cash expansion, gaps, horizons, timing, assumed terms, no writes,
stale source and retained error inputs. Browser completed synthetic one-card entry
and preview with expected25/40.76/37.72 and296.52 ending cash. Frozen schema/spec and
all engine modules are unchanged. No real saved scenarios were changed.

Next: persist/reopen the extended forecast as its own versioned input artifact,
without feeding generated requests through the older opening-balance-capped
Scenario.project path. Then improve date entry and verified scheduling support.
This phase intentionally supplies a preview only, not a saved full payoff plan.


## October 16: explicit future-minimum term entry

Saved reports now link to /forecast-terms/<id>. The form shows existing sourced
floor/rate/rounding and requires explicit new values for all cards. It accepts user
estimates or user-confirmed values (confirmation date required); estimates cannot
carry confirmation dates. Decimal values stay exact; floor must be whole cents,
percentage0..100. Formula acknowledgement is explanatory, not persisted as a claim
that an issuer formula has been verified. Rounding applies to interest posting as
well as projected minimums. Other sourced terms retain their original provenance.

POST /forecast-terms-preview checks original fingerprint and strict fields, builds
and validates a candidate, and shows old/new terms. HMAC-signed existing restore-save
creates a new UUID copy. Original bytes, schedules, balances, priorities and cash
inputs remain unchanged. This does not extend the horizon or generate new payments.
Existing simple editor may reject copies whose updated terms it cannot preserve;
term review and exact payment-amount editing remain available.

564 full-suite tests passed in44.28s; 13 targeted tests passed after final display-only
wording edits. Browser sample entry, old/new review, screenshot and copy-save verified
in an isolated temporary directory. Frozen schema/spec and all engine files unchanged.
No real saved plans changed. Next: explicit future cycles/payment slots and income/
bill horizon integration, preserving supported-scope checks. Personal multi-month
forecast integration remains incomplete; do not present this as a full payoff tool.


## October 16: multi-card forecast practice dashboard

Added read-only /portfolio-forecast-example and home-page link. Two synthetic
three-month forecasts share identical card terms, $50 Jan25 bill, $100 floor and
$20 reserve; starting checking is $400 or $200. Two $1000 cards use .365 APR,
simple daily /365, $25 or 1% plus billed-interest minimums, no grace/purchases/fees.
Explicit coincident lifecycle slots on each month's20th use card1 priority.
Funded case pays206.96, leaves143.04 cash; shortage pays30, leaves120. Every result
comes from portfolio_minimum_forecast, with generated/requested/applied/unfunded
rows, final debt and missed due dates. No full payoff date or optimal priority is
claimed. Unfunded-request sums are explicitly not unique overdue debt. Separate
Mar31 debt and June18 cash horizons and absence of April payments are disclosed.

551 full-suite tests passed in43.36s; final test-only no-write assertion then passed
with all4 dashboard tests. Browser full-page layout and assumptions anchor checked.
Frozen spec/schema and all engine modules unchanged. No saved user data changed.
Next: explicit personal contract inputs and supported scheduling integration;
current practice page cannot be treated as a personal payoff recommendation.


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


## October 16: saved-plan overview

Added a responsive plan-at-a-glance section to the shared report: accepted versus
requested payments, account floors plus end-of-cash-window reserves, and posted
debt with unposted interest separate. Totals count each cash account once. Protection
settings are explicitly not available spending money or proof that floors are met.
Missed dues, unmet requests, missing requests and whole-window cash alerts are shown
above the existing full details. Separate debt/cash horizons remain explicit.
Anchor links navigate to each detail table; all existing information is retained.
No calculation, frozen schema/spec, or saved scenario data changed.

Verification: 534 tests passed in 42.47s. Three new cases cover shared cash totals,
missing-payment warnings and cash-buffer breaches. Browser full-page visual review
and payment-details navigation passed on the synthetic demo.

Next: independently validated multi-card future minimum coordination and explicit
contract input support, before full payoff recommendations. The overview remains a
bounded scenario forecast, not a complete household budget or safe-to-spend quote.

# Latest checkpoint — October 14, minimum forecasting

Three-statement fixtures and a one-card generated-minimum forecast are complete.
527 full-suite tests plus4 added guard cases passed (531 collected cases).
See final October14 entry for supported scope; earlier entries are historical.

# Latest checkpoint — October 11, payment editor

509 tests passed. Exact-priority payment amount editing and before/after review
complete. Multi-month implementation readiness documented, not implemented.
Earlier entries are historical; see final entry for current scope.

# Latest checkpoint — October 11, 2026

499 tests passed. Backup restoration with preview/new-copy save and searchable
scenario library are complete. See the final October 11 entry for verification and
next steps. Earlier entries below are historical.

# Latest checkpoint — October 7, 2026

478 tests passed. Latest work: review/save comparison alternatives, plain-language
comparison takeaways, and downloadable individual scenario backups. See the final
October 7 entry below for current verification, limitations and next steps.
Earlier dated entries are historical checkpoints, not current test counts.

# Debt Shredder handoff — September 28, 2026

## Current state

**368 tests pass:** 91 approved schema cases, 203 engine cases and 74 dashboard cases. Exact runtime/dependency versions and execution output are in TEST_RESULTS.txt. The frozen SPEC v2.4 reference and approved revision-5 SCHEMA.py remain byte-for-byte unchanged. Nothing under sources/ was edited. No real accounts, external messages, deployment, or production financial advice are involved.

This checkpoint combines several steps completed in one autonomous work session:

1. Explicit promo assessments now execute once within daily debt replay.
2. Replacement APR/compounding controls subsequent accrual and payment allocation.
3. Disqualified/expired segments leave the upcoming-promo allocation override.
4. Assessed finance charges enter the next projected minimum exactly once.
5. Optional full-promo-horizon exposure reporting extends selected payments without inventing further payments.
6. Boundary tests, source preservation checks, reproducible demo, and archive verification accompany the changes.

## Architecture and data contracts

- The engine uses Decimal under an explicit 28-digit context; cent rounding occurs at posting.
- All schema updates reconstruct through validation. Source APRs and segment identity remain unchanged after promo exit because the frozen schema cannot represent nonzero APR on a promotional segment.
- Runtime `PromoExitResult` records supply effective replacement terms. `DebtProjection.account` contains updated balances but historical contract terms. Use the separately returned complete `checkpoint` to restart; the bare account remains insufficient. `promo_exits`, `daily_histories`, and audit entries are part of the result contract.
- Legacy callbacks retain source terms plus updated balances. `choose_decision` now receives an immutable `DebtDecisionView` with effective APR/compounding, grace eligibility, balances, capped minimum and previous payments. Exactly one callback style is required.
- `PromoTransition` requires explicit cutoff terms and sourced post-exit grace eligibility. No missed-payment penalty or disqualification trigger is guessed.
- The supported cutoff convention is end-of-day, after morning credit and daily accrual; replacement interest starts the next day. Supplied assessment is added before statement posting/minimum creation. Imported issuer timestamps need an explicit mapping.
- Deferred opening exposure must be dated the day before replay. Simple-daily and daily-compounding retroactive methods are supported. Deferred APR is independent of post-promo APR.
- Unassessed disqualification exposure is retained as a reported liability, not assumed waived. Its future contractual treatment remains unsupported without additional explicit terms.

## Grace and cash integration retained

Consecutive ordinary billing cycles carry full statement balances, subsequent credited payments, restoration streaks, and residual interest. Supported grace cycles require coincident statement close/issue dates, nonoverlapping due windows, and simple-daily eligible segments. Existing balances only; no purchase-origination event stream is implemented.

Per-account cash floors/reserves remain enforced. Transfers conserve total cash, initiated payments commit cash before bank debit, and in-flight checkpoints can resume without repeating journal effects. Explicit business-day payment timing controls credit/debit/settlement. Already initiated contributions cannot be paused. Multiple initiations sharing a credit date are now distinct timestamped events. Exact timestamp ties use explicit sequence, creditor-local dates govern dues, and all daily credits precede daily accrual.

## Exposure report semantics

`plan_promo` accepts planning-window transitions for other segments and later `exposure_transitions`. A target exiting during its own search window is rejected as an active promo constraint. Each candidate still uses deterministic simulation and event-level cash clipping. Search does not assume monotonicity; budget exhaustion is an incomplete search, not infeasibility.

`no_additional_payments_projection` extends the final selected schedule through the supplied later cutoffs. It is an explicitly named scenario, not an optimized later plan. It keeps the exact selected payments, reports any later missed minimums and assessments, and can extend beyond 90 days. It never invents extra funds or truncates the debt deadline to the cash horizon.

## Verification examples

- A $100 synthetic deferred balance with $5 opening exposure accrues $0.30 before cutoff, posts a $5.30 assessment, then accrues $1.47 at the replacement rate: final balance $106.77.
- Cutoff-day payoff waives the historical exposure and produces no subsequent charge.
- A 105-day exposure scenario confirms full-horizon accounting and exact selected-payment preservation.
- Tests cover replacement-rate allocation, removal of disqualified promo priority, assessment on statement close, debt conservation, JSON round trips, duplicate events, invalid cutoffs, and missing histories.

Run:

```sh
python -m pytest -q
python demo.py --output DEMO_RESULTS.json
python demo_promotions.py --output PROMO_DEMO_RESULTS.json
```

The session used `/private/tmp/debt-shredder-review-venv`; recreate from requirements.txt with Python 3.12+ if it disappears.

## Save/resume continuation completed

A complete end-of-day `DebtCheckpoint` now captures the original input context and mutable replay state. `resume_revolving` continues from the following day without repeating payments, assessments or decision callbacks. Pending future promo transitions and grace due dates can be supplied before the initial partial horizon. Full later cycle coverage must already be present; editing/extending contractual schedules during resume is intentionally unsupported.

Validation checks identity, history coverage, minimum-cycle coverage, original contract preservation, promo-exit coverage, grace counters, posted balance/payment reconciliation, accrued interest and unbilled assessments. Validation uses the same Decimal context and addition order as replay.

`checkpoint_io` writes versioned JSON with SHA-256 corruption detection using atomic file publication. Default saving cannot clobber an existing path; overwrite is explicit. The checksum is not an authenticity mechanism. Files are limited to 64 MiB and retain full audit/history, so this is a correctness-first persistence format rather than a compact production database.

The full-horizon exposure report now resumes the selected planning checkpoint instead of replaying the prefix. Tests establish equality with independent full replay. The saved/reloaded synthetic demo uses the effective post-promo APR and ends at $56.07 after a $50 payment, with a single assessment. Run `python demo_resume.py --directory resume-example` in a fresh directory target. Included example files live under `examples/resume`.

## September 26 longer batch completed

- `DebtCreditEvent` supports multiple credits on one day, deterministic timestamp/sequence ordering, creditor time zones, and explicit IDs. Callbacks see progressively updated balances and prior payments. Daily interest still accrues after all credits that day; intraday issuer-specific accrual is not implied.
- Checkpoints preserve credit-event identity, including zero-payment decisions, and reject duplicate/reordered event histories. Optional fields preserve legacy checkpoint compatibility.
- Promo planning now handles weekend initiations that collapse onto a common creditor-credit date, without collapsing their cash commitments.
- `portfolio.coordinate_payments` reserves caller-supplied minimum requests before extras against a shared cash ledger, preserving each source account's floor/reserves and commitment lifecycle. Explicit chronological priority resolves contention; ambiguous simultaneous priorities fail.
- Accepted requests are capped at opening posted debt capacity, replayed per account, and reconciled to cash outflows. The component reports both unfunded requests and actually missed minimum dates. It is not a portfolio optimizer.
- Tests cover reversed credit/initiation order, due-date time zones, same-day grace satisfaction, legacy checkpoint compatibility, seeded shared-cash invariants and demo outputs.

The synthetic portfolio demo preserves a $100 floor and two $50 minimum requests, then limits the extra request to $300. Run `python demo_portfolio.py --output PORTFOLIO_DEMO_RESULTS.json`.

## Next priorities and remaining scope

1. Coordinate cash/debt restart across a portfolio while preserving already accepted future requests. Individual debt and cash checkpoints exist; a single atomic portfolio checkpoint does not.
2. Add supported contractual intraday cutoff/accrual semantics, without substituting the current daily convention for an issuer rule.
3. Add loan inputs and independently verified precomputed rebate fixtures.
4. Add automatic future-minimum request generation, actual statement/import reconciliation, schedule amendments, transactional storage and UI.

Portfolio debt and cash horizons are separately reported. Required future obligations must be supplied; automatic reservations for newly generated debt minimums outside the requested debt horizon are not implemented. Do not use the 90-day cash projection label to imply complete future debt modeling.

Monthly capitalization, 30/360 period semantics, purchase-level retroactive interest, ambiguous grace windows, and pre-existing exited openings without runtime history still stop at affected boundaries. This remains a tested partial engine. No user decision or Gemini input was required for this batch.

## September 27 dashboard first slice

306 tests pass: the prior 294 plus 12 scenario/presentation cases. Added the
`dashboard` package with versioned scenario save/load, full projection validation,
atomic no-clobber persistence, duplicate-key and float protections, and an escaped
HTML report. The synthetic portfolio example now exposes reusable `scenario()`;
its original `run()` output remains unchanged. Package metadata includes the new
package and reusable demo module. Generated example inputs and HTML are under
`examples/dashboard/`. No schema or calculation-engine changes were required.

Tests verify exact input/result round trips, overwrite behavior, malformed imports,
unknown account references, cash clipping, and missed dues even when no minimum
requests were supplied. HTML rendering shows explicit demo/manual origin, cash and
debt horizons, cash protections, initiation/credit timestamps and unposted interest.
No browser interaction or visual QA was performed in this background first slice.

Remaining today's scope: friendly bounded manual-entry form, loopback server,
save/reopen workflow, integration verification and consolidated archive. See
DAY_PLAN.md; automation remains active until completion or 5 p.m. Central today.

## September 27 editable dashboard completed

324 tests pass, including 30 dashboard cases. `dashboard.manual` adapts explicit
manual inputs to the existing engine; `dashboard.forms` and `dashboard.server`
provide the loopback-only home, manual form, calculate/save and reopen workflow.
Run `python -m dashboard.server` from this directory, then open
http://127.0.0.1:8765. No server is left running by the background task.

Manual scope: one checking account, one ordinary card using simple daily interest
with no active grace, one payment, and a window ending before the next statement
close. All inputs are user-provided estimates. The form excludes future cash
activity and pending transactions, preserves additive floor/reserve protections,
and requires explicit statement/payment dates and day count. Zero payments expose
missed dues. Already-overdue openings require reconciliation and are rejected.
No assumed future minimum formula is exercised in the supported window.

The HTTP tests exercise real temporary localhost listeners and request/response
flows, including save/reopen, validation failures without writes, origin/token/host
checks and route bounds. The sandbox initially blocked binding; approved test runs
passed. No browser interaction or visual QA was performed; do not claim otherwise.
The form is intentionally a narrow first usable scenario surface, not a complete
household planner or portfolio editor. Existing read-only report commands remain.

Final dashboard checkpoint: archive hashes verified and the extracted copy also passed all 324 tests (2.84s). The bounded daytime batch is complete; pause the heartbeat. Visual browser QA remains unperformed.

## User-authorized usability batch

After the user successfully entered, saved and reopened the synthetic $200 request,
they authorized another batch focused on understanding and ease of use. Added
lossless manual input reconstruction, Adjust a copy (new file only), plain-language
result explanations, a Mac .command launcher, and concurrent request handling with
a connection timeout. No engine, frozen schema/spec or user scenario files changed.

328 tests pass. New regression tests cover edit round trips, rejected lossy edits,
original-file preservation, idle browser connections and launcher lifecycle/storage.
Browser inspection verified the user's existing synthetic report, its new explanation,
and the prefilled copy form; a screenshot confirmed the desktop form layout. No
copy was submitted in that browser inspection. The launcher passed shell syntax
and mocked lifecycle checks; actual server startup was exercised on port 8766.

The current updated preview is http://127.0.0.1:8766; the previous 8765 process
remains available. A launcher invocation chooses its own free port. No automation
was reactivated, and no future scheduled work is implied by this completed batch.
The archive excludes local_scenarios (user data) and caches.

## September 28 comparison batch

User authorized another batch while away. Added `dashboard.comparison`: exact
Decimal right-minus-left summaries, scope checks, changed input groups, escaped
HTML tables, selectors and a read-only synthetic example. GET comparison routes
accept only saved scenario IDs, reject malformed/repeated selections, and never
write. No bank connection, deployment, engine or frozen contract changes.

Comparison differences are suppressed for different account sets or cash/debt
windows. This is conservative: even an empty later cash period can suppress deltas.
Values remain independently visible. Cash totals mean cleared balances in accounts,
not in-transit money or immediately spendable funds. No globally optimal plan or
lifetime-interest savings are inferred. Subcent differences remain visible.

The report now separates clipped requested dollars from missed contractual dues
and formats times in the common creditor zone, with UTC for mixed zones.

345 tests pass, adding 17 comparison/date/status cases. Browser DOM and desktop
screenshot checks confirmed the example table. HTTP tests exercised saved choices,
read-only comparisons, invalid IDs and empty collections. No user scenario was
created, changed or deleted. The existing user example remains in local_scenarios.

The temporary Python environment no longer had pyvenv.cfg and could not import
pytest. Created project `.venv` from bundled Python and installed exact pinned
requirements after network approval. The launcher already prefers this environment.
It is durable relative to temp cleanup, but still depends on the bundled runtime.

No automation was resumed. Next user-facing step: adjust a copy of the first
manual scenario to another payment amount, then compare the two saved scenarios.
Remaining product limits are unchanged: narrow one-card entry, explicit dates,
no automatic household income/bills, no live banking, no portfolio optimization.

## September 28 guided-practice batch

User requested another autonomous batch while away. Added prefilled practice input,
inline field explanations, friendly validation labels, and a read-only input and
assumption review. Practice submissions use a separate /create-example route and
save origin=synthetic_demo. Practice copies keep this origin through the editor and
validation errors. Real entry remains blank. All writes still require the local
form token, and saved files are never overwritten.

`editable_inputs` now accepts synthetic single-card form scenarios only if a full
reconstruction with the same origin is equal to the saved scenario. Complex demo
portfolios still cannot be silently simplified into the form. Input review uses
the same lossless gate; no-payment dates are explicitly unused.

355 tests pass: 10 new practice/help/review cases. Browser testing used a separate
temporary storage directory and actually submitted the practice form, verified the
$120 applied / $30 cash / $380 posted debt / $8.22 unposted interest result, then
opened the review page. The final navigation/date changes were reloaded, and a
desktop screenshot verified the layout. No user scenario was modified or added.
The temporary browser test app is separate from the user's regular local app.

Frozen schema/spec and every engine Python file remain unchanged. No automation,
bank connection, deployment or messaging was introduced. Updated sources are ready
for the next launcher start; previously running processes do not hot-reload.

## September 28 payment-timeline batch

User authorized further work before arriving home. Added `dashboard.timeline` and
read-only /timeline/<id> plus /demo/timeline routes, linked from result pages. Cash
positions and event amounts are copied from the authoritative projection, not
recomputed in UI code. Each timestamp has one after-batch snapshot; the initial
pre-event point remains distinct. Payment events are named and explained; transfer
transit/holds, sinking reservations and atomic income/expense/reserve events retain
their ledger meanings. Unfunded requests are not represented as executed events.

Known due checks use checkpoint minimum cycle IDs and only dates within each
creditor's debt window. Cash/debt windows and absence of intraday-interest modeling
remain explicit. No new optimization or financial arithmetic was added.

368 tests pass: 13 new timeline tests cover accepted versus requested amounts,
simultaneous/start-time stages, late credit, no/unfunded payments, transfers and
reserve conservation, atomic cash events, horizon boundaries, escaping and read-only
HTTP access. Browser DOM and desktop layout checks used an isolated synthetic demo;
no user files changed. The original engine and frozen spec/schema remain unchanged.

Updated sources require a new launcher/server start; existing processes do not
hot-reload. The user can next open their saved result and choose the timeline.
No automation was resumed or deployment performed.

Final verification completed after usage resumed: extracted checkpoint passed all 368 tests in 12.29s. Final timeline wording was verified in the browser. No implementation changes were needed.

## September 28 income and bills batch

Added a bounded manual adapter for six optional dated income/expense entries,
using existing CashPlan and coordinate_payments behavior. Strict positive Decimal
whole cents, complete rows, description bounds and cash-horizon checks prevent
silent omissions. Cash dates use the supplied time zone at midnight; future income
cannot fund earlier commitments. No recurrence or reserved-cash release is inferred.
Cash plan IDs carry descriptions; lossless editor reconstruction checks the complete
scenario, including IDs, provenance, references and all lifecycle stamps. Existing
empty-cash-plan scenarios remain compatible. POST field bound increased to 80 for
six rows, retaining duplicate-field rejection, CSRF and body-size controls.

386 tests passed in 13.28s (18 new cases). An isolated browser submission added a
$40 February bill to the practice example: accepted payment $80, final cash $30,
posted debt $420, unposted interest $8.98. Saved input review and edit layout were
checked. Temporary test data stayed outside local_scenarios. Frozen schema/spec and
all engine Python files are byte-identical to the preceding checkpoint.

Next bounded batch: recurring income/bills with explicit schedule semantics and
occurrence review. UI still supports one ordinary card, one checking account and
one proposed payment. Automatic optimization and polished dashboard remain pending.
Velocity banking/PLOC support is optional future exploration, not current scope.

## September 28 recurring schedules and preview batch

User requested continued work. Added explicit once/weekly/biweekly/monthly choices,
inclusive optional stops, and required monthly short-month rules. Existing engine
scheduled_dates performs calendar expansion; no engine or frozen schema/spec edits.
No holiday/weekend adjustment or twice-monthly UI was inferred. Blank optional rows
remain compatible and are collapsed until opened; POST still fits the 80-field cap.

Scenario has optional immutable manual_cash_schedules. Loading requires exact equality
between expanded schedule terms and cash_plans. Older inputs without metadata load;
recurring files need the newer app. Lossless edit reconstructs recurrence intent and
re-expands when forecast/payment dates change. Comparison names schedule changes,
even when the concrete dates within this particular window happen to be identical.

POST preview/revise routes use the existing host/origin/token and body-size checks.
Preview writes no file, shows every occurrence and the full financial estimate;
Save revalidates submitted inputs. Example mode survives preview/revise/save.

411 tests passed in 16.78s; the 25 new recurrence tests were rerun after final preview
presentation changes. Browser verified Jan 31 / Feb 28 / Mar 31 monthly $10 bills,
$90 accepted payment and $30 ending cash, Change inputs, saving and editing a copy.
All browser test writes used isolated temporary storage. Checkpoint excludes user
scenario files and the local virtual environment. Engine/schema/spec bytes unchanged.

Next: simplify the long form into a guided setup while retaining transparent input
review. Multi-card manual entry and automatic strategy selection remain unfinished.
Do not imply that this one-card scenario tool already finds the globally best plan.

## September 30 guided setup batch

The manual, practice and copy forms now progressively show four steps: cash and
forecast dates, card/statement details, income/bills, payment and acknowledgment.
Back/Continue retain all form fields; Show all fields offers the complete form.
Local setup.js changes presentation only, never financial values or calculations.
Step controls validate visible fields, and final submission reveals any invalid
field, including one inside a collapsed income row. Server cross-field errors show
all retained inputs for correction. No drafts are stored in browser storage; reload
or closing an unsaved page can lose entries. Without JavaScript the full form and
native browser validation remain available. Preview/save behavior is unchanged.

A fixed /setup.js route serves only the packaged local asset. CSP allows same-origin
scripts; inline and external scripts remain disallowed. Package-data includes the
asset. No frozen schema, specification or engine changes. Existing saved files were
not modified. 411 existing tests passed in 16.87s; 3 added setup tests passed in
1.11s (414 total). Browser verified invalid amount blocking, all four steps,
cross-field error recovery, unchanged $120/$30 practice result, save/copy, toggling
all-fields view, and desktop layout, using isolated temporary storage.

Next useful batch: support entering multiple ordinary cards with clear per-card
statement dates and minimums, preserving shared-cash protections. Automatic strategy
selection, Actual imports and polished dashboard remain future work. Avoid claiming
this one-card UI already optimizes a complete debt portfolio.

## September 30 multiple-card entry batch

Added up to three ordinary cards to the existing guided form, sharing one physical
checking account and one cash schedule. Card 1 retains existing flat fields; optional
card_2/card_3 rows require every card/payment field and reject gaps. AdditionalCard
uses Decimal-safe types, then the existing ManualScenario validation checks each
card's cents, minimums, dates, supported terms and payment lifecycle. Forecast dates
must fit every card's supported cycle window. No frozen schema/spec or engine edits.

For multi-card scenarios only, requests marked Minimum split into min(requested,
remaining minimum) and any excess. Existing portfolio ordering reserves minimum
portions before extras. Within each kind, earlier initiation precedes later, with
Card 1/2/3 tie priorities. Zero payments create no requests. Extra-marked requests
remain extra; minimums are not automatically invented. Original single-card IDs,
requests and calculations remain unchanged. Multi-card IDs are card/card-2/card-3;
excess portions use payment[-N]-excess. Editor aggregates only when rebuilding the
complete scenario is lossless, rejecting mismatched timing or unsupported records.

Manual cash schedule validation now permits multiple debts sharing a time zone and
one checking account, still requiring exact expanded-event equality. POST bound is
140 fields (body-size, host/origin/token and duplicate-field checks unchanged).
Input review includes each card and zero-payment state; report summarizes per-card
requested/applied totals and explicitly explains split portions and shared cash.

437 tests passed in 19.07s, including 23 new cases: cash conservation, minimum-before-
excess handling, cash shortfalls, dates/terms for each card, independent due dates,
zero/below-minimum/zero-minimum/extra request round trips, incompatible lifecycle
rejection, full form transport, save/copy and existing-file preservation. Browser
entered a second card, previewed $70/$50 applied with $30 cash left, saved synthetic
data, opened its input review, and checked desktop layout in isolated temp storage.

Current limit: ordinary simple-daily/no-grace cards, a common short forecast window,
one proposed payment per card, one checking account. It is not an automatic payoff
optimizer. Next: clearer account names and bounded strategy comparisons, followed by
broader forecast support; Actual import remains optional future integration.

## October 3: finish card nicknames batch

Resumed interrupted optional nickname work. Card 1 and optional Cards 2/3 accept
names up to 60 characters. Scenario card_names is immutable optional display
metadata, validated against the debt count. Stable account IDs remain unchanged;
report/timeline labels include the ID so duplicate names remain distinguishable.
Input review and lossless editing preserve names. Names are escaped before HTML
rendering. A nickname alone cannot create an incomplete additional card.

56 targeted tests passed in 7.65s (card names, multi-card, guidance, setup, timeline),
including seven new nickname cases. Full suite was not rerun for this bounded batch;
last complete suite was 437 passing tests before nickname changes. No browser visual
check was performed this round. Frozen schema/spec and every engine Python file
remain byte-identical. User scenario files were not modified. New app is launched
separately so the user's existing preview remains available on the old process.

Next: bounded strategy comparisons using the existing deterministic engine, with
clear common-window limits; do not imply full-lifetime optimization. Actual remains
optional future import/sync, not required for standalone use.

## October 7: bounded payment-priority comparisons

Added dashboard.strategies and read-only /strategies/<id> plus /strategies-example.
Saved result pages link Compare payment priorities; home links a two-card example.
Three columns show unchanged entered plan, highest-opening-APR-first, and smallest-
opening-posted-balance-first. Alternatives allocate full remaining minimums first,
then the remaining requested budget by rank, capped at opening posted balance. Ties
use card order. Existing portfolio engine enforces cash protection, clips actual
payments and replays creditor events. Only extra request priorities are reassigned;
minimum ordering remains deterministic. No frozen spec/schema/engine changes.

Eligibility deliberately narrow: losslessly editable manual scenario, 2–3 cards,
positive explicit request on every card, identical four lifecycle timestamps across
cards, total requested budget between combined remaining minimums and opening debt.
Unsupported scenarios explain the needed change rather than inventing dates, terms,
income or extra cash. Exact checks preserve debts/openings/cash plans/debt window/cash
horizon and total requested budget. Recurring income metadata and names are retained.

UI reports per-card applied/requested, total applied, cash, posted debt, unposted
interest, interest change versus original, missed dues and whole-window cash status.
Differences use unrounded Decimal amounts, with independent display-rounding wording.
No lifetime payoff claim or globally best-plan label; no writes occur from comparisons.
Alternative plans are not yet saved or edited through this page. Custom alternative
priorities may be outside the manual editor's fixed-priority representation, so do
not add a save/edit action without explicitly addressing lossless priority handling.

Full suite: 458 passed in 20.93s, including prior seven nickname cases and fourteen
new strategy cases. Final fourteen strategy cases passed again after wording changes.
Browser DOM and desktop screenshot checked the example: same $400 requested, $120
applied and $30 cash; high-rate priority applies $70/$50, small-balance $50/$70.
Interest display was $9.55 versus $9.80, exact difference rounds independently to
$0.26. No user scenario files modified. App started detached from tool session.

Next: explicit review/save support for a selected comparison alternative, preserving
its priority semantics; then broader multi-cycle forecasts as contract inputs allow.
Actual sync remains optional future integration. No automation or reset was used.

## October 7: saved alternatives, explanations and backups

Completed three connected UI batches, preserving all engine/schema/spec bytes:

- Comparison alternatives have an explicit review page and CSRF-protected POST save.
  Server regenerates the selected candidate; a SHA-256 fingerprint binds saving to
  the exact reviewed candidate. Changed/missing sources, unknown choices, extra form
  fields and mismatched fingerprints fail without writes. Atomic new-file saving
  preserves all requests, amounts, lifecycle timestamps, origin, names, recurring
  cash schedules and custom priorities. No alternative is converted through the
  simple editor at save time. GET review never saves.
- Saved results show actual cash-reservation order: minimum group before extra group,
  then UTC initiation and explicit priority. Unsupported simple-editor plans explain
  why editing is unavailable; timeline and saved comparisons still work. The generic
  result explanation now correctly refers to saved request priorities, not card order.
- Comparison pages explain applied versus requested amounts, unfunded portions,
  missed minimums and identical per-card results above the numerical tables. These
  are deterministic descriptions, not lifetime payoff recommendations.
- Individual saved scenarios can be downloaded as validated JSON attachments. Stable
  IDs supply filenames; scenario names cannot affect headers. Downloads are no-store,
  nosniff, local-only and never mutate source files. The file includes inputs and
  priorities, not a real-payment ledger or other scenarios. In-app restoration is
  explicitly not available yet; parse_scenario round-trip tests verify the format.

Verification: full suite 478 passed in 29.75s (20 new cases). After browser-driven
wording/navigation corrections, 53 affected cases passed in 11.31s. Browser checked
comparison -> review -> save -> reopened result in isolated temporary storage; final
DOM and full-page screenshot checked after server restart. Backup content and headers
were verified through HTTP tests rather than a browser download. Original user files
were not modified. Frozen spec/schema and every engine Python file match the prior
payment-priorities archive. No automation, reset, bank connection or external write.

Next useful batch: restore downloaded scenario backups through a bounded validation
and preview flow, always saving a new file. Then consider a lossless editor for custom
request priorities before expanding multi-cycle forecasts. Do not route selected
alternatives through the current simple form: that can change their priority order.

## October 11: backup restore, review safeguards and searchable library

499 tests passed in 40.68s, including 14 restore cases and 7 library cases.

Restore: GET /restore offers a local JSON file selector with a paste fallback.
restore.js reads the selected file into a normal form; it neither parses financial
values nor sends contents until Preview. File size is capped at 4 MiB; overlapping
file reads cannot substitute an older selection. File input is progressive enhancement;
without JavaScript the paste form remains usable. The fixed script route is packaged.

POST /restore-preview validates through parse_scenario and the existing engine, then
renders the recalculated result plus exact request order. No file is written. The
canonical payload is signed using a per-server HMAC key (the form-token secret), and
POST /restore-save checks both CSRF and this signature before revalidating and saving
a fresh UUID file atomically. Restarted-server forms expire. Altered/unreviewed data,
invalid origins, malformed/duplicate JSON, oversized payloads and unsupported inputs
fail without replacing user files. Restore-specific transport allows percent-encoded
4 MiB content; ordinary form limits are unchanged. Duplicate restored copies are
allowed and described explicitly. Scenario name/origin, Decimal values, priorities,
contract data and schedules retain their original values. This is not bank import.

Library: home supports server-rendered search across scenario/card names plus all,
manual and practice filters. Search is read-only, case-insensitive and bounded; unknown
or repeated parameters fail. Listings show origin, account count and forecast dates.
Empty/no-match states and unreadable files have explicit explanations. Names and query
text are escaped. Existing saved scenarios are not modified by filters.

Browser verification used isolated practice storage: paste a backup -> preview -> save
new copy -> reopen -> search by card name. Desktop screenshot checked. File-picker
selection itself was not exercised by browser automation; the paste route was. HTTP
coverage verifies exact restored model/projection equality for custom priorities,
original-file preservation, rejected saves, limits, escaping and static script delivery.
All engine files, frozen SCHEMA.py and SPEC remain byte-identical to the prior archive.
No user scenario writes, external connections, automation or usage resets occurred.

Next: a lossless editor for saved custom-priority plans, with explicit request order
and validation. Do not silently route those plans through the simple card-order form.
Multi-cycle forecast/minimum generation remains a separate engine-focused task; no
full-payoff optimization or real-payment tracking is implied by these backup features.

## October 11 continued: exact-priority payment amount editor

509 tests passed in 41.81s (10 new editor tests). Saved results now link Adjust payment
amounts for 1–100 existing requests. The editor changes only name and positive
whole-cent amounts, reconstructing each request through validation while retaining
IDs, types, dates, priorities and all other scenario data. It does not regenerate a
manual scenario. Zero/removal/addition, date editing and priority editing are outside
this bounded UI. Existing minimum/extra portions are displayed separately.

Source fingerprint checks prevent previewing against an unexpectedly changed source.
Preview shows amount changes, before/after applied totals and missed-minimum warning.
Signed candidate payload uses the existing validated new-file save flow; original
files never overwritten. Save can preserve the reviewed candidate if the source later
changes, because the exact reviewed snapshot is signed. Both sample/manual origin
and all contract/cash schedule data are preserved.

Browser verified isolated custom-priority example: reduced first minimum 50 to 25;
total applied remained 120, distribution became 25/95 and first card missed its due.
Preview correctly warned, then saved a separate copy that reopened with edit link.
No user scenario files changed. Engine, frozen schema and spec unchanged.

MULTI_MONTH_READINESS.md records the examined implementation boundary and next engine
acceptance cases. Multi-month implementation is NOT completed: explicit future cycle
terms, newly generated minimum requests and shared-cash coordination remain needed.
Next: independently calculated multi-cycle fixtures, then explicit request-generation
policy under the frozen rolling decision-window architecture. No globally optimal
full-payoff promise, automatic bank action, or guessed issuer terms.

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
