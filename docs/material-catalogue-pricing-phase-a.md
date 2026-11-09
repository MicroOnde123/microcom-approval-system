# Audited catalogue pricing — Phase A

`inventory.Material.unit_price` and `currency` remain the only official catalogue
price. Invoice lines and finalized financial snapshots are not updated by this
feature. Unknown price (`NULL`) is distinct from an explicit zero.

## Editing and history

Use Django Admin → Inventory → Materials. Existing-material price or currency
changes require **Price change reason / Motif du changement de prix**. A signed
revision checks both the current values and the latest price-change ID, preventing
stale edits even when a price has been changed and then restored. The existing
stock conflict check remains in place.

The material page links to **Material price history / Historique des prix du
matériel**, a searchable, filtered, paginated, read-only Admin view. Access requires
an active staff account with `inventory.view_materialpricechange` (or superuser).
Editing retains the existing `inventory.change_material` permission; the stock
report permission alone does not grant catalogue editing or history access.

## Persistence and integration

Migration `inventory.0007_materialpricechange` adds one ledger table and PostgreSQL
triggers. It does not backfill history or modify existing material/invoice values.
Initial catalogue values supplied during material creation remain unchanged;
the ledger records subsequent changes, including currency-only and NULL/zero
transitions. No-op saves do not generate ledger entries.

The database compares actual old/new values and inserts the ledger row in the
same transaction. The actor must be active and have the existing material-change
permission, directly, through a group, or as superuser. The ledger stores old/new
price and currency, actor, database timestamp, reason and source. ORM and direct
SQL row mutations/forged inserts into the ledger are rejected.

Future application price writers must use `inventory.pricing.update_price()` with
an expected `price_state()` and a reason. Admin uses the same authorized transaction
context. Uncontextualized updates, including bulk updates, fail at the database.
Stock-only changes and receipt creation retain their existing behavior. Database
owners remain trusted administrators: disabling triggers, truncating tables or
changing schema is outside application authorization.

The follow-up migration `0008_materialpricechange_truncate_guard` rejects ordinary
TRUNCATE statements, including statements by a role accidentally granted TRUNCATE.
It is defence in depth, not protection against an owner disabling the guard. Apply
0007 and 0008 together with the Phase A application code. 0007 is intentionally
unchanged for installations where it has already been applied.

Deploy this migration together with the Admin/service changes. Old open Admin
forms lack price revision evidence and must be reloaded. PostgreSQL permissions
are checked against the existing Django user/group permission tables; custom
authorization backends would require deliberate adaptation.

## Local verification

`config.test_catalogue_pricing_settings` imports only standalone test settings;
it does not load deployment settings or `.env`. It targets loopback PostgreSQL
port 55439 and a dedicated synthetic test database. Verify the cluster identity
and database isolation before running it. Never use it as development-server
settings or point these tests at Supabase.

The tests cover Admin edits/reasons, NULL versus zero, currency changes, stale
revisions, concurrent editors, authorization, ledger immutability, database
rollback and preservation of finalized invoice/document prices.

Persistent receipt drafts, receipt-associated price updates and invoice reissuance
are outside Phase A.

## Deployment approval and database roles

Do not infer database roles from Django's employee permissions. Deployment settings
read `DB_USER` from the environment; this repository does not establish the actual
Supabase login, owner, inherited memberships, default ACLs or PostgREST exposure.
No production role grants, revocations, ownership changes or RLS policies are
automatically introduced by these migrations.

Run the exact read-only queries in `material-price-ledger-inspection.sql` before
approval. Use both the proposed migration principal and the actual Django backend
connection, without sharing passwords. Before 0007, inspect creator default ACLs
and existing material ownership. After application in a controlled window, repeat
the ledger/sequence effective-rights checks before reopening price editing. An
absent ledger before migration is not proof of safe grants. Also inspect Supabase's
API Exposed Schemas setting: SQL-session settings may not reflect the API service's
effective configuration.

The required role plan is:

| Principal | Required access / restrictions |
| --- | --- |
| Migration/ledger owner | Trusted maintenance principal; ideally a separate non-login owner role. Ordinary principals must not own the ledger or be able to assume its owner role. |
| Trusted Django backend | Existing catalogue and authorization reads/writes, plus ledger SELECT and INSERT and sequence USAGE. No ledger UPDATE, DELETE, TRUNCATE or grant option is needed. SELECT supports signed revisions and permission-controlled history. |
| Untrusted API/ordinary SQL principals | No ledger table/column/sequence rights and no route to assume the trusted backend or owner role. They must not inherit those rights through PUBLIC or a group. |
| Approved backup operator | Ledger SELECT only, plus whatever separately approved snapshot tooling requires; restrict access to exported reasons and employee identifiers. |

After actual owners and membership paths are known, a DBA must prepare an atomic,
object-specific ACL change: grant required backend access explicitly; remove
unnecessary rights to this ledger and its sequence from PUBLIC and untrusted
grantees; remove inherited leakage at its actual source. Revoking from a member
does not cancel a parent role's grant. Ownership implies rights that REVOKE cannot
remove; owner separation requires deliberate role/ownership planning. Inspect
column-level ACLs too. Do not revoke schema USAGE, database TEMP, or privileges on
other application tables as a shortcut. Do not make global ALTER DEFAULT PRIVILEGES
changes without reviewing their effect on unrelated future tables. Existing creator
defaults may require a targeted cleanup on this new table/sequence in the same
deployment transaction/window, before exposing it to ordinary clients.

RLS may provide an additional default-deny boundary for API roles in an exposed
schema, but must be coordinated with explicit trusted-backend SELECT/INSERT
policies if the backend is not an owner/BYPASSRLS principal. RLS does not control
TRUNCATE; ACLs and the 0008 guard address that path. Owners and BYPASSRLS principals
are trusted regardless of policies. A new private schema/table move or SECURITY
DEFINER writer would need separate design and testing, and is not silently added.

The current audit trigger is SECURITY INVOKER. Removing backend ledger INSERT or
sequence USAGE, or blocking its authorization-table SELECTs, rolls back legitimate
price updates. The transaction-local employee context is supplied by trusted
application code, not an independently authenticated database identity. In
particular, `pg_trigger_depth()` is an insertion-shape guard, not proof of actor
identity or a security boundary against arbitrary SQL/trigger creation by a role
trusted to INSERT ledger rows. Do not give that access to PostgREST/ordinary client
roles. If direct backend SQL must be treated as hostile, stop and design a separate
restricted writer; this implementation does not claim to solve that threat model.

Deployment remains blocked until this role/exposure plan is reviewed against the
actual query results. No Supabase role configuration is assumed safe from local
superuser tests alone.

## Non-destructive recovery / Récupération sans perte de données

**Do not routinely reverse 0007. Reversing it drops the ledger and permanently loses
its records unless separately preserved. / Ne pas annuler systématiquement la
migration 0007 : cette opération supprime l’historique et entraîne la perte définitive
des enregistrements sans sauvegarde distincte.** Reversing only 0008 removes the
TRUNCATE guard but keeps ledger rows; it weakens protection and is not a routine
application rollback either.

Prefer a forward-fix migration and compatible application patch. First pause price
editing and other price writers, retain receipt/stock services only if their code
and schema remain compatible, and investigate without changing official prices.
Record the code revision, applied inventory migrations, table/function owners,
ACLs, policies and trigger definitions. Never fake/unapply migration records to
make an old code version appear compatible.

Before **any approved migration rollback (including 0008), or destructive schema
recovery**:

1. Keep price writers paused until backup and verification finish, or use a DBA-
   managed consistent exported snapshot for every backup/query. Restrict backup
   files: reasons and employee identifiers are sensitive audit information.
2. Take a complete database snapshot/backup for dependencies and a separate custom-
   format ledger archive, using a PostgreSQL client compatible with the server.
   Use a protected libpq service/password file, never credentials in shell arguments.
   Example commands for the DBA (not executed by this feature):

   ```text
   pg_dump --dbname=service=microcom_backup --format=custom --file=database-before-price-recovery.dump
   pg_dump --dbname=service=microcom_backup --format=custom --table=public.inventory_materialpricechange --file=material-price-ledger.dump
   pg_restore --list material-price-ledger.dump
   ```

   Substitute the schema confirmed by inspection. The table archive is not a full
   dependency backup: material/user references and external functions need the full
   snapshot and recorded schema. Capture and verify sequence state as well as rows.
3. Record counts, ID range and timestamp range while writers are paused:

   ```sql
   BEGIN TRANSACTION READ ONLY;
   SELECT count(*) AS rows, min(id) AS first_id, max(id) AS last_id,
          min(changed_at) AS first_change, max(changed_at) AS last_change
   FROM public.inventory_materialpricechange;
   COMMIT;
   ```

   Save archive checksums with `Get-FileHash -Algorithm SHA256`. Check exit codes
   and the archive listing; a file existing is not proof of a valid backup.
4. Restore the full snapshot into an isolated scratch database, never into Supabase
   development/production for verification. Verify the ledger count/ranges and all
   columns, not just totals. With writers still paused, export the same explicit
   column list from source and scratch in ID order and compare file SHA-256 hashes:

   ```sql
   COPY (SELECT id, material_id, old_price, new_price, old_currency, new_currency,
                user_id, changed_at, reason, source
         FROM public.inventory_materialpricechange ORDER BY id)
   TO STDOUT WITH (FORMAT csv, HEADER true, NULL '\N', ENCODING 'UTF8');
   ```

   Use the same client settings on both connections (`TimeZone=UTC`,
   `DateStyle=ISO,YMD`, UTF-8) and byte-preserving output redirection. NULL must stay
   distinct from zero and empty strings. Check restored owners/ACLs, row/TRUNCATE
   guards and sequence next-value safety using scratch-only tests. Do not disable
   guards or replay ledger INSERTs in the live database merely to test the backup.
5. Only after successful restore verification and explicit recovery approval may a
   DBA plan destructive reversal. Preserve the verified archives and recovery log.
   Keep backups out of Git and out of publicly served storage.

Application compatibility is mandatory: Phase A Admin queries the ledger for
revision evidence and will fail if it is missing. Old code can create materials
and perform stock-only updates, but its existing-material price writes fail while
the audit guards remain. A compatible forward fix should retain table/guards and
audit history. Do not drop the ledger simply to make old price-writing code work.
DDL reversal of 0007 removes both guards and table in its transaction; it does not
restore old catalogue prices, reverse quantities, alter invoices or preserve a
copy of audit rows. A full rollback past 0007 also requires reversing its dependent
0008 first. Restoring the schema later does not recreate lost audit history.

The disposable test runner has a tightly scoped owner-only exception for Django's
synthetic teardown: generated flush SQL temporarily disables the TRUNCATE guard,
then re-enables it in the flush transaction. It verifies the dedicated test database
and local cluster identity. Explicit TRUNCATE security tests remain guarded. This
is test-only configuration, not a production recovery procedure or guard bypass.


### Approved Admin stock scope

Authorized administrators may edit stock, price/currency, or both in one save,
and create materials with nonzero opening stock. Existing permissions, field
validation, signed stock/price/catalogue snapshots and transaction locks apply.
Existing-material price/currency changes require a reason and an atomic ledger
entry; unchanged prices and initial creation do not create price-change entries.

Direct Admin stock edits and nonzero opening stock do not create stock movements.
This is an explicitly approved, deferred traceability limitation, not a reason to
block authorized Admin operations. Material Entries continues to record receipts
with its existing exactly-once stock movement processing. No new stock adjustment
mechanism is introduced.


### Material Entries price editing

Existing-material mode includes an independent price dialog. Active stock
personnel (`can_manage_stock`) and users with `inventory.change_material` may
use the audited pricing service without receiving Django Admin access. Pricing
permission alone grants no receipt/draft permissions. The dialog fetches a fresh
signed price revision and saves only price, currency and a mandatory reason;
receipt inputs, operation tokens and saved draft versions are not submitted.
Blank price means unknown; zero remains an explicit price. Invoice capture timing
and finalized snapshots are unchanged.

Migration 0011 replaces only the existing audit function, allowing the stock flag
for `service` source changes while preserving the existing Admin permission rule.
It does not rewrite materials or ledger records. Reversing 0011 restores the prior
permission check without dropping history; deploy compatible application code
with the migration (stock personnel price saves require 0011). Ledger ownership,
ACL and privileged-owner limitations documented above still apply.
