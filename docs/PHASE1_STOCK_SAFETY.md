# Phase 1 stock safety

This change preserves approval routing, gross-issued reports, Excel analytics,
and existing document printing. It adds no pricing, branch or document models.

## Stock operations

Final approval retains its existing atomic transition. Deductions reload and lock
the request, aggregate quantities by material, then lock materials in ascending
primary-key order before checking availability. Movement writes and the deduction
flag share the transaction. The existing service import remains available from
`requests_app.services`.

Returns run in an atomic service with authorization, request/item eligibility,
quantity validation, material locking, movement creation and audit logging.
Locks are acquired in request/item/material order. Legacy OUT and RETURN movements
are counted only when request/material identifies exactly one request line.
Repeated-material lines, missing issues, nonpositive movements, issued quantities
that differ from the original line, and historical over-returns block new returns.
No historical association or stock adjustment is inferred.

Each rendered return form receives a signed operation token bound to the user and
item, expiring after 24 hours. The UUID is saved in a unique nullable field on the
existing RETURN movement. The same token is a retry of the first operation; a new
form represents a distinct return, even when quantity and reason match. Invalid
or expired forms must be reopened. A retry after expiry is rejected without writes.
Do not delete or edit completed RETURN movements: their tokens are the retry ledger.
The movement admin now denies add/change/delete operations, including bulk delete
and forged POSTs, even for superusers. Existing authorized staff retain read-only
list/detail access. All movement fields, including reason and retry token, are
read-only. Service creation is unaffected: no StockMovement save/delete override
is used. Material and request relationships use PROTECT so parent deletion cannot
delete movements or clear their request references through the Django collector.

Direct SQL, database administrators, custom scripts and direct movement ORM
updates/deletes remain outside these admin controls. This is not a database
immutability policy; database privileges and backups remain necessary. User
deletion can still clear the nullable performed_by link under existing behavior.

Draft material forms validate every supplied quantity before any database writes,
while allowing incomplete rows and quantities above current availability. Only
complete validated rows are persisted. Header, line changes/deletions and attachment
database records share a transaction, with model ValidationError handled outside
the transaction. Invalid drafts keep their submission token available for a retry.
Final submission retains its stricter completeness and stock checks. File storage
itself is not transactional; unexpected storage failures can leave orphan files,
although invalid quantity validation happens before attachment saving.

The existing `stock_returned` flags are not used as quantity accounting. Movement
history is authoritative for this phase. No new return model is introduced.

## Migration and historical data safety

`0015_stock_return_retry_and_quantity_validation` adds a nullable unique UUID to
StockMovement and records the request quantity validator in migration state.
Existing rows retain NULL tokens. There is no backfill, data correction, deletion,
or positive-quantity database constraint. PostgreSQL permits multiple NULLs in a
unique column. Adding the unique field still takes a schema/index lock: schedule
the migration appropriately after staging validation and a backup.

`0016_protect_stock_movement_references` changes the material and request deletion
policies to PROTECT in Django migration state. It performs no data backfill or
record correction. Existing NULL request references remain valid. Parent deletion
is intentionally blocked when movements exist; legitimate stock service writes
are unchanged. PostgreSQL SQL generation for this migration should be reviewed
alongside the migration plan before rollout.

Forms, model validation/save, submission, and deduction reject quantities below
0.01, with two decimal places retained. Direct SQL, bulk_create and QuerySet.update
can bypass Python validation. A future positive-quantity database constraint must
wait for an authorized historical data review. Do not silently fix invalid rows.

The following are read-only preflight queries for an authorized database operator:

```sql
SELECT id, request_id, material_id, quantity
FROM requests_app_requestmaterialitem WHERE quantity <= 0;

SELECT request_id, material_id, COUNT(*) AS line_count
FROM requests_app_requestmaterialitem
GROUP BY request_id, material_id HAVING COUNT(*) > 1;

SELECT id, request_id, material_id, movement_type, quantity
FROM requests_app_stockmovement
WHERE movement_type IN ('OUT', 'RETURN') AND quantity <= 0;

SELECT request_id, material_id,
       SUM(CASE WHEN movement_type = 'OUT' THEN quantity ELSE 0 END) AS issued,
       SUM(CASE WHEN movement_type = 'RETURN' THEN quantity ELSE 0 END) AS returned
FROM requests_app_stockmovement
GROUP BY request_id, material_id
HAVING SUM(CASE WHEN movement_type = 'RETURN' THEN quantity ELSE 0 END)
     > SUM(CASE WHEN movement_type = 'OUT' THEN quantity ELSE 0 END);
```

Also reconcile each unambiguous line with its OUT total and review approved
requests with missing issue movements or `stock_deducted = false`. These queries
do not establish a reconciled physical stock balance; opening balances and direct
admin adjustments may not have movement records.

Deploy migration before enabling this application version. For rollback, retain
the nullable token column and completed token records while rolling back the
application; removing the column loses retry history. Older application versions
also restore the old unsafe return behavior, so disable returns during rollback.

## Verification

Run `python manage.py check`, `python manage.py makemigrations --check --dry-run`,
and `python manage.py test` only with explicitly isolated test database settings.
The stock-specific suite is `requests_app.test_stock_safety`.

PostgreSQL concurrency tests use TransactionTestCase and separate thread/database
connections, with lock and statement timeouts. They cover competing final
approvals, repeated approval, competing returns, duplicate return tokens, distinct
equal returns, reverse material order and simultaneous issue/return. They skip
explicitly on other backends; SQLite cannot verify row-lock behavior.

Before rollout, review blocked historical requests without changing them, verify
English/French forms and messages in a browser, and check migration lock timing on
a staging copy. Inventory admin and external SQL/import writers remain outside
the coordinated stock service and require operational controls.

### Local verification on 2026-10-21

The complete suite ran on a freshly initialized disposable PostgreSQL 17.11
cluster bound to 127.0.0.1:55439, with all database settings overridden before
Django setup. The configured application database and existing SQLite file were
not used. Email used the in-memory backend and password hashing used MD5 only
inside the test process.

- 138 tests: 137 passed, 0 failed, 1 skipped.
- All 34 new stock tests passed, including 7 PostgreSQL concurrency tests.
- The skipped test is the existing opt-in Excel sample generator
  (`GENERATE_STOCK_REPORT_SAMPLES=1`), not a concurrency test.
- Django system checks passed; migration consistency reported no changes.
- The migration was exercised only while setting up the isolated test database.
- French compiled-catalog comparison retained every previous entry/value and
  added 16 entries; no existing translation changed.

An early test run exposed a translation-function variable shadowing bug and a
test client language-header issue; both were corrected before the successful
full run. Windows sandbox permissions prevented PostgreSQL's automatic DROP
DATABASE/checkpoint signaling during early teardown. The final successful run
used `keepdb=True` on a separate test database, and the temporary server was
stopped afterward. No production migration or historical data review was run.

### Final hardening verification on 2026-10-21

A fresh disposable PostgreSQL 17.11 cluster on localhost:55439 was used with
explicit test-only database settings, in-memory email and test-only MD5 hashing.

- Complete suite: 155 tests, 154 passed, 0 failed, 1 skipped (the same opt-in
  Excel sample generator). All 7 PostgreSQL concurrency tests passed.
- All 17 final-hardening tests passed, including bilingual invalid/valid drafts,
  rollback after writes, direct/bulk admin attacks, superuser restrictions and
  parent deletion protection.
- English/French tests assert precision, positive-value, invalid-number,
  oversized-value and successful-draft messages using existing language selection.
- Three explicit quantity translations were added because the installed Django
  French catalog did not translate its decimal-precision error. PO and MO updated.
- System checks passed and migration consistency reported no changes.
- PostgreSQL `sqlmigrate` for 0016 generated only BEGIN/COMMIT and no-op comments:
  the two deletion-policy changes affect Django's collector and migration state.
- Migrations ran only on disposable test databases, never the configured database.

No commit, push or deployment was performed. Historical production records were
not inspected or modified. Staging validation remains the recommended next step.
