# Checkpoint E-R1 — Internal material return-note database foundation

Local schema and guards only. Factures remain internal material valuation
documents. No issuance, preview, confirmation, numbering allocator, UI, PDF,
download, email or credit lifecycle service is implemented.

## Preflight and approved ledger policy

Reviewed B/C/D/E-B documentation, actual models, stock services, financial
functions, reference registry, sequence guards, private artifact ownership and
test conventions. E-B migrations 0004/0005 and their function definitions remain
unchanged. A separate preceding trigger adds credit-allocation exclusivity.

Approved invoice-level exclusivity avoids independently rounding two different
RETURN movements in separate ledgers above the original facture value.
Active credit allocations include draft reservations and finalized allocations;
released allocations remain historical evidence without reserving quantity.
Return-note financial construction is rejected while active credits exist.
Once a return-note header exists, new active credit allocations are rejected,
including allocations using a different RETURN or material on that facture.
No credit reservation is released, converted, deleted or backfilled.

## Schema

- MaterialReturnNote inherits the existing financial header conventions and links
  the finalized original facture, append-only issuance audit, nullable unique
  operation token, sequence/counter, immutable original snapshots and human-readable
  request-reference snapshot. Original total is frozen as an exact decimal string
  in original_invoice_snapshot; numeric monetary columns remain Decimal/numeric.
- MaterialReturnNoteLine protects its original issue allocation and has a unique
  RETURN relationship. Entire positive movement quantities, frozen codes,
  descriptions, units, prices and computed values are required.
- MaterialReturnNoteAudit is append-only attribution: UUID, original facture,
  active actor, nonblank reason, payload and DB-stamped transaction/time.
  A supplied issuance token must match the operation payload. Unused attempt
  audits can remain; they cannot authorize a later transaction.
- MaterialReturnNoteArtifact has a dedicated protected note owner. It retains
  language, rendering version, opaque file reference/checksum and rendering
  status. It is append-only and requires an issued note. This supplies ownership
  metadata only: existing invoice download/rendering endpoints remain unchanged.
- Default view/add permissions and explicit issue/document-view permissions are
  metadata only. No permissions are granted. E-R2 must implement object scope.

No persistent monetary drafts are supported: DRAFT is a transaction-local
construction state. Deferred checks require nonempty FINALIZED notes before
commit. An operation is created before building header/lines and completing the
finalized snapshot in the same transaction. This is a schema protocol, not an
operational issuance API. Schema fixtures manually supply synthetic references;
no return-note numbers or sequence counters are automatically allocated here.

## Locking and exclusivity

READ COMMITTED is mandatory. Return-note audit INSERT obtains precisely the
existing E-B advisory transaction lock:

`hashtextextended('microcom.credit:' || invoice_id, 0)`

Supported order: invoice coordinator first, then original invoice/request and
return-note rows; selected RETURN rows in deterministic order in E-R2; sequence
last. E-B already obtains the coordinator at CreditOperation insertion before
credit row locks. The new aa_rn_credit_exclusive allocation trigger runs before
the existing inv_creditallocation_guard, requires the existing current-transaction
E-B context, and checks the other ledger. It does not replace or weaken E-B
validation, auditing, review invalidation or deferred monetary checks.

The SQL functions are volatile. Their reads after a coordinator wait see newly
committed evidence under READ COMMITTED. The pre-implementation PG18.6 prototype
proved waiting and rejection in both directions before application files changed.
Actual-table regression tests repeat both races and serialize two notes.

Future services must create attribution before locking document rows. Taking
arbitrary locks before the protocol can still deadlock; PostgreSQL aborts a
participant rather than committing conflicting evidence. E-R2 needs deliberate
retry handling and confirmation-payload binding.

No triggers are added to StockMovement or Material. These restrictions affect
financial documentation only. Existing stock-return services remain authoritative
for stock increments and their own retry tokens.

## Provenance, rounding and frozen values

Validation requires a finalized original facture, whole positive post-finalization
RETURN evidence, matching request/material, unique consistent positive OUT and
request item, no pre-invoice exclusion, consistent original net/exclusion totals,
and no historical over-return. Ambiguous or zero historical evidence blocks
documentation without repairing or changing stock records. Timestamp evidence
uses existing RETURN timestamps; clock-skew ambiguity is not silently inferred.

For each original issue allocation, order notes by DB finalization time, note ID,
then line ID. With Q/V the preceding documented quantity/value, P the frozen
price and T the original frozen line total:

`increment = min(T, ROUND_HALF_UP((Q + quantity) * P, 2)) - V`

Quantity cannot exceed original net-valued quantity. Positive quantities with
zero monetary increments are valid. Each note total equals its line sum;
cumulative returned value and adjusted net value are verified at commit against
the immutable original total. Old note totals remain issuance-time snapshots.
Current catalogue prices never participate.

## Migrations, locks and reversal

- 0006_material_return_note_schema depends on invoicing0005, requests_app0017
  and the swappable user model. Adds four tables, constraints/indexes/FKs and
  RETURN_NOTE sequence choice; widens sequence document_type to 11 characters.
- 0007_material_return_note_guards depends on0006. Adds separate guards and
  extends the shared immutable reference registry to RETURN_NOTE, retaining its
  global number primary key. A verified annual sequence is required, business
  date/year uses Africa/Kinshasa and DB time, and backdating is rejected.
- Guard installation validates any existing return-note ledger and fails closed
  on conflicts/incomplete or inconsistent evidence. No repair is performed.
- DDL takes PostgreSQL table locks. New FK creation locks referenced tables;
  registry ALTER/constraint replacement and sequence alteration can require
  ACCESS EXCLUSIVE locks. Reference constraint validation scans existing rows.
  Small disposable timings are not production timing guarantees. Capture real
  migration SQL, use a reviewed maintenance/lock-timeout policy and deploy both
  migrations before enabling future functionality.
- 0007 reversal is intentionally refused if return-note audits, headers or
  RETURN_NOTE sequence configuration exist. Empty foundation reversal/reapply
  is tested. After business evidence exists, use a reviewed forward correction,
  not migration rollback or deletion. E-B reversal restrictions are preserved.

## Validation and remaining boundaries

Evidence is retained under local_artifacts/checkpoint_er1_evidence. Tests use only
fresh localhost PostgreSQL18.6 clusters with verified data directory, role,
database, version and port before writes. Credential-free disposable settings
reuse staging settings declarations without loading staging.env.json or the
normal .env. Email is local-memory, media/static/private roots are disposable.

Focused suite: 88 passed, 0 failed, 0 errored, 0 skipped (128.395 seconds).
Final full suite: 372 run, 371 passed, 0 failed, 0 errored, 1 skipped
(266.746527 seconds). The skip is the existing opt-in stock-report sample
generator. The clean final launcher run also checked migration consistency.
All 146 literal model translation messages are present in the French MO
catalogue; runtime English/French label and validation tests passed.

Final disposable migration timings: 0006 0.677311 seconds, 0007 0.118449 seconds.
Source preservation, legacy zero/NULL-token preservation, unchanged E-B/invoice
function definitions, empty reversal/reapply, evidence-bearing reversal refusal
and conflict preflight rollback passed. See the retained JSON for exact SQL and
observed locks. These small synthetic timings do not predict production runtime.

Intermediate fixture errors (missing price currency and an inconsistent reserved
amount) were corrected in new tests only. An initial credential-free launcher
omitted localhost ALLOWED_HOSTS and caused HTTP400 regression failures; the
launcher was corrected before the passing full runs. Windows DROP DATABASE
teardown stalled in intermediate runs. The final launcher keeps only its fresh
disposable test database until cluster cleanup; its clean full test process
exited successfully. This does not reuse any existing staging/development DB.
Cleanup uses fresh process/data-directory/port/start-time checks and retained
process handles, followed by path/reparse-point/free-port/unlocked-log checks.
An earlier stale-parent-PID cleanup proposal was rejected by automatic review;
no termination used that proposal. Fresh ownership checks and a file-only
cleanup alternative resolved cleanup without touching existing services.

This is same-major compatibility; it is not exact PostgreSQL18.4 verification or
production-data reconciliation. Full evidence, file hashes and cleanup status
are retained under local_artifacts/checkpoint_er1_evidence.

Direct SQL by database owners/superusers can disable triggers or TRUNCATE tables.
Existing stock rows do not gain new universal update immutability. Production
privilege review, historical balances and opening-balance reconciliation remain
separate requirements. E-R2 must add explicit object authorization, mandatory new
issuance tokens, normalized payload binding, stale-preview rejection, safe
number allocation and retry behavior. Protected artifact generation/download and
bilingual PDFs remain later checkpoints. No stock, request, approval or invoice
lifecycle services were changed.
