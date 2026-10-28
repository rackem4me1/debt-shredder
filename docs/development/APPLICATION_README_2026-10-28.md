## Weekly automated-system check

Open [Weekly system check](http://127.0.0.1:8765/weekly-check) when a private
reference has been prepared. Compare historical net-pay scenarios with flexible
savings, optional housing savings and bill-account funding. What-if inputs do not
change a bank, payroll setting or saved financial record. This is a weekly budget
diagnostic, not yet a dated cash-flow forecast or a safe-extra recommendation.
Test one-time fund transfers back or direct spending, recheck the goal, and save
a separate comparison with JSON/CSV downloads. An optional take-home-pay trial
is hypothetical income. See WEEKLY_SYSTEM_CHECK.md. Earlier money snapshots retain their original facts.

## Continue your saved setup to a payoff result

Home now offers **Continue my payoff plan** for an existing personal setup. Review
its dates/payment budget, income/living costs/transfers and necessary repayment
terms, then calculate and save the payoff preview. Existing account answers are
reused. Missing facts remain visible; credit limits/APY do not block calculation.
See WIZARD_TO_PAYOFF.md. This does not invent a complete personal plan from missing
balances or unsupported loan/promotional terms.

Plan review also offers **Download complete setup backup**, keeping accounts and
planning answers together. **Restore as a separate copy** previews the backup and
creates a new setup without replacing your current one. See SETUP_BACKUPS.md.

Use **Update balances together** from plan review when figures change. Required
date/timing conflicts now link to the answer needing correction; calculated
results show the first payment round and distinguish initiation from credit dates.
See PLAN_REFRESH.md.

## Set up your accounts with the wizard

Open [Set up my accounts](http://127.0.0.1:8765/setup). Choose how many checking,
savings, credit-card and loan accounts you have, then answer one account at a time.
Unknown details can stay blank. Save and resume later; card promotional terms and
loan payment behavior are recorded separately. Continue from the setup summary to income, bills and payoff review. See
ACCOUNT_SETUP.md and WIZARD_TO_PAYOFF.md.

## Combined card and loan payoff

Open [Cards and a loan together](http://127.0.0.1:8765/mixed-payoff-example) to try a
sample monthly target shared across all debts. The screen compares two strategies
and downloads exact inputs and dated schedules. See `MIXED_PAYOFF.md` for supported
terms, recurring-transfer rules and the headless command. Your personal loan terms
have not been guessed.

## Open the app

Double-click **Open Debt Shredder.command** in this folder, or visit http://127.0.0.1:8765/ while it is running. Start with **Show me how it works**; no numbers are required. The launcher needs the existing `.venv` in this folder.

# Debt Shredder — local dashboard checkpoint

Working deterministic engine components built on the unchanged **Phase 2 revision-5 schema** and **frozen SPEC.md v2.4**. This is the first engine implementation milestone, not the finished application or full production engine.

**Validation:** 925 tests passed in107.12s full suite; browser correction, signed comparison save/reopen and JSON/CSV equivalence verified. Includes read-only weekly comparisons, balance refresh, readiness and first-round payment review. Python 3.12.14 / Pydantic 2.13.5 / pytest 8.4.2. Browser wizard calculation/save/reopen and exact exported-input replay also verified. See TEST_RESULTS.txt.

## Run

Use Python 3.12 or newer. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python demo.py --output DEMO_RESULTS.json
python demo_promotions.py --output PROMO_DEMO_RESULTS.json
python demo_resume.py --directory resume-example
python demo_portfolio.py --output PORTFOLIO_DEMO_RESULTS.json
```

`requirements.txt` records the exact tested dependency versions. No network, external budget account, bank connection, or LLM is used by the engine or demo once dependencies are installed.

## Working example

The included demo uses synthetic data:

- Checking opens at $1,000 with a $100 floor.
- Savings holds $1,500, of which $1,200 stays reserved.
- A $300 transfer moves through debit, credit, and settlement.
- Explicit future bills total $1,350; a scheduled paycheck adds $800.
- The resulting 90-day safe immediate payment is **$650** under those inputs. Transfer principal contributes **zero** external income or expense.
- A separate card example allocates a $125 payment as $25 toward the minimum on the lower-rate balance and $100 of excess toward the higher-rate balance.
- A scalar search with event limits of $50 and $150 finds a **$110** candidate to deliver $160 total: actual payments are $50 and $110.

The JSON includes transaction audit entries, cash positions, statuses, allocation lines, and search results. These examples are not recommendations for a real user's accounts.

## Modules

| Module | Implemented behavior |
| --- | --- |
| `engine/common.py` | Explicit 28-digit Decimal context, finite-value checks, contractual cent posting modes, provenance labels, validated immutable replacement |
| `engine/promotions.py` | Explicit expiration/disqualification assessment, deferred exposure through full cutoff, payoff waiver, posted assessment and runtime replacement terms |
| `engine/grace.py` | Statement-history grace resolution, consecutive full-payment restoration, pending state, duplicate-credit and history validation |
| `engine/interest.py` | Unrounded simple-daily/daily-compounding accrual; actual/365, actual/366, actual/actual; deferred exposure from complete daily balances; contingent grace delta |
| `engine/allocation.py` | Billed minimum cap, projected minimum formula, minimum/excess waterfall, complete-cycle promo override, directed excess, pro-rata cent apportionment, configured custom waterfall |
| `engine/loans.py` | Note-rate simple-interest accrual, fees → posted interest → principal, explicit paid-ahead date input, posting adjustment audit |
| `engine/liquidity.py` | Immutable planned events, commitment/debit separation, transit conservation, settlement holds, account-local reserves/floors, 90-day event projection, graded breaches, contribution-pause comparison, validated in-flight checkpoints and resumption |
| `engine/schedules.py` | Explicit income/bill/contribution expansion, weekly/biweekly/monthly/semimonthly dates, short-month handling, no loss of coincident nominal payments |
| `engine/portfolio.py` | Explicit multi-account request coordination, shared-cash limits, minimum-request reservation, clipping and per-account replay |
| `engine/checkpoint_io.py` | Validated debt checkpoint save/load, atomic publication, checksum verification, explicit overwrite control |
| `engine/timing.py` | Sourced business-day payment delays, named time zone, explicit holidays, credit/debit/settlement ordering |
| `engine/search.py` | Cent-bounded bisection for a declared monotone family; bounded grid with exact cent verification otherwise; explicit evaluation-budget failure |
| `engine/simulation.py` | Daily revolving replay, grace transitions, once-only promo assessment, post-exit interest, minimum tracking, integrated promo search and full-horizon exposure scenario |

## Integration boundaries

Inputs must describe a complete, reconciled opening and the planned financial events. Omitted bills are not inferred. The snapshot adapter rejects unresolved pending aggregates/in-flight actual transactions instead of silently ignoring or double-counting them.

`project_liquidity` counts unscheduled secondary liquidity only for eligible accounts with a verified zero-day route. Delayed transfers require explicit lifecycle plans. `plan_promo` is more conservative: **all secondary-account funding requires a scheduled transfer**, including zero-day routes. It does not execute automatic transfers.

The integrated promo path accepts `PaymentTiming` with explicit business-day creditor-credit, bank-debit, and settlement delays, a named time zone, and supplied holidays. The buffered deadline is checked against creditor credit. If timing is omitted, **same-day timing at 12:00 UTC is an assumed default**. Multiple initiations sharing a credit date now remain separate identified events, including separate cash commitments. Results remain estimates. The caller must supply all cash events through the last candidate date plus 90 days, and must not duplicate generated target-account payments as external obligations.

`reconcile_at` creates a validated cash-ledger checkpoint from supplied lifecycle events. Resuming includes only remaining events and preserves commitments, settlement holds, and transit cash. This is deterministic journal replay; matching bank statements or importing actual transactions is still future work.

Custom allocation uses account-aware readiness. Equal APR fallback ties use stable segment IDs and are treated as an assumed detail. Pro-rata cent remainders use largest fractional remainder, then stable ID. Posted balances/minimums must be whole cents; unposted interest retains full precision.

## Still to implement

- Extend grace integration to overlapping statement due windows, separate statement issue dates, and non-simple-daily purchase terms. Consecutive ordinary billing cycles now carry generated statement balances, credits, and restoration streaks.
- Automatic mapping of contractual disqualification triggers, imported timestamp rules, and reconciliation of already expired/disqualified openings. Explicit supplied exits and full-horizon exposure scenarios are implemented.
- Precomputed-loan rebate calculations, which need origination/finance-charge/term/rebate inputs beyond the present schema labels.
- Contractual 30/360 and monthly-capitalization semantics, purchase-level retroactive sums, and any issuer behavior outside the supported allocation rule formats.
- Portfolio optimization/automatic request generation, coordinated portfolio restart, intraday issuer-specific accrual, bank-statement reconciliation and transactional database storage, import/export adapters, and application UI. Explicit multi-account requests can now share a cash ledger. Local debt checkpoint files are implemented.

Unsupported/missing contract inputs raise `UnsupportedTerms` or `MissingTerms`. Exhausted search raises `SearchBudgetExceeded`; it does not claim the debt is impossible to pay. See `HANDOFF.md` for the next implementation step.

## Explicit grace replay inputs

`simulate_revolving(..., grace_terms=GraceReplayTerms(...))` supports consecutive due-date transitions with nonoverlapping statement windows. Supply the original opening statement, only pre-replay credits, the last resolved grace state/restoration streak, and an explicit contingent opening amount for every eligible segment through the day before replay. These amounts must come from reconciled historical balances; current principal alone cannot establish them. Simulated creditor credits are appended exactly once.

Daily order is morning credit, daily accrual, end-of-day grace resolution, supplied promo-exit assessment, statement posting, then minimum compliance. Loss transfers the accumulated contingent amount to unposted accrual without intermediate rounding; normal statement posting performs rounding. Restoration changes subsequent eligibility without deleting already accrued interest. At each subsequent close, the posted account balance becomes the new full statement balance. Credits after that close count toward its due date; earlier credits are already reflected in its balance. The integration rejects overlapping due windows, differing close/issue dates, and non-simple-daily eligible segments. New purchases are not generated by this replay. Results remain estimates. Promo search accepts the same optional `grace_terms` input and independently replays it for each candidate. Missing history still raises an error where required; it is never inferred from the candidate or current principal. Feasibility means promo payoff with minimum compliance and cash constraints; it does not promise to preserve purchase grace.

## Promotional exit assessment

`assess_promo_exit` accepts a segment, complete consecutive post-credit daily balances, and explicit end-of-day exit terms. Deferred opening exposure must be dated immediately before that history. Simple daily and daily compounding use the deferred APR independently of the post-promo APR; only assessment is rounded. True-zero promotions receive no retroactive charge. Disqualification requires explicit replacement rate, compounding and assessment policy; a missed payment does not invent those terms. Unassessed disqualification exposure is retained separately, not assumed waived.

Daily simulation accepts explicit `promo_transitions`. Each transition includes exit terms and sourced post-exit grace eligibility. It collects post-credit daily balances, assesses once at the cutoff, adds the posted charge before statement minimum calculation, and applies replacement APR/compounding from the next day. Allocation uses replacement APRs for minimum/excess waterfalls and removes exited segments from promo priority. Monthly capitalization and purchase-level retroactive methods still require additional inputs and stop explicitly.

The approved schema forces promotional APR to zero. Its fields remain historical contract terms; runtime replacement terms are returned in `DebtProjection.promo_exits`. The returned `account` alone is **not** a resumable post-exit snapshot. Legacy payment callbacks receive updated balances with source terms. New strategies can use `choose_decision` instead, receiving immutable effective APR/compounding, grace eligibility, current balances, capped minimum, and previous payments. Outputs also include `daily_histories` and the charge audit. Exact issuer timestamps must be mapped explicitly to the supported end-of-day cutoff/next-day reversion convention.

## Full-horizon exposure scenario

`plan_promo(..., exposure_transitions=(...))` extends the selected payment schedule through supplied later cutoffs, assuming **no additional payments**. The separately named `no_additional_payments_projection` reports charges or waivers and any later missed minimums. It resumes the selected checkpoint without repeating historical decisions. It does not change candidate selection, claim that later payments cannot be made, or silently recommend this scenario. Its debt horizon can exceed the 90-day cash window. Missing required transitions for other crossed promos still stop the calculation.

A target exiting during the search window is rejected as an active-promo planning request; direct debt replay can model its exit. An explicit disqualification with no immediate assessment retains its unassessed exposure in the result rather than assuming waiver. Subsequent contractual treatment of that retained liability is not inferred.

## Reproducible transition example

`demo_promotions.py` uses synthetic contract inputs. An unpaid $100 deferred promo has $5 of reconciled opening exposure and three more days at a 36.5% deferred APR. The $5.30 assessment posts once. Twenty-eight days at an 18.25% replacement APR add $1.47 at statement posting, giving **$106.77**. Paying $100 on the cutoff date instead waives $5.20 of accumulated exposure and leaves zero. See `PROMO_DEMO_RESULTS.json` for results and audit entries.

## Save and resume debt replay

Every `DebtProjection` now includes a complete `checkpoint` for the supported replay: original terms, current balances/accruals, effective promo exits, pending transitions, per-cycle minimums, active statement credits, grace shadow/streak, unbilled assessments, and cumulative history. `resume_revolving(checkpoint, end, new_payment_dates, ...)` starts the following day and invokes callbacks only for new payment dates. The result retains cumulative history.

Use `save_debt_checkpoint(checkpoint, path)` and `load_debt_checkpoint(path)` from `engine.checkpoint_io`. Files are atomically published, protected against accidental overwrites by default, checked for accidental corruption, and revalidated on load. Checksums are not authentication or encryption. Format version 1 has a 64 MiB limit. `overwrite=True` explicitly replaces an existing file.

Checkpoints are end-of-day states, not intraday banking snapshots. Supply the full billing calendar and future transition terms before the initial replay; this version does not append or revise contractual schedules during resume. Bare legacy account records still cannot reconstruct expired promo history. Restart tests compare full results—including audit entries, interest, payments, grace decisions and resulting checkpoints—against uninterrupted replay at cutoff, due-date, payment and close boundaries.

`demo_resume.py --directory resume-example` writes a synthetic checkpoint and result to a new directory. It resumes after promo cutoff, makes a $50 payment using the effective 18.25% APR, and reaches $56.07 with exactly one assessment. The included `examples/resume` contains a generated checkpoint and result for inspection; choose a new output directory when running the demo.

## Same-day creditor credits

`DebtCreditEvent` records a unique ID, aware creditor-credit timestamp, and sequence for resolving exact timestamp ties. Supply events in unambiguous chronological order, `credit_timezone`, and a `choose_decision` callback with empty legacy payment dates. The decision view includes event identity and timestamp. Payments on a common day apply sequentially; **all that day's credits precede its daily accrual and end-of-day contract events**. This is an explicit daily balance convention, not an implementation of issuer-specific intraday interest or cutoff clocks. The creditor time zone determines the statement due date.

Checkpoints retain processed event IDs even when the callback returns zero. Resume rejects reused IDs and historical dates. Legacy date-only inputs and older checkpoints without the new optional event fields remain supported. Promo planning uses explicit events when weekend/business-day timing causes credit-date collisions.

## Shared-cash request coordination

`coordinate_payments` in `engine.portfolio` accepts revolving debt inputs, one physical cash ledger, external cash plans and explicit payment requests. It reserves supplied `MINIMUM` requests before `EXTRA` requests. Each group follows initiation time and caller-specified priority; ambiguous simultaneous priorities are rejected. Cash is committed at initiation, not deferred until creditor credit or bank debit. Account-specific floors and reserves remain protected.

This is a deterministic request allocator, **not an automatically generated or globally optimized payoff plan**. Each account's accepted total is conservatively capped at its opening posted balance; later generated interest does not create additional spending authority. Actual debt application must match the accepted cash commitment. Requests cannot also appear as debt payments in base cash plans. Transfers must be explicit.

Results separately report request shortfalls, simulated missed due dates, debt horizon and cash horizon. `all_minimum_requests_funded` means all supplied minimum requests were funded; it does not establish that every contractual obligation was supplied. Debt replay covers the requested debt horizon; the cash lookahead extends at least 90 days from the last initiation. Callers must supply the obligations needed for those horizons. Newly generated future debt minimums beyond the debt horizon are not automatically reserved.

`demo_portfolio.py` reserves two $50 minimum requests from $500 checking with a $100 floor, then clips a $500 extra request to $300. Checking ends at $100; debt balances are $150 and $450. These are synthetic zero-rate accounts.

## Local dashboard — first slice (September 27)

A read-only local report is available at `examples/dashboard/shared-cash.html`.
It shows a synthetic two-card scenario, protects the $100 checking floor, and
reserves both $50 minimum requests before accepting $300 of the extra request.
Posted debt and unposted interest appear separately. Cash and debt windows are
explicit: a longer cash window does not imply future debt minimums were supplied.

From this project directory, generate a new report and save its scenario inputs:

```sh
python -m dashboard --output my-report.html --save-inputs my-scenario.json
python -m dashboard --scenario my-scenario.json --output reopened-report.html
```

Open the HTML file locally. Outputs must be new paths; the CLI never silently
overwrites them. The scenario JSON is a versioned input document, not an actual
ledger or a restart checkpoint. Loading/saving validates it through the existing
engine. The editable local app described below builds on this report. No bank connection or hosting is involved.

## Editable local app

From the project directory, start the local app:

```sh
python -m dashboard.server
```

Then open `http://127.0.0.1:8765` on the Mac. Select **Create a manual scenario**,
enter the explicit inputs, and choose **Calculate and save a new scenario**.
Saved scenarios appear on the home page. Every submission creates a separate file
under `local_scenarios/`; reopening never overwrites the original. Stop the app
with Control-C. Optional `--port` and `--data-dir` select another local port or
storage folder. The listener is always loopback-only, with no external assets.

The manual form is intentionally limited to one checking account, one ordinary
card balance with simple daily interest and no active grace, and one requested
payment. Enter zero to model no payment. Choose the day-count rule and provide
statement, due, initiation, creditor-credit, bank-debit, and settlement dates.
Dates use midnight in the chosen time zone; creditor credit must precede or
coincide with bank debit. The forecast must end before the next statement close,
so no assumed future minimum formula or posting rule is exercised. All manual
inputs are marked estimates. Do not use this form for promotional balances,
active grace, daily compounding, or accounts with pending transactions.

No future cash activity is included in this first form. Floors and reserves are
separate and additive. The report exposes unpaid requests and missed minimums,
including when a zero payment leaves a minimum unpaid. It is a bounded scenario,
not a complete household budget or an automated payment plan. The two-card
synthetic example remains available from the home page.

Phone check-ins use the desktop app's Remote connection; this local web server
is not exposed to the phone or the internet.

## Easier use: saved copies and Mac launcher

Double-click `Open Debt Shredder.command` in Finder to start the local app and open
a browser. Keep its Terminal window open; Control-C stops it. The launcher selects
a free loopback port and keeps scenarios in this project's `local_scenarios` folder,
regardless of where it was launched. It uses an existing project `.venv` or the
current development environment; it installs nothing. If that environment is later
removed, it displays a recovery message instead of altering saved scenarios.
This is a launcher script, not yet a self-contained Mac application.

Open a saved manual scenario and choose **Adjust a copy**. The form is filled with
your saved inputs; calculating creates a new file. The original is untouched. A
lossless round-trip check prevents the simple editor from silently dropping inputs
it cannot represent. Zero-payment scenarios have no payment timing to restore, so
the unused date fields are set to the forecast start.

Single-account reports now lead with **What this means**, explaining the proposed
payment, cash protections, remaining cash and interest awaiting statement posting.
The local server handles simultaneous connections so an idle browser connection
does not block another tab. Its listener remains loopback-only.

## Compare saved scenarios (September 28)

Choose **Compare saved scenarios** on the home page, or **Compare with another
scenario** on a saved report. Select a starting scenario and a second saved
scenario. The table shows payments requested/applied, unfunded amounts, cash left,
protected/reserved/committed cash, posted debt and interest awaiting posting.
The right-minus-left column describes amounts; it does not recommend a winner.
Comparison never creates or changes scenario files.

If the debt or cash windows differ, or the account sets differ, numeric differences
are hidden with an explanation. Ending values and both windows remain visible.
Changed input groups are listed so a change in balances or terms is not silently
attributed to a payment change. Comparisons of synthetic and manual inputs are
labeled. Tiny nonzero interest differences display as less than one cent instead
of zero. The read-only example comparison requires no saved files.

Dates now display in the common creditor time zone, or UTC when creditors differ.
The report separately describes unfunded requested dollars and actually missed
minimum dates. It no longer calls a clipped request an unfunded minimum when the
contractual minimum was nevertheless met.

The project now has its own `.venv` with the exact requirements installed; the Mac
launcher prefers it. The old temporary environment had lost its configuration.
The project environment still depends on the bundled Python runtime and is not
a standalone application bundle. Archives exclude `.venv` and your saved scenarios.

## Learn with practice data and review assumptions

Choose **Practice with sample numbers** on the home page to open a prefilled
example. Its January 2026 dates and financial figures are deliberately made up.
Calculating saves an example, and **Adjust a copy** keeps the example label on
subsequent copies. The real-data form stays blank; sample figures never become
real-account defaults. Practice still requires acknowledgment of the limited scope.

Field help explains cleared cash, separate floor/reserve protections, the difference
between posted and unposted interest, and all four payment dates. Errors use the
visible field labels. Unknown real values should not be filled with guessed zeros.

On a supported saved scenario, **Review inputs and assumptions** opens a read-only
summary of the entered amounts, dates, day-count rule, payment type and supported
calculation conventions. **Back to result** returns to its report. Zero-payment
scenarios show unused dates as not used, rather than inventing meaningful timing.
Scenarios outside the simple form's lossless representation are not silently
simplified; their original reports remain available.

## See when the money moves

Choose **See the payment timeline** from a saved result or the shared-cash demo.
The timeline explains submission, card credit, bank debit and settlement separately.
It displays the accepted amount at each stage; these are stages of one payment,
not additional payments. Unfunded requested dollars have no fabricated lifecycle.

Cash snapshots come directly from the engine, including commitments, holds, reserves,
floors and money in transit. Simultaneous events share one after-batch cash snapshot.
The opening snapshot is before start-time events, even when timestamps are equal.
Known minimum due dates are reported only within the debt forecast. The cash forecast
may be longer and does not imply that future minimums have been supplied.

Transfers remain internal cash movements, not income/expense. The timeline also
recognizes supplied income, expenses and reserve allocations. The manual form now
accepts dated income and expenses as described below. No hourly interest semantics or
new financial rules were introduced. Above-protection balances are snapshots, not
recommendations to make additional payments.

## Add upcoming income and bills

The manual and practice forms accept up to six optional income/bill schedules.
Each needs a description, positive whole-cent amount, type and cash date. Income
uses its cleared availability date; a bill uses its bank withdrawal date. Blank rows
are ignored, partial rows rejected, and dates outside the engine cash window are
rejected rather than silently excluded. Recurrence is explicit, as described below.
No transfers, card purchases or reserve releases are inferred.

Include known activity through the cash window (at least 90 days, extended by
payment initiation/settlement). All events use local midnight, with same-day activity
modeled together. Do not count the planned card payment again as a bill. Opening
cash precedes first-day events. Reserved cash stays protected after expenses;
this form cannot represent spending down an earmarked reserve.

Later income cannot fund an earlier payment. Bills beyond the debt window but inside
the cash window still constrain payments. Input review, timeline and lossless editing
preserve the entries. Existing scenarios remain compatible. Next: a simpler guided
interface; automatic plan selection remains separate unfinished work. Optional credit-line strategies are deferred.

## Recurring cash activity and preview before saving

Each cash row now supports Once, Every week, Every two weeks, or Every month.
The cash date is the first occurrence and must be inside the cash forecast. An
optional inclusive stop date can end the schedule early; no occurrence after the
forecast horizon is included, even if the stop date is later. Monthly schedules
repeat on the first occurrence's day number and require explicit short-month
handling: last day of that month or first day of the next month. Local midnight
is preserved across daylight-saving changes. Weekends and holidays do not shift
cash dates. Twice-monthly and irregular repeating schedules are not supported by
this form yet; do not substitute every two weeks for twice monthly.

Preview dates and payment shows every occurrence in chronological order and the
existing engine's financial estimate. Nothing is saved until Save this scenario.
Change inputs retains all entries and the example/manual designation. Empty cash
rows remain collapsed, reducing clutter. Input review also displays the schedule
terms and concrete dates, and comparison identifies changed schedule settings.

Optional manual_cash_schedules in the scenario envelope preserves recurrence intent
for editing; SCHEMA.py is unchanged. On loading, those terms must reproduce every
cash plan exactly (amount, identity, provenance, account routing and timestamps).
Old files without this field still load. Recurring files require this newer app;
older builds may reject the added envelope field. Pure one-off cash plan IDs remain
unchanged. Editing payment timing regenerates occurrences through the new horizon.

Validation: 411 full-suite tests passed in 16.78s; 25 focused recurrence tests passed
after the final preview layout/comparison assertion changes. Browser checks covered
monthly February handling, preview, Change inputs, save, and editing the saved copy.
All browser writes used temporary storage, not the user's scenarios.

## Guided setup

Create a manual scenario, practice, or adjust a saved copy using four steps:
Your cash → Your card → Income and bills → Your payment. Back keeps your entries;
Continue checks the current step. Show all fields switches to the full form without
losing values. Errors found during preview retain your data and reveal all fields
for correction. Preview still shows exact dates and estimates before a separate save.

The steps use a small local script with no financial calculations or browser storage.
They do not save drafts: finish preview/save before closing or reloading the page.
If scripts are unavailable, the complete form still works. This batch changes setup
presentation only; multi-card entry and automatic strategy selection are still pending.

Verification: 411 existing tests plus 3 new setup cases passed. Browser checks covered
navigation, invalid amounts, error recovery, view switching, preview, save and copy.

## Multiple cards sharing checking

The guided form now supports Card 1 plus optional Cards 2 and 3. Each has its own
balance, APR/day count, statement dates, minimum and proposed payment dates/amount.
Fill all fields for an included card, or leave the whole card blank. Use payment 0
for an included card you do not intend to pay. Cards share forecast dates, time zone,
checking cash, protections and income/bills. The forecast must fit every card's
supported statement window. Do not omit a real debt when interpreting cash capacity.

In multi-card scenarios, a Minimum request is split into its required-minimum portion
and excess. Minimum portions reserve cash before extras; earlier initiation dates
come first within each group, with Card 1 then Card 2 then Card 3 breaking ties.
An Extra request stays extra. Missing or too-small requests do not silently become
full minimum payments. Shortfalls and missed due dates remain visible. This order
is explicit and deterministic, not a recommendation that it is the best strategy.

Preview and report show total requested/applied per card. Detailed minimum/excess
rows are portions of the same proposed payment, not additional payments. Input
review and Adjust a copy preserve all supported card inputs. Existing single-card
saved scenarios continue to open unchanged. Bank sync and automatic strategy
selection are not included in this batch.

## Card nicknames

Add an optional nickname for each card to recognize it in results, input review,
and the payment timeline. Names remain attached when you save or adjust a copy.
Stable account IDs remain visible alongside names to distinguish duplicate names.
Names affect display only; they do not change payment priorities or calculations.
Old unnamed scenarios remain compatible. This batch passed 56 targeted tests;
the preceding complete suite passed 437 tests before nickname changes.

## Compare payment priorities automatically

On a saved result, choose **Compare payment priorities**, or choose **Try payment
priorities** on the home page. The page generates highest-interest-first and
smallest-balance-first alternatives alongside the unchanged entered plan. It shows
requested and applied payments, cash left, posted debt, unposted interest, and missed
minimum dates, with per-card amounts and nicknames.

For a fair bounded comparison, use two or three supported cards with positive
proposed payments and identical initiation/credit/debit/settlement dates. The total
requested budget must cover remaining minimums and not exceed opening posted debt.
Alternatives keep that budget, all dates, terms, cash activity and protections fixed;
they request remaining minimums first and distribute extra requested dollars by the
chosen priority. Engine cash constraints can reduce what is actually applied.
Unsupported inputs get an explanation; they are never silently simplified.

This compares one payment round within the supplied forecast, not the whole payoff.
It neither identifies a globally best plan nor moves money. Viewing comparisons never saves a file;
use Review beside an alternative to save it as a separate scenario after reviewing its exact payment order. Amounts and interest differences
are independently rounded from exact estimates. No personal data is needed for the
built-in example. All 458 tests passed, followed by browser example verification.

## Save an alternative and keep a backup

Choose **Review Highest interest first** or **Review Smallest balance first**, then
**Save as a separate scenario**. The review shows the exact request order and resulting
estimate. Saving preserves that priority order and leaves the original unchanged.
If the source changed after review, review again before saving. Alternatives whose
priority order the simple editor cannot preserve remain viewable but are not editable
there. Results and the payment timeline remain available.

Every saved result includes **Download scenario backup**, a JSON file containing that
scenario's inputs and exact payment requests. It contains any financial information
you entered; keep it locally where you can find it. This is not a backup of all saved
scenarios, nor a real-payment ledger. Use **Restore a backup** on the home page to preview and save a separate copy.

Current verification: 478 tests passed; 53 affected tests passed again after final
presentation changes. Isolated browser save/reopen flow and desktop layout checked.

## Restore and find saved scenarios

Choose **Restore a backup** on the home page, select your downloaded JSON file, then
choose **Preview restored scenario**. Review its recalculated results and payment
request order before choosing **Save restored copy**. Existing files are never
replaced. The backup name, input values and priorities are preserved; restoring the
same file twice creates two separate copies. A paste fallback works without JavaScript.
The size limit is 4 MiB. This restores a what-if, not actual bank transactions.

Search the home page by scenario or card name. Use **Show** to select manual estimates
or practice examples; **Clear search** returns to all scenarios. Each entry shows its
forecast dates so older estimates are easier to recognize.

October 11 verification: 499 tests passed, with isolated browser restore/save/reopen
and card-name search checked. Frozen schema, spec and calculation engine unchanged.

## Adjust payments on a saved strategy

Choose **Adjust payment amounts** on a saved result. Change existing positive
whole-cent amounts, preview the differences, then **Save payment changes as a copy**.
This preserves the exact request order, dates, account terms and cash activity.
Minimum and extra portions are separate. Review missed-minimum warnings before
keeping a reduced payment. This editor does not add/remove requests or change dates.
509 tests passed; isolated browser preview/save/reopen verified.

## Three-statement practice forecast

Choose **See a three-statement forecast** from the home page. The synthetic example
shows interest posting, statement balances and new minimums for three months. A
separate minimum-only forecast generates requests from each new unpaid minimum at
supplied payment dates, subject to cash protections. Different payment totals are
explicitly identified; this is not a same-budget strategy comparison.

This first forecasting component supports one ordinary simple-daily card without
active grace/promotions, explicit matching minimum formula terms and explicit dates.
It is not connected to personal manual entry yet and does not choose extra payments,
coordinate future minimums across several cards or calculate a full payoff plan.

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

## My Money

When a starting picture is saved locally, choose **Open My Money** on the home page.
It displays dated reported balances and expected paycheck, separate from hypothetical
plans. Updates retain prior values locally. This screen does not calculate an extra
payment or automatically apply changes to saved scenarios.

## Bills linked to My Money

Choose **See my bills** on My Money. The draft separates Bills Box, checking and card
charges, shows the next five cash bills first, and supports reviewing one occurrence
at a time. Estimated dates/status remain visible. This calendar does not yet compute
a running bank balance or an extra-payment amount.

## Cash before payday

From My Money or Bills, choose **See cash before payday**. The dated conditional view
shows direct cash bills before the expected paycheck, separate checking/Bills Box
balances and a food/fuel cushion held in checking. Adjust cushions or save the draft
for later; saved drafts retain original inputs even after current figures change.
Payday funding/transfers, unresolved bills and debt interest remain outside this view.
It does not give an extra-payment recommendation.

## Payday and the following week

Choose **See payday and the following week** in My Money or the cash view. The draft
shows one expected paycheck, Bills Box funding, a KC transfer or protected hold, cash
bills and spending cushions through the following six days. It compares deposit-first
with payday-bills-first timing, supports assumed arrival delays and saves exact drafts.
KC balance/date can stay unknown; its transfer is held in checking until both are
supplied for the same starting date. Estimates and unresolved items remain visible.
No bank transactions or extra-payment recommendations are performed.

## Full payoff calculation in a saved plan

Open a saved plan, enter the **total payment target for each date across all cards**,
and choose **Calculate both payoff plans**. The existing plan page shows both
strategies, payoff dates when reached, interest, remaining debt and dated payments.
The preview uses the standalone payoff engine; original requests are kept separately.
It does not change or save the source plan. Unsupported terms are explained. Dates
and cash events are used exactly as saved; short date ranges may not reach payoff.

The standalone command and JSON/CSV exports are documented in PAYOFF_PLANNER.md.

## Repeating payoff calendars and saved runs

In a saved plan, open **Repeat a longer payoff calendar** to declare payment
frequency, first/end dates, short-month handling and lifecycle delays. Saved
recurring income/bill rules expand once with their stop dates; no recurrence is
invented for dated one-off cash. Future statement dates and constant future terms
remain explicit estimates. The form stops if the pattern conflicts with saved
statement dates. **Save this payoff run** keeps the reviewed starting snapshot and
exact calendar. Reopen saved runs from home; download dated CSVs or exact JSON for
the standalone calculator. See PAYOFF_CALENDAR.md for scope and commands.

## Separate funding accounts and simple-interest loans

Card payoff inputs now retain individual checking/savings floors and reserves,
explicit per-debt funding routes and timed internal transfers. Payment schedules
show **Paid from**; transfers never count as income or expenses. Weekly payments
are judged against minimum due dates rather than requiring the full minimum at
every weekly opportunity.

A separate simple-interest loan calculation now uses the existing loan accrual and
fees → interest → principal waterfall. Try `/loan-payoff-example` or run
`payoff_cli.py --loan-demo`. For a shared card/loan budget, use the new
`payoff_cli.py --mixed-demo` or `/mixed-payoff-example` (see MIXED_PAYOFF.md).
Paid-ahead and precomputed contracts remain blocked pending real schedules. See
PAYOFF_FUNDING_AND_LOANS.md for inputs and limitations.
