# Succursale address and future invoice snapshots

Implemented locally; no database migration or database-dependent test was run.

## Behavior

- `inventory/0004_succursale_physical_address` adds one blank-compatible text
  column. Existing IDs, relationships and values remain intact; no address is
  inferred. Reversing this migration after entry would discard address data.
- Admin uses a multiline widget. Model validation requires an address on new
  records and permits existing blank records to be edited. ORM/script callers
  must use `full_clean()` as usual; bulk/SQL writes bypass model validation.
- Finalization locks the branch and checks a stripped nonblank address before
  line writes or numbering. Existing draft invoices require the branch address
  to be completed before finalization. Finalized replay remains read-only.
- The existing JSON branch snapshot captures `physical_address`. Detail and v3
  PDF rendering read only that snapshot. Legacy snapshots without an address
  remain valid; no current-address fallback or historical backfill is used.
- Existing append-only PDF artifacts/checksums remain untouched. New renditions
  use the incremented renderer version; original downloads remain available.
- Return-note issuance still copies the entire original branch snapshot, so an
  address is retained without following the live branch. No return-note workflow,
  route, renderer or activation setting was changed.
- Stock classification, authorization, stock movements, rounding, pricing and
  reference formats are unchanged. Five new messages have French translations.

## Validation

Run only the dedicated database-free harness:

    .\venv\Scripts\python.exe local_artifacts/test_succursale_address_offline.py

It uses synthetic settings with no database and blocks network/DB connections.
It covers new/legacy model and generated-admin-form validation, bilingual escaped
multiline PDF and HTML rendering, legacy PDF support, template compilation,
translations, migration/model state consistency, and source-level preservation
checks. Those source checks do not establish actual transaction behavior.

Latest database-free result: 12 passed, 0 failures/errors. Thirteen changed/new
Python files compile. One invoice template compiles; migration/model state has
no detected differences. No application settings or database were loaded.

Pending isolated PostgreSQL tests: `inventory.test_address_migration`,
`invoicing.test_succursale_address`, updated `inventory.test_stage1`, existing
invoice lifecycle/documents/guards and `invoicing.test_return_note_services`.
Verify migration preservation, permission behavior, rollback/counter identity,
immutable finalization and return-note snapshot copying under real transactions.
No test database may be created on the Supabase development project.

## Controlled next steps

Review changes and migration SQL; authorize isolated database validation before
running the pending suites. Separately authorize applying inventory 0004 to the
verified development project, with application writes paused and preservation
checks. Before that migration, the new code expects a column that does not yet
exist; do not run normal application traffic using this code against the old
schema. Enter real branch addresses through admin after migration. Keep
`MATERIAL_RETURN_NOTE_UI_ENABLED=False`. No commit or deployment is included.
