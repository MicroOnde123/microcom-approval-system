# General Permission resubmission

Only the configured administrative request type (`ADMINISTRATION_REPORT_REQUEST_TYPE_CODE`,
default `AUTORISATION_GENERAL`), with `is_permission_request=True`, no materials flag
and no material rows, can resume. Material resubmission still rebuilds every step,
including the configured classification review. Reference numbers never change.

## Approval validity

Submission writes a signed, version-1 `PERMISSION_BASELINE` audit event. It covers:

- Request type ID/code/active/permission/material/amount flags, requester and both departments.
- Description, amount, date needed, and the entire permission metadata JSON (including
  scope, people, destination/site, reasons, dates and times, and any additional keys).
- Attachment IDs, stored/original names, uploader IDs and SHA-256 content hashes.
- Applicable workflow ID, type, department, amount thresholds, active status and every
  ordered step's ID/order, configured user/role, resolved primary/alternate IDs and active
  status, required flag and stock-review flag.
- Instantiated approval IDs, orders, workflow-step IDs and assignments.

Description-only corrections are approval-neutral: the description remains in signed
baselines but is excluded from the validity comparison, including for existing version-1
baselines. All other content differences still restart, including permission reason
metadata (`exit_reason`) if changed outside the editing form. General Permission
Reason / Motif is editable only in drafts. After submission the form field is disabled
in Django validation, uses the persisted metadata as its initial value, and ignores
tampered POST values. Draft and Material Request forms retain their existing rules.
Returned General Permission forms expose description separately
from Reason / Motif. Each saved description change records previous/updated text, actor
and timestamp in `PERMISSION_DESCRIPTION_CHANGED`; resubmission baselines preserve the
attempt descriptions as well. Earlier baseline and decision records are not rewritten.
Unreadable attachments, absent/invalid signatures, unsupported versions, altered chains,
missing decision actors/timestamps, workflow/assignment changes and legacy missing
baselines cannot reuse approvals. Normal saves do not replace the baseline. A new baseline
is recorded only when an approval attempt starts or resumes.
Normal HTTP creation saves attachments before starting the attempt, within the
same database transaction, so the single initial baseline includes all uploads.

With valid unchanged evidence and exactly one returned step, earlier APPROVED rows remain
unchanged. The returning step and later PENDING steps receive new rows/IDs. Primary and
alternate permissions are unchanged, including when the alternate returned the request.

## History, security and transactions

Every successful resubmission archives all prior approval fields, actor-name snapshots,
and the routing decision/reason in the existing version-1 archive JSON. Legacy archives
remain readable. Request detail shows all archived steps; employee Approval History shows
their prior decisions separately, with existing filters and separate pagination. Historical
participants retain read access to request detail, but gain no new approval/document rights.

Edit/Save Changes/resubmission and approval actions lock the parent request before child
approval rows. The resubmission service independently requires an active authenticated owner.
Old pending URLs cannot target replacement rows. A second resubmission fails the locked
status check. General Permission intermediate-save token replays are recorded under the
request lock to avoid duplicate attachment saves. Emails retain their recipients/content,
but dispatch only after commit; rollback discards queued mail.

No schema migration or historical backfill is required. Signed evidence relies on the
configured Django signing keys; lost keys cause safe restarts. Audit rows remain subject
to existing administrator/database privileges, not a new tamper-proof storage guarantee.
File storage is not transactional: failed uploaded-file saves can leave an unreferenced
file, as with the existing upload mechanism. No automatic file deletion is performed.
Archived employee-history filtering reads legacy JSON in a streaming pass because
the existing audit column is text. Exact counts require scanning matching archives,
but only the requested page and final-page fallback are retained (at most 50 attempts
for a 25-row page), and only the displayed page needs actor-name hydration. Database
cursor batches are bounded; malformed and legacy archives keep the existing parsing
rules. Both current and archived results and their pagers are inside the live-filter
response region. No result cap hides historical decisions.

Removing the remaining system-wide scan safely needs an additive, indexed archive
participant/decision projection linked to the source audit record, with a validated
legacy backfill and dual writes for new archives. It would enable database filtering,
counts and pagination, at the cost of a migration and consistency/backfill review.
Text matching is deliberately not used: it can omit valid legacy JSON. That redesign
is deferred; the present bounded-memory change introduces no schema migration.

## Focused verification

Use a positively verified disposable local PostgreSQL test database; never inherit `.env`
or Supabase settings. The current local harness is
`config.material_entries_phasec_test_settings` with `--keepdb`. Run
`requests_app.test_permission_resubmission` plus existing material classification,
returned-material editing, alternate-approver and approval localization regressions.
Tests use synthetic records and an in-memory attachment store.
