# Phase 2 / Stage 3 / Checkpoint B

Local financial database foundation only. No production/shared database was
accessed. No issuance, number-allocation, invoice UI, PDF, payment or stock-change
service is included. The new app is deliberately not registered for ordinary
financial editing in Django admin.

## Schema

- `Invoice`: one per request, currency, nullable draft number, creation/finalization
  actors/times, explicit business timezone/date, protected classification approval,
  actor/date and succursale references, company verification, independent company,
  succursale, request-reference and branding snapshots, financial total, rounding
  policy/version, French amount-in-words and snapshot/audit metadata.
- `InvoiceLine`: stable position, protected material, code/description/unit
  snapshots, net quantity, nullable draft unit price and total, currency/rounding.
  Unknown price is NULL; explicit zero is valid. Quantity can be zero for an
  entirely returned pair so its financial exclusion evidence can be retained.
  Negative net quantities/prices/totals are forbidden. Actual source OUT movements
  must always have strictly positive quantities.
- `InvoiceIssueAllocation`: one OUT per line and one line per OUT under the
  approved conservative rule; stores the net quantity billed from that issue.
- `InvoiceReturnExclusion`: dedicated one-per-RETURN, whole-quantity exclusion
  ledger linked to the issue allocation. Excluded returns cannot support credits.
- `DocumentSequence`: document type, business calendar year, series, format
  (including prefix/year), positive configured starting/next counters, verification
  actor/time/digest and external-history evidence. No allocation method exists.
- `CreditNote` / `CreditAllocation`: protected original finalized invoice,
  financial snapshot/numbering fields, individual RETURN/issue allocation links,
  partial quantities, frozen price/description/amount and audit metadata.
- `CompanyVerification`: append-only administrator/time/content digest and full
  configuration snapshot; no invented company details or automatic attestations.
- `DocumentArtifact`: separate append-only protected storage/rendering metadata,
  one financial owner, language, version, reference/checksum/status/creator/time.
  Future render attempts append records instead of changing financial snapshots.
- `InvoiceAuditEvent`: append-only document/actor/time/type/identifier/details.
  Runtime migrations do not fabricate events.

Monetary storage: unit prices Decimal(16,4), totals Decimal(20,2), allocation/net
quantities Decimal(14,2). The explicit initial rounding policy identifier is
`DECIMAL_HALF_UP_2_V1`; PostgreSQL numeric round(value,2) guards the schema fixtures.
Future services must use Decimal ROUND_HALF_UP consistently, refresh DB-stamped
finalization timestamps and enforce domain limits before writes.

## Attribution and net quantities

Automatic financial eligibility requires an approved MICROCOM material request,
stock-deducted flag **and** actual consistent issue evidence, recorded classification
actor/time and its approved designated confirmation. A legitimately classified
succursale need not still be active. Ordinary classification rules are unchanged.

For every request/material pair:

1. Exactly one request-material item and one positive OUT must exist.
2. OUT quantity must equal the item quantity and relationships must match.
3. RETURN quantities must be positive, not predate their OUT, and cumulative
   returns must not exceed the issue. Unmatched OUT/RETURN materials are rejected.
4. At finalization, billed allocation plus recorded RETURN exclusions must equal
   the OUT quantity. Every pre-finalization RETURN must have its whole quantity
   excluded. Each line quantity must equal its issue allocation.
5. Zero legacy OUTs, multiple OUTs, duplicate items or inconsistent histories
   block only financial eligibility with an administrator-review error. No legacy
   records are repaired, associated by FIFO, deleted or backfilled.
6. Future credit schema accepts only matching post-finalization RETURN evidence,
   rejects excluded RETURNs, and caps cumulative allocations by both the individual
   RETURN quantity and the original net invoiced allocation. Draft credit
   allocations conservatively reserve capacity too; deleting an unfinalized
   allocation releases it. Credits never mutate stock.

Database guards lock the financial parent (and source movement when allocating)
before aggregate checks. Invoice eligibility/finalization takes a SHARE row lock
on its request, which serializes against the existing return service's request
lock. Partial credit allocations serialize on the original finalized invoice.
The concurrency tests exercise competing schema allocations, not a future credit
issuance service.

Document/allocation writes explicitly require READ COMMITTED (Django's existing
PostgreSQL default) and fail closed under other isolation modes. Parent row locks
plus fresh statement snapshots protect aggregate checks; a REPEATABLE READ
snapshot could otherwise miss a competing allocation despite waiting for its
lock. No existing stock/approval service isolation setting is changed.

## Calendar and numbering

`CompanyDocumentSettings.business_timezone` defaults to validated
`Africa/Kinshasa`. Django `TIME_ZONE='UTC'` and timestamp storage remain unchanged.
Aware instants convert to business-local dates/years; at 23:00 UTC on December 31
Kinshasa has entered January 1 of the following year. A document records its
applicable timezone. Invoice and credit-note timezones must match explicit company configuration.

Separate `(document_type, series, year)` rows provide annual invoice/credit scopes.
Formats must contain `{year}` and `{number}`; existing format validation prevents
unsafe format expressions. Starting values are configurable and no year rows or
counter increments are generated automatically. Administrator attestation must
reference an independently checked external numbering history. A changed sequence
configuration invalidates attestation; once used by a finalized document it cannot
be changed. Counters cannot move backwards.

Future allocation must lock the existing scope row with `select_for_update()` in
the same transaction as finalization, verify its attestation, use/increment the
counter and persist all document data atomically. First-row creation needs the
unique scope constraint plus a savepoint/retry. This allocator is **not implemented**
or claimed as tested. No MAX+1 is used.

Final number/counter lifecycle constraints forbid draft numbering. Final numbers
are unique within each table; the technical `invoicing_finalreference` registry
adds a shared unique key across invoice/credit tables, including at REPEATABLE READ.
Its trigger-written entries are append-only and transactionally rolled back if
finalization fails. It does not generate numbers. This remains a final
safety net if administrators configure overlapping formats across series/years.

The finalization guard rejects stale/future caller timestamps and persists current
database time. Its business-local date must match the issue date and sequence year;
a boundary mismatch aborts atomically. No caller backdate is persisted. Future
services must keep transactions short and retry with the correct business year.
No actual finalization or number-allocation service is exposed in Checkpoint B.

## Company attestation and frozen branding design

`CompanyVerification.attest(configuration, administrator)` locks configuration,
checks active staff plus explicit `invoicing.add_companyverification` permission,
requires supplied name/address/contact information, and records contents/digest.
No existing user receives new permissions automatically. `is_current` reads current
configuration, so even an ORM bulk configuration change invalidates the content
binding. Final invoice guards compare both company snapshot and current persisted
configuration to the attestation snapshot. Editing settings requires re-verification.
There is no invoice finalization UI.

Snapshots are independent stored JSON/text/Decimal values, not live catalogue
renderings. Future branding must freeze actual asset bytes (embedded data or
immutable content-addressed protected storage), record SHA-256/content type and
version, and never render a finalized document from a mutable logo path. The
`branding_snapshot` field reserves this structure; this checkpoint does not copy
assets, implement storage migration, validate file bytes or render documents.
Future lifecycle services must validate snapshot structure/content, French wording,
asset integrity, permissions and numbering format output before issuance. Nonempty
JSON in a schema fixture is **not** evidence of a production-ready branding pipeline.

## Guards and limits

- DB lifecycle/choice/nonnegative checks, unique invoice/request, line ordering,
  source allocation, full numbers and sequence counters; protected foreign keys.
- PostgreSQL BEFORE INSERT/UPDATE/DELETE guards for eligibility, ownership,
  cumulative allocation limits and finalized parent/child immutability. They also
  cover direct row SQL and attempts to move a finalized child to another parent.
- Model validation on ordinary saves, model finalized/evidence restrictions,
  and rejection of ORM bulk create/update/delete paths. DB triggers cover ORM
  internal operations and races that model validation alone cannot prevent.
- Append-only company attestation, financial audit and artifact records; artifacts
  may be added later without changing finalized financial content.
- No admin bypass, database extension or existing-stock-table trigger is introduced.

Table owners/superusers can disable triggers, execute DDL/TRUNCATE or alter data
outside these guards. Deployment must separate migration ownership from the
runtime role and withhold TRUNCATE/DDL/trigger-management rights. No roles or
privileges were altered here. Existing stock-table direct SQL/privileged edits
remain an external limitation; the new financial snapshots themselves are frozen.
Production security review and historical balance reconciliation remain outstanding.

## Migrations, locks and rollback

- New `core/0002_companydocumentsettings_business_timezone`: depends on core0001;
  adds the approved timezone default only, not company identities/verification.
- New `invoicing/0001_initial`: depends on core0002, inventory0003,
  requests_app0017 and the swappable user model. requests_app0017 already depends
  on workflows0003. Creates only new financial tables/constraints/indexes/FKs.
- New `invoicing/0002_financial_guards`: depends on invoicing0001; creates reversible
  PL/pgSQL guard functions/triggers on the new tables only.

No existing migration was edited. No request, approval, material, movement,
quantity, price, classification or financial record is backfilled.

Measured disposable timings, SQL and locks are in the evidence JSON. Core column
addition takes AccessExclusiveLock on its configuration table. New table/index
creation locks the new relations; foreign-key installation also takes
ShareRowExclusiveLock on referenced existing tables, including request, movement
and material tables. These can briefly block ordinary writes: additive does **not**
mean lock-free. Future authorized deployment must use a short lock timeout,
preflight active transactions and retry rather than wait indefinitely. Disposable
timings are not production availability guarantees.

Guard DDL and empty financial schema reversal/reapplication are rehearsed. Reversing
populated financial migrations would destroy financial evidence and remove guards;
it is not an acceptable business rollback after issuance. Use verified backups and
forward corrections under a separately reviewed release plan.

## Verification and ReportLab

The runner never imports normal config settings or the repository .env. It uses
the existing staging-only settings module with credentials/DB configuration replaced
before Django initialization, random disposable credentials, localhost port55442,
and a unique workspace data directory. PostgreSQL server version180006, DB name,
role, IP, port, data directory and postmaster start identity are verified before
writes, including new connections. Existing staging port55440 and live/shared
databases are not used. Tests use synthetic records only.

Focused schema tests include valid drafts, NULL/zero prices, invalid negatives,
legacy ambiguity rejection, partial/full return exclusion, credit caps/concurrency,
immutability through ORM/raw row SQL, protected references, company invalidation,
sequence scopes/row locks, backdating checks, and English/French labels/errors.
Migration tests preserve synthetic legacy zero/OUT/RETURN/NULL-token records and
rehearse reversible DDL. Schema fixtures explicitly use synthetic document references;
they are not actual business issuance or number allocation.

ReportLab is absent from the venv; nothing was installed and no PDF generated.
Read-only review of https://docs.reportlab.com/install/open_source_installation/
indicates an independent PDF dependency would be needed for a later rendering
checkpoint. A later approved prototype must test Windows/Python compatibility,
embedded Unicode fonts/French accents, images, A4 pagination, tables, protected
storage and reproducibility. No dependency/version choice is committed here.

## Exact checkpoint file manifest

Modified existing files:

- `config/settings.py` — register invoicing only; UTC retained.
- `core/models.py` — explicit validated business timezone.
- `inventory/test_stage1.py` — include new timezone field in the admin POST fixture.
- `inventory/test_stage1_migrations.py` — remove dependent financial schema when
  rehearsing older migrations and restore real leaves afterward.
- `requests_app/test_legacy_stock_compatibility.py` — same migration dependency handling.
- `requests_app/test_stock_classification_migrations.py` — same dependency handling.
- `locale/fr/LC_MESSAGES/django.po` and `django.mo` — additive bilingual messages.

Created files:

- `core/migrations/0002_companydocumentsettings_business_timezone.py`
- `invoicing/__init__.py`
- `invoicing/apps.py`
- `invoicing/configuration.py`
- `invoicing/models.py`
- `invoicing/tests.py`
- `invoicing/test_migrations.py`
- `invoicing/migrations/__init__.py`
- `invoicing/migrations/0001_initial.py`
- `invoicing/migrations/0002_financial_guards.py`
- `local_artifacts/test_checkpoint_b_runner.py`
- `local_artifacts/checkpoint_b_translations.py`
- `docs/PHASE2_STAGE3_CHECKPOINT_B.md`

Generated evidence files and final results are listed in the accompanying local
checkpoint report. Disposable cluster directories are removed after verification;
only nonsensitive test evidence is retained. Existing work is preserved. Checkpoint C
requires user review and separate authorization.

## Final recorded result

Final complete suite on PostgreSQL 18.6: **262 tests run, 261 passed, zero failures,
zero errors, one existing optional sample-generation skip**, in 143.765 seconds.
This includes 37 new financial schema/migration/concurrency tests and the existing
Phase 1 / Stage 1 / Stage 2 suites. System checks, dry-run migration consistency
and diff whitespace checks passed. PostgreSQL 18.4 was not tested.

All 104 explicit invoicing model/configuration messages have French catalogue
entries. Runtime tests assert English/French model/field labels and validation;
existing bilingual approval/report regressions also pass. Existing translations
were retained and PO/MO files remain UTF-8 compatible.

Final synthetic migration timings (not production estimates):

| Migration | Seconds |
| --- | ---: |
| core0002 business timezone | 0.105875 |
| invoicing0001 initial schema | 3.418875 |
| invoicing0002 guards/unique reference registry | 0.100636 |

Exact retained evidence files:

- `local_artifacts/checkpoint_b_evidence_6ff4c2ad/pg18-regression-results.json`
- `local_artifacts/checkpoint_b_evidence_6ff4c2ad/checkpoint-b-migration-results.json`
- `local_artifacts/checkpoint_b_evidence_6ff4c2ad/stage1-migration-results.json`
- `local_artifacts/checkpoint_b_evidence_6ff4c2ad/stage2-migration-results.json`
- `local_artifacts/checkpoint_b_evidence_6ff4c2ad/verification-summary.json`

The runner dropped the final disposable test database and stopped its cluster.
Fourteen explicitly identified disposable directories created during this checkpoint
were removed after verifying their resolved workspace paths and absent postmaster
PID files. An exclusive localhost bind confirmed port55442 is unused. Windows CIM
process metadata was unavailable under the sandbox; cleanup did not rely on that
query as shutdown evidence. Existing services/staging directories were not modified.

Recommendation: **GO for Checkpoint B review**. Checkpoint C and production
deployment remain unauthorized. Actual lifecycle services, number allocation,
French amount conversion, frozen asset/storage integrity, document rendering,
production privilege review and historical-data preflight remain future work.
