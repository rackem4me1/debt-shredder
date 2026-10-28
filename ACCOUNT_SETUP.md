# Guided account setup

Open `/setup` or choose **Set up my accounts** from home. The wizard asks how many
checking accounts, savings accounts, credit cards and loans the user has, then
presents one account at a time. It supports up to 20 bank accounts in total, 20
cards and 20 loans as an inventory; this does not expand the payoff engine's limits.

Bank questions cover nickname, balance, original reporting date, optional interest
APY, cash cushion and other reserved money. Card questions add purchase APR, credit
limit, unpaid minimum, due date, paying bank account, autopay and promotional terms.
Promotion options distinguish ordinary 0%, deferred interest and other offers;
amount, promotional APR, end date and post-promotion APR are retained when known.
Loan questions distinguish disclosed APR from contractual note rate, principal from
lender total, simple from precomputed interest, and principal curtailment from
paid-ahead/rebate behavior. Notes retain other offers and lender wording.

Only the account nickname is required on account pages. Blank numeric values stay
unknown; explicit zero stays zero. Dates are not advanced when reopening a setup.
Overdraft bank balances and over-limit cards are retained as reported facts; an
over-limit card is flagged. Financial values reject floats, nonfinite values,
negative rates and fractional-cent balances/payments. No arbitrary APR ceiling is
invented. Contradictory promo details and unknown bank references fail validation.

**Save and next**, **Save and back**, and **Save and finish later** persist the
current account. The saved summary can resume the exact account or review any
account separately. Add-account buttons preserve existing IDs and payment routes.
The summary lists unknown and unsupported details without calling an account ready
for calculation. The summary downloads inventory-only JSON. Plan review downloads a complete
setup backup and can restore that complete format as a separate copy.

Optional reuse copies matching figures already present in My Money, without
altering that source file. Checking/Bills Box balances retain their original date.
The historical card figure has no refreshed balance date and stays explicitly
unconfirmed. No APR, promotion status, autopay clearance or new income is inferred.
The feature does not assume that other named savings goals are distinct physical
accounts. New personal counts and account classifications come from the user.

A separate practice button creates a labeled practice setup without reusing private
figures. Browser verification uses only that practice setup.

Persistence lives under private `local_scenarios/account_wizards/`. Each update is
validated and written atomically. The previous content is retained by digest under
`history/`; a per-server lock and stale-fingerprint check prevent an old browser tab
from overwriting a newer answer. Bad local files are kept and reported. Host,
Origin, CSRF, exact-field, size and JSON-version protections apply; text is HTML
escaped. No external service, bank action or browser storage is used.

The account inventory now connects to a planning review at `/setup/<id>/plan`.
Required settings, declared cash flow and supported calculation terms can be saved
and converted directly into an engine payoff preview and signed saved result.
Unknown/unsupported facts remain blocked. See WIZARD_TO_PAYOFF.md for the complete
workflow and limitations. Inventory-only backups remain separate. Complete setup backups now include the
planning sidecar and have a preview/restore UI; see SETUP_BACKUPS.md. Calculated
results export complete engine inputs.

Frozen source schema, specification and every existing engine module are unchanged.
