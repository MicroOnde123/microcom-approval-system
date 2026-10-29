# Checkpoint E-R4 — Return Note integration and failure recovery

Status: database-free implementation and validation complete. Activation remains
disabled. E-R2 database validation and real E-R3/E-R4 integration remain
outstanding; no database safety or production-readiness claim is made here.

## Issuance recovery

E-R2's two error helpers now carry stable sanitized codes: `preview_invalid`
and `outcome_uncertain`. Their existing messages are unchanged. Every other
E-R2 function's AST is compared with the E-R4 baseline: valuation, locking,
rounding, numbering, guards, authorization and exact committed replay are
unchanged. Unclassified validation errors conservatively require review.

An uncertain issuance shows an explicit CSRF-protected **Retry same confirmation**
POST, carrying only the retained opaque session handle. The original arguments,
issuance UUID and signature remain server-side and are forwarded unchanged to
E-R2. No new UUID/preview is generated automatically. The error page also offers
issued-note history and explains that the prior transaction may have committed.
It does not offer a new-preview shortcut for an uncertain result.

Missing/invalid handles lead to history recovery and an explicit explanation:
a new preview is a different operation, not a retry of the previous operation.
Fresh authorization is still required by both view and E-R2. Retrying does not
guarantee success if permissions were revoked or the original new issuance's
confirmation expired. A committed replay remains E-R2's decision.

## Session envelopes and expiry

Server-side storage, existing session key and 900-second session timeout are
preserved. No new storage service, global session setting, lock or CAS mechanism
was introduced. Each new entry has a version, creation timestamp, actor/invoice,
exact issuance arguments, canonical UUID token and nonempty signed confirmation.
The implementation validates container/handle/entry shapes, positive integer IDs,
unique complete movement IDs, reason/series bounds, finite timestamps, excessive
future timestamps, UUID shape and confirmation size. Extra/unknown entry fields
and previous unversioned envelopes fail closed. Invalid unrelated entries cannot
crash a valid tab; invalid targets cannot invoke issuance.

The signed two-hour issuance limit remains authoritative in E-R2. Session helpers
check whether a retained envelope has exceeded that window but do not reject it
before E-R2 can recover a committed note. An expired NEW issuance is rejected by
E-R2 as before. Server-session expiry or overwrite removes access to the handle,
so exact replay cannot be promised once its payload is lost.

Storage remains bounded at 32 handles. Concurrent whole-session writes can still
overwrite a newer handle. The accepted behavior is safe failure plus history
recovery, not guaranteed concurrent-tab persistence. No attempt is made to merge
sessions or recreate lost issuance UUIDs. Global timeout is not extended.

## PDF recovery

PDF generation/download views retain an authorized issued-note owner and requested
language. Error pages provide **Return to issued note**. Reliably retryable failures
provide a separate CSRF-protected **Retry PDF** POST for that note/language. This
action calls PDF generation only; it never calls issuance.

Failure categories are conservative:

- Known SQLSTATE connection/interruption/concurrency failures and identified
  temporary filesystem errors permit PDF retry.
- Missing/corrupt READY file bytes permit regeneration from the immutable note.
- Unknown database failures, permission/configuration errors, frozen snapshot,
  font, invalid-renderer and other unclassified failures require administrator
  review rather than blind retry. OperationalError alone is not proof that a
  failure is transient.

Private root/reference checks, size/PDF-header/SHA-256 verification, per-note
serialization, document permissions and append-only READY/FAILED artifact
records are preserved. Frozen notes, originals and financial sequences are not
modified by rendering or retrying. No exception details, signatures, issuance
UUIDs or private paths are included in recovery HTML.

The PDF renderer itself is unchanged. Existing bilingual, logo-free A4 formatting
and immutable snapshots continue to be used. A metadata transaction failure may
leave a private file with no committed artifact row; no automatic deletion or
reconciliation is performed.

## Read-only orphan diagnostics

`invoicing.return_note_orphans.inspect_private_files(root, artifact_snapshot)`
accepts an explicit absolute private directory and an explicitly supplied artifact
snapshot. It imports no ORM/settings, opens no database, follows no links/junctions,
creates no files, and does not remove or reconcile anything. It reports provisional
unreferenced files, FAILED references, missing references and unexpected entries.

The report is explicitly non-atomic: a concurrent generation transaction can
make a file appear unreferenced before its row commits. Its output is not a
deletion authorization. There is no public diagnostic route or automatic scan.
Only newly created synthetic directories were inspected during offline tests;
existing E-R2 clusters/evidence/private operational storage were not scanned.

## Workflow and history

Material Reports now includes the existing gated, permission-aware navigation
fragment for each request. Authorized users without a finalized facture see an
explanation that returning stock creates neither a facture nor a Bon de retour.
All links/messages remain hidden without the gate and appropriate authorization.
Existing Return to Stock URLs, physical-return POST, calculations and redirect
are unchanged. No stock business/view code was modified.

Selection adds a display-only explanation for ineligible movements dated before
or exactly at facture finalization. E-R2 eligibility is never overridden. No
quantity, price, invoice cutoff or historical exclusion is changed.

Issued-note history shows finalization time converted to the note's explicit
business timezone, and up to five immutable note-line movement references with
quantities/units. A count points to the full note for additional movements. It
does not infer past valuation from current stock data or expose audit payloads.

## Exact implementation files

Created:

- `invoicing/return_note_recovery.py`
- `invoicing/return_note_sessions.py`
- `invoicing/return_note_orphans.py`
- `invoicing/test_return_note_recovery.py`
- `local_artifacts/checkpoint_er4_static_review.py`
- `local_artifacts/checkpoint_er4_translations.py`
- `docs/PHASE2_STAGE3_CHECKPOINT_E_R4.md`

Modified:

- `invoicing/return_note_services.py` (two error codes only)
- `invoicing/return_note_views.py`
- `invoicing/return_note_documents.py`
- `invoicing/return_note_access.py`
- `invoicing/test_return_note_views.py`
- `invoicing/test_return_note_documents.py`
- `invoicing/test_return_note_pdf.py`
- `templates/requests_app/material_reports.html`
- `templates/invoicing/return_notes/pdf_error.html`
- `templates/invoicing/return_notes/history.html`
- `templates/invoicing/return_notes/links.html`
- `locale/fr/LC_MESSAGES/django.po`
- `locale/fr/LC_MESSAGES/django.mo`

New baseline/results/manifest/log artifacts live under
`local_artifacts/checkpoint_er4_baseline.json` and
`local_artifacts/checkpoint_er4_evidence`. Existing evidence is not removed.
Synthetic PDF/file-test outputs are directed to E-R4 evidence rather than
overwriting E-R3 examples. Config/settings, stock workflows, invoice services,
models, migrations, permissions and all routes are unchanged from the baseline.

## Validation actually performed

Final offline suite: **52 passed, 0 failures, 0 errors, 0 skipped**.
Ten templates compile; 87 literal messages match between French PO/MO catalogues.
The standalone runner loads synthetic settings only, never application settings
or .env, and supplies no database configuration. Database/network connection
attempts are blocked and counted: **zero**. Feature settings remain absent/default
false in the harness; gate behavior is mocked only inside individual tests.

Checks include:

- Same-handle uncertain issuance retry and identical saved payload forwarding.
- Missing, malformed, wrong-owner/invoice, expired-session, overwritten and evicted
  handles; future/nonfinite timestamps and expired-confirmation replay forwarding.
- Explicit whole-session last-writer-wins simulation, without a concurrency claim.
- PDF retry language/owner retention, permission-before-generation, conservative
  failure categories, no issuance calls from PDF retry and immutable FAILED attempts.
- Gated optional report links, unchanged stock-return URL, display-only cutoff
  explanation and immutable history summaries/business timezone conversion.
- Existing E-R3 route/gate/CSRF/privacy/document checks and synthetic EN/FR PDF tests.
- Read-only diagnostic file hashes/timestamps unchanged before/after inspection.
- Preservation hashes plus exact AST equality for every E-R2 financial function.

The initial expanded harness exposed outdated fake history/session fixtures and
two tests using POST against GET-only routes; those fixtures/tests were corrected.
It also imported an existing TestCase class into a discovered module, duplicating
11 tests. The import was changed to a module reference; final counts include each
test once. Earlier run evidence is retained.

## Remaining risks and deferred validation

E-R2's database tests and real E-R3/E-R4 integration are still outstanding. Offline
results do not prove exact committed replay, lock/sequence behavior, session
concurrency, permissions against live assignments, artifact transaction/file
coordination or historical-data preservation. Run the outstanding E-R1/E-R2 suites,
real HTTP/session/PDF integration and full regressions only after separate local
PostgreSQL authorization and configuration. Browser visual/accessibility review
also remains outstanding.

Session loss can prevent replay even when a note committed; history is the safe
recovery route. Older envelope versions require new previews after checking
history. Per-request navigation and per-note authorization queries may need later
measurement. Private orphans remain possible and are not automatically cleaned.
The existing E-R2 disposable-cluster issue remains unresolved and untouched.

No migration is required or added. No database settings, environment variables,
activation gates, roles, historical data or document numbers were changed. No
commit/push/deployment or subsequent checkpoint work was performed.

## Deferred final-stage requirements — not investigated or implemented

1. **Approval History search/filtering.** Before future implementation, inspect
   the actual existing views, templates, queryset, permissions and pagination.
   No assumptions about their structure are made here.
2. **Reference-number standardization.** Before future implementation, inventory
   actual formats, prefixes, sequences, references, dependencies and collision
   safeguards. Propose a recognizable consistent convention while preserving
   historical references, internal IDs and business rules. Never rename or
   renumber historical documents.

These requirements were documented only. No Approval History investigation,
reference inventory, search/filter implementation or renumbering was undertaken.
