# Checkpoint E-R2 — Material Return Note issuance services

Bon de retour is an internal valuation of returned materials against a finalized
internal facture. It is not a credit, refund, payment adjustment or stock operation.
This checkpoint adds services, authorization and regression coverage only. No
views, URLs, templates, PDF rendering, artifact generation or E-R3 functionality.
No schema migration is required; migrations 0001–0007 remain unchanged.

## Service contract

`invoicing.return_note_services` provides:

- `eligible_return_movements(invoice_id, user)`: authorized eligibility with
  translated exclusion reasons. No reservations or writes.
- `preview_material_return_note(invoice_id, user, *, return_movement_ids, reason,
  series="MAIN")`: in-memory lines, frozen snapshots, totals and signed confirmation.
- `issue_material_return_note(invoice_id, user, *, return_movement_ids, reason,
  series="MAIN", issuance_token, confirmation)`: one committed immutable note,
  or exact replay of that same committed issuance.
- `get_material_return_note(note_id, user)`: authorized finalized-note retrieval.

Selections must be nonempty distinct positive integer movement IDs. The service
accepts no caller-provided quantity, price, currency, total, date or number. It
normalizes reason/series whitespace and selection order. Reason is mandatory
and at most 2000 characters; series is mandatory and at most 30 characters.

The confirmation expires after two hours for a new issuance. It binds actor,
invoice, normalized inputs, new UUID token, evidence/ledger digest, exact proposed
valuation and business date. A committed replay must present the original
confirmation and identical normalized inputs; it can succeed after expiry but
always rechecks current authorization. New UUIDs cannot reuse old confirmations.
Historical NULL issuance tokens remain untouched; every new service issuance
requires a token. Preview creates no persisted audit, editable draft or number.

## Authorization

All service actors must be authenticated, active staff. Fresh database user and
permission state is used, avoiding caller permission caches.

- Read: `view_invoice` and `view_materialreturnnote`.
- Eligibility/preview: additionally `issue_materialreturnnote`.
- Issue/replay: additionally `issue_materialreturnnote` and
  `add_materialreturnnote`.

Existing stock-review object scope is reused: primary reviewer, alternate reviewer
or acting reviewer for an approval marked as requiring stock classification.
Staff with `manage_all_invoices` have cross-assignment scope; active staff
superusers retain their permission behavior. Stock capability or later approval
participation alone does not grant access. No permissions/groups are granted.
Existing invoice authorization is unchanged. Protected document-view permission
remains reserved for future artifact functionality.

## Eligibility and valuation

Only whole positive RETURN movements strictly after `invoice.finalized_at` and
not in the future are eligible. Each must match the original request/material,
unique positive OUT and request item, invoice issue allocation and pre-invoice
exclusions. Historical zero/negative, duplicate or over-returned provenance fails
closed. A NULL stock-operation token is accepted only with otherwise unambiguous
provenance. No historical stock movement is repaired or backfilled.

Each selected movement becomes one line, in ascending movement-ID insertion
order. A movement cannot be split or documented twice. Multiple movements and
materials can be selected. Frozen facture prices/currency/code/description/unit
and original company/branch/branding/reference snapshots are copied. Current
catalogue prices and company configuration do not affect valuation.

For each original issue allocation, with prior documented quantity Q/value V,
frozen price P and original line total T:

`increment = min(T, ROUND_HALF_UP((Q + quantity) * P, 2)) - V`

Calculations use Decimal with explicit high precision and HALF_UP. Quantities
cannot exceed the original net-valued allocation. Positive quantities can have
zero monetary increments, including explicitly zero frozen prices. Totals and
cumulative values cannot exceed the original invoice total. The original facture
remains FINALIZED and unchanged even when adjusted net material value reaches zero.
Existing notes retain their issuance-time cumulative snapshots.

## Transactions, exclusivity and numbering

Preview/eligibility/issuance require an outermost READ COMMITTED transaction.
Issuance returns success only after deferred guards commit. Ambient transactions
are rejected to avoid savepoint success followed by later outer commit failure.

Lock order: existing `hashtextextended('microcom.credit:' || invoice_id, 0)`
advisory transaction coordinator; original invoice; request; prior note headers
in primary-key order; selected RETURN rows in primary-key order; annual sequence
last. E-R1 attribution is inserted before new header/line construction. The
coordinator is obtained before financial row locks, including during preview.

Current permissions, provenance, ledger state, confirmation and calculations are
revalidated inside issuance. E-R1 SQL guards and deferred validation remain
authoritative. Active allocations on any credit on the invoice block issuance,
including reservations against different RETURNs/materials and finalized credits.
Released allocation history is preserved. A return-note header blocks new active
credit allocations through the existing E-R1 trigger.

The existing annual RETURN_NOTE sequence must already exist and have a valid
administrator attestation/digest. No sequence is auto-created or verified. Number
allocation locks the sequence, checks bounds and database business date/year,
increments its counter, registers the globally unique reference and finalizes
in the same transaction. Business calendar is Africa/Kinshasa per E-R1, independent
of the caller's language/timezone. Number collisions abort without skipping ahead.

Any failure rolls back the new audit, note, lines, reference and counter together.
Deadlock/serialization SQLSTATEs alone receive up to three complete attempts with
the same token/confirmation. Other failures require review or a fresh preview.
Retries do not release/convert credits or modify stock. Failed attempts leave no
issuance audit; durable operational failure logging is outside this checkpoint.

## Bilingual behavior and boundaries

All new service/authorization messages use gettext and have French translations.
Financial confirmation content is language independent. French amount wording is
persisted using the existing exact-money helper; English/French display of other
data remains the responsibility of later presentation layers. No source text is
machine-translated or current material descriptions substituted during issuance.

Timestamp/cross-record provenance cannot reconstruct clock-skew ambiguity. Owners
and superusers can bypass triggers through privileged direct SQL. E-R2 does not
add universal stock-row immutability, production reconciliation or deployment.
Validation uses disposable PostgreSQL18.6, not exact18.4 verification.

## Validation evidence

**Status as of October 27, 2026: code reviewed and corrected statically;
E-R2 database validation is incomplete. E-R2 is not declared complete.**

The initial October 26 disposable run recorded 36 tests: 13 passed, 4 failed,
19 errors, 0 skipped. Its passing subset does not validate the corrected code.
The E-R1 checkpoint's earlier passing full suite predates E-R2 and is not an
E-R2 regression result. Original evidence remains unchanged under
`local_artifacts/checkpoint_er2_evidence`, including `interrupted-status.json`.

The disposable cluster was last verified running in recovery diagnostics at
localhost15521, under
`local_artifacts/microcom-checkpoint-er2-tests-ce8a1a8ddede44e08fec03972e62f610`.
Its cleanup is incomplete. Restricted Windows tokens deny write access to the
signal pipe despite the matching account; the original launcher's automatic
cleanup failed. That launcher must not be treated as a verified cleanup path.
No cluster/process status was queried and no database/cluster operation was
performed during this static review. No tests or migrations may run under the
current development-only authorization. Recovery and safe future test execution
require separate authorization; no automatic fallback termination is permitted.

### Static corrections

- Retain and review the header `refresh_from_db()` immediately after INSERT:
  E-R1 stamps `created_at` in SQL, so finalization must use that exact value.
  A dedicated pending regression asserts equality with the stored timestamp.
- Correct the numbering collision fixture to create a separate verified
  `COLLISION` series starting at one, rather than illegally reducing MAIN from
  seven to one. Its confirmation binds to that series. Both counters are checked
  after the expected rollback.
- Recheck fresh authorization after waiting for request/prior-note locks, also
  covering committed replay. Final issuance separately rechecks authorization
  and confirmation age after waiting for the numbering sequence.
- Reject malformed confirmation objects and out-of-range/bool IDs with translated
  errors; verify signatures through one shared helper. Committed replay alone
  bypasses the two-hour age limit, retaining exact payload/actor binding.
- Translate missing issue-allocation provenance into the existing fail-closed
  validation message; check pre-invoice exclusions across the whole exclusion
  ledger, consistent with E-R1's SQL guard.
- Translate database failures in eligibility listing, aborting the whole result
  rather than leaking raw SQL or returning a partially assessed list.
- Keep deferred-failure injection after finalization, so the new timestamp reload
  cannot move that regression's corruption into the construction stage.

### Database-free checks actually performed

`local_artifacts/checkpoint_er2_static_review.py` compiles source without importing
application services/models. It extracts only named pure helpers from the AST,
uses an explicit synthetic signing key, and never configures Django or imports
`django.db`. It checks input normalization/bounds, malformed confirmations,
Unicode signed payloads, age rejection and canonical digest ordering. These are
isolated helper checks, not issuance or database integration tests.

Recorded in `local_artifacts/checkpoint_er2_static_review_20261027.json`:

- Six Python files compile; 39 isolated helper checks pass.
- All 19 literal service/permission messages have nonempty French translations
  matching between PO and MO. No new strings were needed for these corrections;
  the catalogues were read and preserved.
- Static write receivers are restricted to new note/audit/line construction,
  the note header and the annual sequence. No stock-operation imports exist.
- Existing checkpoint baseline hashes differ only for the already-approved
  permissions module and French catalogues. Existing models, migrations, stock
  workflows and invoice services remain unchanged.

### Outstanding database validation

There are 42 E-R2 service/concurrency test methods awaiting an authorized run.
All database-dependent behavior remains unverified after these changes:

1. Timestamp identity, finalization, deferred checks, audit attribution and exact
   rollback of note/lines/reference/counter; real deadlock/serialization retries.
2. Missing/unverified/colliding/overflow numbering, shared annual sequence races,
   and business-day/year rollover. The corrected collision fixture is unexecuted.
3. Complete movement eligibility, strict cutoff, legacy NULL tokens, ambiguous
   historical source data and cross-invoice/material rejection.
4. Frozen snapshots/currency/prices, fractional cumulative HALF_UP rounding,
   zero-price/zero-increment returns, quantity/value caps and multiple materials.
5. Both credit race winners and invoice-wide active-allocation exclusivity;
   preservation of released credit history.
6. Current staff/action/object authorization, revocation during lock waits,
   malformed/stale/expired/cross-user confirmation and exact committed replay.
7. Same-token, overlapping and disjoint issuance races; concurrent stock returns;
   original facture/request/approval/stock/credit preservation.
8. Runtime Django English/French validation/authorization paths, E-R1/E-B
   regression suites, the full suite and migration consistency checks.

Further boundary coverage still needs to be added for exact counter overflow,
expiry during a sequence-lock wait, unsupported isolation at the public service
boundary, and cross-material credit exclusivity at the service boundary. Existing
E-R1 schema tests do not substitute for executing E-R2 services in those cases.

Static inspection agrees with the existing E-R1 lock key, deterministic selected
movement/line order, whole-movement uniqueness, frozen valuation formula and
deferred caps. This is not empirical proof of concurrency or preservation. No
schema migration, UI/PDF feature or E-R3 work was added.
