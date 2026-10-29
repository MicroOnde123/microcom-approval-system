# Invoice finalization statement-time correction

The confirmed PostgreSQL guard `finalization_timestamp_window` rejects the
previous timestamp when validation/network delay exceeds five seconds.

## Flow and correction

`_issuance_sequence()` locks the verified annual scope, validates it and samples
`clock_timestamp()` for the business date/year. Before the invoice UPDATE, the
sequence's `save()` and invoice's `save()` perform immutability and `full_clean()`
queries (foreign keys, uniqueness and constraints). Thus there are two model save
paths, each with multiple SQL operations, after that time sample. Exact round-trip
counts vary with validation/data and were not measured against a database.

The service now opts into `_finalize_at_statement_time=True` on the existing
invoice save. The option is restricted to existing finalized-state Invoice
instances. All existing immutability checks and concrete-field validation run
first. Immediately before Django's normal persistence path, the timestamp value
is replaced with `Now()`, which Django compiles to PostgreSQL
`STATEMENT_TIMESTAMP()` inside the UPDATE itself. No earlier SELECT or Windows
clock determines the submitted timestamp. Other saves remain unchanged.

- `transaction_timestamp()`/`CURRENT_TIMESTAMP` freeze at transaction start and
  may be stale after a long transaction.
- `statement_timestamp()` is the start time of this UPDATE and matches the
  trigger's comparison baseline, independent of earlier round trips.
- `clock_timestamp()` is actual PostgreSQL wall-clock time. The unchanged trigger
  persists this after checking the five-second window.
- Django `timezone.now()` uses the application clock and would retain both
  clock-skew and round-trip risks.

The original `moment` remains solely as a concrete model-validation value before
the expression substitution. The service refreshes the invoice after UPDATE, so
audit/returned values use the database's actual persisted timestamp.

## Preserved safeguards

No migration/trigger change. The five-second guard, company/stock/allocation
guards, READ COMMITTED requirement, sequence lock, unique official reference,
counter increment, prices/rounding and permission checks remain unchanged.
The same atomic transaction contains every financial write. Diagnostics and the
generic EN/FR error remain unchanged.

Business date/number/year still come from the locked sequence selection. Crossing
local midnight or year-end before UPDATE can intentionally fail the trigger's
date/year check and roll back. No date/sequence is silently switched and no
automatic retry is added. Existing request/sequence locks retain their ordering.
Long lock waits do not age a statement timestamp relative to itself; the trigger
still uses its actual clock timestamp for the date check and persisted value.

## Verification and remaining work

Offline tests cover delayed validation handoff, actual PostgreSQL UPDATE
compilation without a connection, unchanged ordinary saves, immutable/invalid
state rejection, business timezone/year-boundary behavior and post-save refresh.
Deferred PostgreSQL tests cover validation lasting more than five seconds,
date mismatch/counter/reference rollback, and failure after header persistence.
Existing concurrency, direct-SQL backdating, numbering and lifecycle regressions
also remain required on a separately authorized isolated test database.

No database/network access or controlled retry is part of this implementation.
After review, a separately authorized development retry can verify the correction
with sanitized diagnostics and subsequent read-only integrity checks. That is
development verification, not a substitute for full database regression coverage.
Keep `MATERIAL_RETURN_NOTE_UI_ENABLED=False`.
