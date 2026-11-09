# Material Entries draft management

The existing Approval Request conventions are retained: incomplete saves, owned
editing, translated status badges/messages, and explicit cancellation by POST.
Approval Request models/services are unchanged.

## Behavior

- Each new form has its own signed receipt operation token. **New Entry / Nouvelle
  entrée** opens a fresh form even when other saved drafts exist.
- **Save Draft / Enregistrer le brouillon** stores incomplete values in the existing
  `MaterialEntryDraft` JSON data. It does not create a material, receipt, movement,
  invoice or price change. Valid French dates are stored as ISO; invalid partial
  text is retained for later correction.
- A successful save redirects to a fresh form in the same mode. The accessible
  success notice shows the saved material name when known and links **Continue
  Editing / Continuer la modification** to that exact owned draft ID. Only mode
  and draft ID appear in the redirect; notes, supplier, prices and other draft
  contents are not placed in URL parameters or Django message cookies. Names are
  fetched after authorization and HTML-escaped when rendered. The notice can be
  dismissed without clearing values already typed into the fresh form. Dismissal
  uses a small JavaScript enhancement; without JavaScript the resume/new-entry
  links still work and the notice remains visible. Failed saves never redirect or
  clear entered values. Cancelled/completed/inaccessible draft IDs do not produce
  actionable notices. Continue Editing always reloads the current draft version.
- The paginated **Saved Drafts / Brouillons enregistrés** list shows material name,
  entry mode, last modification, status, resume and cancellation actions. Existing
  materials are resolved in one batched lookup per page.
- Saving an owned draft updates its existing row using its submitted version.
  Identical creation/update retries do not duplicate rows or consume new versions.
  Stale conflicting saves fail and retain the submitted version and entered values;
  reload the saved draft before trying to overwrite newer work.
- Existing-material receipts are independent by operation token, not by material.
  Several drafts may reference the same material with different quantities and
  delivery details. The list explicitly identifies Existing Material Receipt and
  shows quantity/unit, e.g. `Ubiquiti AP (AP-1) — 5 pcs` and a separate `10 pcs` row.
  Starting another receipt never replaces either draft. Confirming/cancelling one
  leaves the other's saved data, version and status unchanged.
- Resuming an existing-material draft loads current stock and official catalogue
  price/currency. The price is informational, never a draft price update. Selector
  changes update that display too. Material existence, permissions and receipt data
  are revalidated on confirmation. The existing policy for inactive catalogue
  materials is preserved. Later stock/price changes are not overwritten: the locked
  receipt service adds only the received quantity to current stock, captures current
  metadata and leaves official prices untouched.
- Cancellation requires a separate confirmation page and a CSRF-protected POST.
  Only the owner, still authorized to manage stock, may cancel; superusers do not
  automatically gain access to other employees' drafts. Cancellation retains the
  row/data, marks it CANCELLED and increments its version. Repeated cancellation is
  harmless. Completed drafts cannot be cancelled or resumed for editing.
- Review remains read-only. Draft proofs bind the existing receipt operation token,
  transaction payload, owner, draft ID and draft version. Modify restores submitted
  values. Confirm revalidates and calls the existing atomic receipt service.
- Finalization and completion commit together. Exact confirmation retries return
  the same receipt. Changed payloads and stale proofs fail without changing stock.
  Omitting the draft ID cannot bypass draft ownership/version/cancellation rules.
- PostgreSQL transaction advisory locks serialize creation and finalization of the
  same operation before a receipt/draft row exists. Row locks and existing receipt
  uniqueness/payload hashes remain in place; no second receipt identifier is added.

Migration `0010_materialentrydraft_cancelled` adds the CANCELLED choice to migration
state. It preserves 0007/0008/0009 and existing records; no new table or data rewrite
is needed. Catalogue pricing, audit guards, invoice prices, receipt references and
approval workflows are unchanged.

## Automated verification

The supplied `config.test_material_entries_settings` targets the local database
`microcom_material_test` on `127.0.0.1:5432`; it is preserved unchanged. The dedicated
runner verifies PostgreSQL identity and its local data directory, then creates a
fresh `test_microcom_material_entries_<random>` database for each run. `--keepdb`
retains only synthetic test evidence and avoids dropping existing databases.

```powershell
.\venv\Scripts\python.exe manage.py test inventory.test_draft_save_continue inventory.test_entry_drafts inventory.test_material_entries inventory.test_receipt_retries inventory.test_entry_review inventory.test_entry_dates inventory.test_entry_translations inventory.test_receipt_history inventory.test_pricing invoicing.test_lifecycle --settings=config.test_material_entries_settings --testrunner=config.material_entries_draft_test_runner.MaterialEntriesDraftRunner --keepdb --noinput
```

The runner permits owner-only Django synthetic teardown flushes, verifying the
dedicated test database first; explicit ledger mutation/TRUNCATE operations remain
protected. No application pricing or audit safeguard is removed for tests.

## Manual verification in the isolated local environment

Do not use normal deployment settings. First verify `DB_USER`/host from the explicit
local module and the intended local database identity. No password needs printing.
Apply only the additive local migrations, then launch:

```powershell
.\venv\Scripts\python.exe manage.py migrate inventory --settings=config.test_material_entries_settings
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8001 --settings=config.test_material_entries_settings
```

These commands are for the user to run locally; the implementation does not migrate
the manual database or start its server automatically. Use an existing local active
stock manager account. If one is missing, create/configure a local account through
the project's normal local setup; do not use Supabase credentials or records.

1. Open `http://127.0.0.1:8001/materials/entries/`. Enter only a name, optional price
   proposal and notes; save. Verify that inventory and official prices are unchanged.
   Confirm that the form is now empty in the same mode and the success notice names
   the saved product. Continue Editing must restore the exact draft and its values.
   Save again: it must update that draft, then return to another fresh form. Type
   into the fresh form and dismiss the notification; typed values must remain.
2. Choose New Entry, save another product, then save an existing-material receipt.
   Resume each row and confirm the correct values and dates are restored.
3. Edit/save one draft repeatedly. Confirm no extra draft rows appear. Open the same
   draft in two tabs: save different values in the first, then attempt a stale save
   in the second. It must show a conflict and keep the newer saved values intact.
4. Cancel one draft. The first page must only ask for confirmation. Confirm the
   cancellation; the row disappears from active drafts, others remain, stock/prices
   stay unchanged. Retry/back-button cancellation safely. Another user's draft must
   not be accessible through copied resume/cancel URLs.
5. Resume a valid draft, Verify, Modify, Verify and Confirm. Verify one receipt and
   one IN movement. Repeat the exact confirmation POST: the same receipt must be
   returned and stock must not increase again. A completed draft cannot be cancelled.
6. Switch EN → FR → EN without restarting. Check action-bar text, draft list/status,
   confirmation page and errors. Check keyboard focus, native selector fallback and
   calendar/date input. At desktop, tablet and narrow mobile widths, check wrapping,
   button alignment and absence of horizontal page overflow.

No Supabase/production access, migrations, exports, commits, pushes or deployments
are part of this work. Database-role/ACL approval from the earlier price-ledger
deployment review remains separate; local tests do not approve Supabase exposure.
