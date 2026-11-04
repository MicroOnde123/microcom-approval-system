# Material Entries Phase 1

The page is `/materials/entries/`, linked beside Material Reports. Only active authenticated stock managers and superusers can use it. New categories can be created inline with the bilingual + New Category dialog.

Receipts use one signed user/mode-bound operation token per form. The unique receipt token serializes concurrent retries; a material row lock serializes separate receipts. Receipt, line, IN movement (with no request), and stock update commit together. New materials are inserted at zero stock. Receipt references are `IN-` plus a UUID. Delivery references are optional external references and may repeat. A browser replay redirects to the original result; the service rejects changed payloads under the same token. Tokens intentionally remain valid for durable retries. Each newly opened form is a separate receipt.

## Local inspection (PowerShell)

The isolated settings never import deployment settings or `.env`. They connect only to the disposable `material_entries_local` PostgreSQL database on `127.0.0.1:55439`. The verification cluster is under `$env:TEMP\microcom_material_entries_pg` and was initialized with local trust authentication; use it only for synthetic local data.

If the disposable server is stopped, start it in a hidden window:

```powershell
Start-Process -FilePath 'C:\Program Files\PostgreSQL\18\bin\postgres.exe' -ArgumentList @('-D', "$env:TEMP\microcom_material_entries_pg", '-h', '127.0.0.1', '-p', '55439') -WindowStyle Hidden
```

From the project root:

```powershell
venv\Scripts\python.exe manage.py migrate --settings=config.material_entries_local_settings
venv\Scripts\python.exe manage.py createsuperuser --settings=config.material_entries_local_settings
venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --settings=config.material_entries_local_settings
```

Sign in, then open `http://127.0.0.1:8000/materials/entries/`. Select + New Category beside the category dropdown to create and automatically select a category without losing material or initial stock values. Use the base navigation language selector to inspect French and English. Try both receipt modes and resubmit a completed POST to confirm stock does not increase twice.

## Verification

```powershell
venv\Scripts\python.exe manage.py test inventory.test_material_categories inventory.test_material_entries requests_app.test_stock_safety requests_app.test_stock_integrity inventory.test_material_currency_form --settings=config.material_entries_local_settings --keepdb
venv\Scripts\python.exe manage.py check --settings=config.material_entries_local_settings
venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.material_entries_local_settings
```

Final verification: **74 tests passed** on PostgreSQL 18, including inline category creation, permissions, CSRF, simultaneous category submissions, receipts and retries. Five JavaScript tests also passed for form-state preservation, repeated clicks, errors, retries and cancel focus. Django system checks, migration drift checks, migration application, and JavaScript syntax checks passed.

Use `--keepdb` in this Windows sandbox: PostgreSQL 18 encountered an OS process-signaling problem during automatic test database deletion. The test database contains only synthetic fixtures. SQLite checks can use `config.test_stock_review_settings`; they skip the PostgreSQL concurrency tests.

Migration `inventory.0005_materialreceipt_materialreceiptline` adds two tables without changing historical movement rows or existing approval, deduction, return, invoice, or report code.

Category creation uses the existing unique category code as its retry key: an identical normalized payload returns the existing category, while a conflicting name or description returns a field error. It never creates materials, stock movements or receipts. No new migration is required for inline category creation. The native dialog requires JavaScript and a browser with HTML dialog support.

```powershell
node --test --test-isolation=none inventory/js_tests/material_categories.test.cjs
```

Scope limits: Phase 1 has one line per form (the schema supports grouping), free-text suppliers, no receipt editing/reversal or receipt listing, and no delivery-reference uniqueness rule. The selector displays a page-load stock snapshot; the committed stock is calculated under a row lock. Browser visual inspection remains a manual check.
