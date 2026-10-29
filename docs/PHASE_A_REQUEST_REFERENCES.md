# Phase A: ordinary request references

Implementation is local only. Migration `0018_ordinary_request_references` is
created but **not applied**. No real database or PostgreSQL tests were used.
Do not deploy the source before the migration has been reviewed and applied in
an authorized environment. Keep `MATERIAL_RETURN_NOTE_UI_ENABLED=False`.

## Formats and namespaces

New requests use `REQ-{namespace}-{counter:04d}/{year}`. Canonical request-type
code `MATERIAL` maps to MAT; the type matching the existing
`ADMINISTRATION_REPORT_REQUEST_TYPE_CODE` setting (default
`AUTORISATION_GENERAL`) maps to ADM. Other types derive uppercase alphanumeric
namespaces from their stable code. Codes longer than 16 characters use a
deterministic shortened code with a hash suffix. Numeric-leading, empty,
reserved or colliding derivations fail closed; an authorized administrator can
configure a distinct valid namespace before first use. No addresses, type rows
or namespaces are invented in a data migration.

The request type stores a unique namespace on first successful creation (or
explicit authorized initial configuration) and locks it against later changes,
including direct SQL updates. Model/Admin validation and database INSERT/UPDATE
guards enforce canonical ADM/MAT ownership even for explicit configurations.
Admin presents it read-only once assigned. Display-name changes do not change
an assigned namespace. Noncanonical code changes can retain the same namespace;
canonical codes cannot be renamed away from their reserved ownership after
assignment. A new separately numbered category requires a distinct
request type. A draft changing its request type keeps its original reference
and allocation metadata; it is never renumbered.

Counters are independent by request-type ID and year. PostgreSQL computes one
allocation instant using `clock_timestamp()` after the type lock, deriving its
year explicitly in Africa/Kinshasa. First use automatically creates counter 1.
No annual preparation, attestation or management command is involved. A
transaction crossing midnight retains the year of its allocation instant;
the next allocation after midnight uses the new year. No server-local date is
used. Padding expands beyond 9999. Exhaustion at signed-bigint capacity fails
without changing the counter. Requests retain their existing globally unique
reference field and additionally have a unique allocation identity.

## Creation and retry

The existing browser endpoint, multipart fields and UUID `submission_token`
remain unchanged. New operations still require a pending token admitted by the
existing session mechanism, normal forms, existing department access, CSRF and
material validation. There is no new API endpoint or permission grant.

The existing token becomes the durable creation key. The receipt binds the
actor and a SHA-256 digest of submitted field lists and uploaded file contents,
names, sizes and content types. CSRF and submission-token fields are excluded
from the payload hash. Receipt rows store no upload bytes or plaintext payload.
Replays must resend the same submitted data (including attachments); semantic
equivalence with different raw field values is not treated as exact replay.

An exact committed replay returns the same request before form revalidation,
even if the session token entry was lost or overwritten. Actor or payload
conflicts are rejected. An initial database recovery error returns a sanitized
503 response without creating a fresh token or attempting creation; keep the
original form and retry the same fields and attachments. Exact replay remains
available to the authenticated owner even if their department assignment was
removed; new creation still requires that assignment. Storage/database failures
during creation return the same bound form/token with a sanitized 503 error.
An expired/unrecognized token with no committed
receipt cannot create. Existing pre-migration used session tokens have no
receipt and are rejected as expired; their saved requests remain accessible
through My Requests. Do not replace the token to recover an uncertain commit.

The transaction locks receipt, then request type, then allocates its annual
counter. Receipt creation uses a unique UUID key with race-safe get-or-create;
only the receipt itself is locked across its nullable request join. Existing
scope uniqueness and a PostgreSQL UPSERT protect first-year initialization.
Request, material rows, approval steps, submission audit and receipt commit
together. Failure rolls back namespace assignment and counter allocation.
Creation email is deferred until successful commit; other service callers keep
their previous notification behavior. Committed receipts cannot be edited or
deleted; their protected request relation also prevents deleting a referenced
request. Cancellation retains its reference.

Only the creation endpoint invokes the new service. Edit, correction,
resubmission, approval, rejection, printing and stock operations do not allocate.
Direct ORM imports supplying historical references remain possible, with NULL
allocation metadata; they are not an alternate automatically numbered API.
New Request add access is disabled in Django Admin, including direct add URLs.
Existing authorized Admin viewing/editing remain available, with the reference
read-only. Use the normal application creation page for all new requests.

## Preservation and limitations

The migration adds tables, nullable metadata, constraints and guards for
ordinary references only. Its RunPython operations install/remove DDL guards
and perform reversal preflight; they do not backfill or UPDATE historical
rows. Existing request numbers become immutable without being rewritten.
Existing financial models, guards, number sequences, PDFs and stock deduction
code are unchanged. BC, BS and BR numbering are outside this phase.

File storage is not transactional. Uploads are saved after workflow validation,
but a later filesystem/commit failure may leave a private uploaded-file orphan.
No automatic deletion or reconciliation is introduced. A resubmitted form must
reselect the same attachments when the browser clears file inputs. Database
receipt recovery prevents a second committed request after a lost response.

Before migration, inspect request-type namespace derivations and any manually
entered references already matching the new format in an authorized read-only
assessment. Collisions fail closed; this phase never skips occupied references,
renumbers historical data or resets a counter. PostgreSQL trigger execution,
concurrency and real workflow integration are not proven by offline tests.

## Validation

Database-free runner:

```powershell
.\venv\Scripts\python.exe local_artifacts/test_request_references_offline.py
```

It uses synthetic settings with no database aliases and blocks connection and
network attempts. It checks formatting, mapping, metadata, clock SQL, replay,
upload hashing, legacy compatibility, migration state, bilingual messages and
model system checks. The existing invoice offline runner checks compatibility.

`requests_app.test_references_postgresql` and
`requests_app.test_references_material_postgresql` are supplied but **not run**. Future
execution requires an explicitly verified disposable isolated PostgreSQL test
database and explicit authorization; never run it with Supabase application
settings. It covers concurrent first use, same-token races, rollback, rollover,
10000/exhaustion, historical references, frozen namespace guards, real workflow
submission and lost-session HTTP replay. Also run the existing request,
approval, classification, stock and invoice regression suites there before
approving controlled development migration. No migration, deployment or
database-backed test execution is authorized by this document.

## Reversal and operational recovery

Migration 0018 has not been applied and is amended in place for this review.
Do not replace an already-applied copy in another environment; stop for an
explicitly reviewed forward migration if its history differs.

The migration installs the configured canonical administration type code as a
quoted literal in the PostgreSQL ownership guard. The material code is MATERIAL.
Do not change ADMINISTRATION_REPORT_REQUEST_TYPE_CODE after installation without
a reviewed forward policy migration; application and DB ownership must agree.
An ambiguous administration/material configuration fails installation. No session
setting can bypass database ownership rules.

Fresh unused reversal remains possible through Django's migration executor.
The LAST forward operation is a no-op whose reverse runs FIRST. It requires an
atomic PostgreSQL migration, locks receipt/type/sequence/request tables, then
refuses reversal if any receipt, positive counter, or allocated request exists.
Locks remain held through the subsequent reverse DDL, preventing a check/drop
creation race. A refusal aborts before any guard, field or evidence is dropped.

Future approved recovery procedure:

1. Quiesce application writers and positively verify the authorized target and
   migration history. Preserve all counters, metadata and receipts.
2. For unused installations only, an approved normal Django reversal may pass
   the preflight. Do not execute exported reverse SQL: RunPython safety checks
   are not represented by sqlmigrate output.
3. After ANY numbering use, keep 0018 applied. Fix application behavior or use a
   separately reviewed forward migration preserving existing evidence. Never
   fake-unapply, disable guards, delete receipts/counters, or drop fields to force
   reversal. Do not redeploy a reference-unaware creation path.
4. Rehearse unused reversal/reapply and used-reversal rejection in an explicitly
   verified isolated database before any real migration approval.

Expanded isolated tests include real material rows and stock-review workflows,
draft submission/correction/resubmission, one final stock deduction, concurrent
submitted retries and one creation notification callback, attachment retry and
storage failure, Admin access, explicit namespace ownership, concurrent namespace
collisions, immutable receipts/counters, and migration round trips. These remain
unverified until executed on the authorized isolated target. Notification tests
prove callback scheduling only; no exactly-once external mail delivery is claimed.
