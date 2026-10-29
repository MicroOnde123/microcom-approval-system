# Phase 2 / Stage 3 / Checkpoint E-B

Local credit schema, guards and tests only. No operational credit creation, editing,
review, finalization, release, rebalancing, numbering, UI, PDF, email, payment or stock
service is implemented. Synthetic schema transitions are test fixtures, not issuance
services. No production/shared/existing development database is accessed.

## Compatibility and pre-implementation proof

Reviewed the preceding assessment, B/C/D reports, credit/invoice models, migrations,
tests, invoice finalization/numbering, stock return/provenance, company verification,
timezone, artifact protection and translation conventions. Existing credit quantity
caps counted draft reservations, but independent rounding could over-credit money.
Header finalization did not fully validate snapshots or prevent parent reassignment.

Before application schema changes, a disposable PostgreSQL18.6 prototype demonstrated
that a DEFERRABLE INITIALLY DEFERRED constraint trigger can reject an incomplete
rebalance at COMMIT while allowing the complete multi-row transaction. Immediate
finalized-row immutability stayed enforced. The corrected Decimal-only proof passed;
an initial test assertion compared Decimal against float and was corrected. No live
database was involved.

Existing supported multiple allocations against the same RETURN remain allowed.
No uniqueness constraint on (credit_note,return_movement) was introduced.

## Additive schema

`invoicing/0004_credit_reservation_schema` depends on invoicing0003, requests_app0017
and the swappable user model. It adds:

- CreditNote.creation_operation_token: independent nullable unique UUID, no token
  backfill/default; legacy NULLs remain NULL. New supplied tokens must match their
  attributed CREATE operation payload. Future E-C must bind/validate normalized
  request payloads and require tokens for its own new creation requests.
- CreditNote.reservation_revision, reviewed_revision, reviewed_by, reviewed_at,
  review_operation. New revision metadata starts unreviewed; no historical review
  or human confirmation is invented.
- CreditAllocation.released_at/release_operation with a paired-null constraint.
  Active reservations have both NULL. Release retains the original positive
  quantity, amount, price, identity and description; released rows are frozen.
  There is no expiry, delete workflow or operational release method.
- CreditOperation: append-only UUID, original invoice, active responsible actor,
  kind, reason, payload, DB-stamped transaction identity/time. Kinds support future
  CREATE, RESERVE, REBALANCE, RELEASE, REVIEW and FINALIZE operations.
- CreditReservationAudit: database-generated append-only allocation/operation,
  previous/new amount and quantity, and timestamp. Actor/reason/kind are retained
  in its protected append-only operation. New/released reservations are audited
  too; release is represented as zero active quantity/value without destroying
  original allocation evidence.
- `finalize_creditnote` model permission. Normal view/add/change permissions remain
  distinct. No existing user, group or role receives any permission automatically.

No extra copy of invoice/material/company columns was added. Existing snapshot JSON
and original finalized fields provide financial history; original invoices are not
edited. All previous migrations remain unchanged.

## Credit-only database guards

`invoicing/0005_credit_financial_guards` depends on0004. It leaves
inv_document_guard()/inv_child_guard() and their invoice/line/issue/exclusion trigger
bindings untouched. It replaces only the credit header/allocation trigger bindings
with separate functions, plus operation/audit and deferred ledger guards.

Immediate checks protect:

- READ COMMITTED financial writes and attributed current-transaction operations.
- Original finalized invoice, matching currency and explicit Africa/Kinshasa timezone.
- Parent/creation identity; no credit reassignment or alteration of creation actor/time.
- RETURN type/positive quantity, original request/material/positive OUT, post-invoice
  timing, no future return timestamp and no pre-invoice RETURN exclusion.
- Frozen price and cumulative RETURN/net-invoice quantity caps, counting all active
  drafts and finalized allocations, excluding the current allocation correctly.
- Finalized/released allocation immutability and evidence deletion prohibition.
- Database-generated audit insertion; audit/operation UPDATE/DELETE are forbidden.

Deferred validation checks the complete invoice credit ledger at COMMIT. It verifies
parent/currency attribution, cumulative money, current source consistency, quantities,
RETURN caps, unique source OUT/item, gross-issued quantity versus frozen net plus
exclusions, and any populated credit header total. A stale partial rebalance aborts
the transaction, including its monetary changes, audit rows, revision changes and
synthetic finalization/reference registry insertion. No automatic rebalancer is hidden
inside a trigger: future E-C performs the multi-row changes; guards only audit,
invalidate review and validate them.

## Cumulative rounding and reservations

For each original invoice issue allocation, order active allocations explicitly:

1. FINALIZED credits by DB-stamped finalized_at, credit ID, allocation ID.
2. DRAFT credits by credit ID, allocation ID.

Let Q be cumulative quantity, P the original frozen unit price, T the original frozen
line total, and V the preceding allocated amount. Each expected incremental value is:

`min(T, ROUND_HALF_UP((Q + quantity) * P, 2)) - V`

Then increase Q and V. Quantity cannot exceed original net billing or eligible RETURN
evidence. Values cannot be negative or exceed the original line cap. PostgreSQL
numeric round(value,2) matches Decimal ROUND_HALF_UP for the nonnegative domain.
Finalized values remain frozen; drafts reserve the remaining quantity AND money.
Released allocations are retained but do not reserve active capacity.

Three units at0.0050 have original total0.02. Three successive one-unit allocations
are0.01,0.00,0.01, including when finalized. Positive quantity with zero amount is
valid. Finalizing a later draft first may change its amount and other drafts' amounts;
all affected active reservations must be updated in the same transaction. A release
that shifts remaining draft amounts likewise requires a complete atomic rebalance.

Every allocation amount/quantity/snapshot adjustment inserts an audit row and increases
its draft's reservation_revision, clearing prior review fields. Client-written revision
increments are prohibited. An explicit REVIEW operation binds the actor and exact
current revision/allocation payload; no trigger automatically confirms a review.
FINALIZE requires that unchanged proof. Any updated monetary reservation must be
explicitly reviewed again before finalization; no stale review can silently authorize it.

## Locking contract for E-C

Creating CreditOperation acquires a transaction-scoped advisory coordinator lock for
the original invoice, BEFORE row updates. All credit writes require an operation from
that same transaction/invoice; an old committed operation cannot be replayed. Hash
collisions would only serialize unrelated operations conservatively.

Future E-C must begin an atomic transaction and create its attributed operation before
taking financial row locks. The established row order remains CreditNote → original
Invoice → RETURN; multiple credit/RETURN rows should be locked in stable ID order.
The coordinator prevents two rebalancers from each holding one draft while waiting
for the other. Manual callers that take row locks before obtaining the coordinator
can still deadlock and be rolled back; this is not a supported future service order.

The CREDIT sequence is locked last during a future issuance operation. Any additional
request lock needed for a service-level evidence snapshot must follow the invoice and
precede RETURN locks. No material/inventory lock or stock-service change was introduced.

Deferred validation permits temporary monetary inconsistency inside an atomic operation,
never a committed inconsistent ledger. Quantity ceilings and finalized immutability
remain immediate. SET CONSTRAINTS ... IMMEDIATE may be used as an explicit validation
barrier; partially updated money cannot pass it. Concurrent transaction tests verify
coordinator blocking and rejection of the losing over-reservation.

## Snapshot and finalization preconditions

New final credits require snapshot_version2 and rounding policy
CREDIT_CUMULATIVE_HALF_UP_2_V1. Company, succursale, branding, request reference and
currency must exactly match the original immutable invoice. Credit metadata contains:

```
credit_snapshot = {
  version: 1,
  invoice_number: original.number,
  invoice_issue_date: original.issue_date as ISO date,
  invoice_rounding_policy: original.rounding_policy,
  invoice_snapshot_version: original.snapshot_version
}
```

Each active allocation preserves the original description and validated line_snapshot
metadata (version1, original material code, unit and rounding policy), plus the frozen
price. Totals must equal active allocation sums; French words must be present. E-C
must generate those words using the existing tested converter; E-B does not implement
an issuance service or a PostgreSQL French-language converter.

Credit finalization uses the separate verified CREDIT sequence and global financial
reference registry, DB time and current Kinshasa business date/year. No backdating or
silent annual sequence creation is allowed. Existing invoice numbering remains intact.
Tests set explicitly synthetic references/counters as schema fixtures; they do not
implement or exercise a business credit-number allocator.

## Migration safety and historical compatibility

0004 adds schema/default revision metadata only; it does not invent credit amounts,
actors, relationships, prices, tokens, reviews or classifications.0005 evaluates
existing credit ledgers transactionally without rewriting them. An incompatible
legacy rounding ledger causes migration failure and DDL rollback, requiring separate
review; there is no automatic repair. Historical finalized records are not resnapshotted.
Compatible legacy drafts keep their values and NULL tokens; future finalization must
satisfy the new explicit review and snapshot requirements.

Synthetic tests compare source requests/items/movements/materials, credit values and
invoice fields before/after migration, including an unrelated zero item/OUT and a
NULL-token RETURN. The original invoice guard function definitions are identical.
Tests also deliberately reject legacy3×0.01 credits against an original0.02 line.

Measured locks include AccessExclusiveLock on altered credit tables, index-creation
locks and FK-related locks on referenced financial/user tables. Trigger creation uses
financial-table locks; this is not lock-free deployment. The retained SQL/lock report
lists exact relations/modes. A future authorized deployment needs a short lock timeout,
statement timeout appropriate to the inspected ledger size, active-transaction review,
verified backups and a retry plan. Disposable timings are not production guarantees.

Schema-only reversal/reapplication is rehearsed with no E-B operation/audit evidence.
Guard reversal explicitly refuses once that evidence exists. Removing guards or dropping
financial evidence after real credit issuance is not a safe production rollback; use
reviewed forward corrections and a verified restore plan. No production migration or
production historical-data assessment was performed.

## Validation, language and limits

New model labels, operation choices, permission text and model validation use Django
i18n. French PO/MO additions preserve existing entries and UTF-8. Runtime tests check
French/English labels and validation, not only catalogue compilation. PostgreSQL guard
errors remain technical diagnostics; E-C must map failures to localized application
messages while enforcing actor/object permissions and explicit signed confirmations.

The schema attributes an active actor but is not an application authorization service.
Future E-C must enforce designated stock-review scope or explicit administrator access,
separate action permissions, creation-token payload binding and review forms. Nothing
is exposed through new views/admin/endpoints in E-B.

DB owners can disable guards/TRUNCATE and privileged filesystem/stock SQL remains an
external limitation. Runtime/migration-role separation and production privilege review
are still required. Financial checks run on financial writes; no stock-table triggers
were introduced. Timestamp uncertainty fails conservatively; production clock/provenance
and legacy stock reconciliation are separate outstanding requirements.

Deferred checks currently validate the invoice ledger for each queued event; E-C/E-F
must assess realistic batch sizes and lock durations before operational deployment.
Private storage, approved no-logo PDFs, request-reference handling, stock returns,
approvals, resubmission, invoice pricing/finalization and previous migrations are unchanged.

## Exact file manifest

Modified:

- invoicing/models.py
- invoicing/tests.py (schema fixtures adapted; existing assertions retained)
- locale/fr/LC_MESSAGES/django.po
- locale/fr/LC_MESSAGES/django.mo

Created:

- invoicing/migrations/0004_credit_reservation_schema.py
- invoicing/migrations/0005_credit_financial_guards.py
- invoicing/test_credit_guards.py
- invoicing/test_credit_migrations.py
- local_artifacts/test_eb_probe.py
- local_artifacts/test_checkpoint_eb_probe_runner.py
- local_artifacts/test_checkpoint_eb_runner.py
- local_artifacts/checkpoint_eb_guard.json
- local_artifacts/checkpoint_eb_translations.py
- This report and retained nonsensitive evidence listed below.

No dependencies were installed. Existing tracked/untracked work is preserved.

## Final recorded results

| Verification | Run | Passed | Failed | Errors | Skipped | Seconds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pre-implementation deferred-commit proof | 1 | 1 | 0 | 0 | 0 | 0.610 |
| Focused financial/schema/migration suite | 60 | 60 | 0 | 0 | 0 | 83.584 |
| Complete regression suite, final source | 344 | 343 | 0 | 0 | 1 | 463.157 |

The sole skip is the existing opt-in local sample-generation test. E-B adds24 tests:
21 focused guard/concurrency cases and3 migration cases. Existing B credit schema
fixtures were updated to provide operation attribution/review/snapshots while keeping
their regression assertions. A new SQL alias/record collision was caught in an
intermediate focused run and fixed before the successful focused/full runs.

All runs use fresh disposable PostgreSQL18.6 clusters. The final full suite used
127.0.0.1:15499, database test_microcom_checkpoint_eb, role microcom_checkpoint_eb_test,
and an independently checked unique workspace data directory/postmaster identity.
The normal repository .env was never loaded. No existing staging, development, shared
or production database was connected. This is not exact PostgreSQL18.4 verification.

Final synthetic migration timings:0004 **1.2531635 seconds**;0005 **0.1648933 seconds**.
Application, compatible legacy-data preservation, schema-only reversal/reapply,
incompatible-ledger rejection and evidence-bearing reversal refusal all passed.
Original invoice trigger function definitions and protected source/migration hashes
match the pre-E-B baseline. System checks, dry-run migration consistency, French model
catalogue checks and whitespace checks passed. No credit UI/PDF/lifecycle coverage
or historical production reconciliation is claimed.

Evidence: `local_artifacts/checkpoint_eb_evidence_2f8dd125/` contains:

- full-suite-results.json
- focused-results.json
- preimplementation-proof.json
- checkpoint-eb-migration-results.json (exact SQL, timings and observed locks)
- Existing B/C/Stage1/Stage2 migration regression reports
- verification-summary.json
- cleanup.json and port-checks.json

Every started cluster was stopped successfully by pg_ctl and its test database
dropped. Eight explicitly identified checkpoint-created directories were removed
after absolute-workspace-path, reparse-point and absent-postmaster-PID checks.
Exclusive localhost binds verified temporary ports15492–15499 free. Existing services
and staging55440 were untouched; only nonsensitive evidence was retained.

Recommendation: **GO for Checkpoint E-B review**. E-C requires separate approval.
Its remaining work includes scoped authorization, signed explicit review/confirmation,
transactional creation/rebalancing/release/finalization services, localized failure
handling, annual CREDIT sequence verification and operational capacity testing.
No commit, push, deployment or production access occurred. Stop here.
