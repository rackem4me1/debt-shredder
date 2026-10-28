# Keep and restore a complete setup

From plan review choose **Download complete setup backup**. It contains the
account entries and partial forecast settings, repayment terms, income, bills and
transfers for that setup. Keep this private JSON file locally. It does not include
other setups, edit histories, calculated runs, legacy My Money/bill records, bank
transactions or a record of completed payments.

Choose **Restore as a separate copy** (also available from saved setups), select
the file or paste its contents, then choose **Preview setup backup**. Review the
account/plan summary or expand **Review all saved fields**. Nothing is saved until
**Save restored setup as a new copy**. Restoring always uses a new ID; it cannot
replace an existing setup. Check dates and future bills again before calculating.

Incomplete answers, explicit zero, unknown values, personal/practice origin and
review states are preserved. Opening old data does not refresh it, mark bills paid,
add received income or certify that its contractual assumptions are correct. A
complete file is a complete snapshot of entered fields, not proof that every field
has been answered.

The complete format is debt-shredder-complete-setup, integer version1, maximum
1 MiB. Duplicate JSON keys, numeric floats/nonfinite values, extra fields, wrong
formats and boolean/floating version markers are rejected. Accounts and planning
retain their existing size and schema limits.

The older **Download accounts-only backup** from the inventory summary remains
available but is not accepted by this complete restore flow. What-if scenario
backups use the existing scenario restore page. Calculated-run input exports are
calculation snapshots rather than editable setup backups.

Restore follows the app's Host/Origin/CSRF and exact-field protections. A signature
binds the save to its preview. Publication uses a new ID, saves planning first,
and publishes inventory last; failed unpublished planning is cleaned up. The
complete download captures both records under the setup lock. No engine calculation
is performed during backup or restore.

Verified:839 tests passed in100.83s full suite. Browser preview/save/reopen used
synthetic data only. Restored engine input JSON matched the original byte for byte.
Original personal financial records, engine modules, schema and frozen spec stayed
unchanged.
