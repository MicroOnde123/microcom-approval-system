# Document presentation stabilization — 30 October 2026

## Inspection and design decisions

The current Facture is the visual reference: logo-free and issuer-free PDF,
with a centered title, official reference/date row, frozen Client name,
four-column material table, right-aligned totals, Stock Department signature
and numbered A4 footer. This follows the earlier explicit issuer-removal decision.
No company name, contact block or logo has been reintroduced into financial PDFs.
Company and branding snapshots remain stored and validated unchanged.

Inspected components: `invoicing/pdf.py`, `documents.py`, `printing.py`,
`views.py`, `urls.py`, `admin.py`, `models.py`, `words.py`, return-note
services/permissions/sessions/recovery/documents/PDF/views/forms/access,
financial guard migration 0007, invoice and BR templates; existing BC/BS
approved-document template and print views; Material Management views/template,
JavaScript and styles; reconciliation/receipt services and receipt artifact/PDF
implementation; relevant synthetic, isolated PostgreSQL and browser tests.

## Implemented changes

* Facture renderer v5 displays a multiline physical address only when present
  in the frozen branch snapshot. Legacy snapshots without it remain renderable.
* Financial BR renderer v2 follows the Facture identity, dimensions, fonts,
  material table, totals and footer. It retains original facture references,
  movement IDs, frozen quantities/prices, returned and cumulative values,
  adjusted material value and reason. It explicitly disclaims payment/refund/credit.
* English amount wording is presentation derived from the stored exact total and
  currency. French uses the retained French wording. No monetary values or
  stored wording are rewritten; no rounding or currency conversion is performed.
* Nonfinancial RCP renderer v2 uses matching typography, margins and footer,
  while retaining its operational meaning and omitting financial values.
* BR selection, preview, detail and history use scoped styling, structured frozen
  party information, readable summaries, responsive tables and existing actions.
* Facture single/bulk, BR and RCP Print actions open a standalone private viewer.
  The browser receives only an already-authorized, checksum-verified PDF, encoded
  safely in JSON; JavaScript creates a temporary in-browser Blob URL. The viewer
  attempts the print dialog on load and provides Print and Download PDF controls.
  The document services still authorize every generation and retrieval. No public
  PDF URL or filesystem path is exposed. Responses remain private/no-store.
* Language is taken from Django's active language, not submitted language fields.
  BR's EN/FR buttons and RCP's second selector are removed. Legacy generation
  URLs remain available but use the active language. Direct historical artifact
  retrieval preserves the artifact's original language and bytes.
* BC/BS keep their established printable layout, copy controls and existing
  issuance flow; document/root HTML language attributes follow Django language.
* Material Management separates CLIENT-installed, MICROCOM-used, physically
  returned, retained/testing and outstanding quantities. Fully returned materials
  start a new unbound editor with zero usage values, without a destination
  shortcut. Bound input and existing revisions are not rewritten. Existing
  reconciliation and physical-return services remain authoritative.
* DocumentSequence Admin makes numbering configuration read-only after finalized
  financial BR usage, matching the existing database guard. Permissions and
  stockuser's explicitly authorized non-staff issuance rule are unchanged.

## Exact application/documentation file manifest

Production Python:

* `invoicing/admin.py`
* `invoicing/pdf.py`
* `invoicing/return_note_pdf.py`
* `invoicing/document_presentation.py` (new)
* `invoicing/print_delivery.py` (new)
* `invoicing/views.py`
* `invoicing/return_note_views.py`
* `invoicing/urls.py`
* `requests_app/material_outcome_views.py`
* `requests_app/return_receipt_pdf.py`

Templates:

* `templates/base.html`
* `templates/invoicing/detail.html`
* `templates/invoicing/print_document.html` (new)
* `templates/invoicing/return_notes/presentation.html` (new)
* `templates/invoicing/return_notes/select.html`
* `templates/invoicing/return_notes/preview.html`
* `templates/invoicing/return_notes/detail.html`
* `templates/invoicing/return_notes/history.html`
* `templates/requests_app/material_outcomes.html`
* `templates/requests_app/receipt_pdf_error.html`
* `templates/requests_app/approved_document.html`
* `templates/requests_app/bulk_print_material_documents.html`

Assets/catalogues:

* `static/css/document_print.css` (new)
* `static/css/financial_documents.css` (new)
* `static/js/document_print.js` (new)
* `static/js/material_operations.js`
* `locale/fr/LC_MESSAGES/django.po`
* `locale/fr/LC_MESSAGES/django.mo`

Tests:

* `invoicing/test_document_consistency.py` (new)
* `invoicing/test_printing_offline.py`
* `invoicing/test_documents.py`
* `invoicing/test_succursale_address.py`
* `invoicing/test_return_note_pdf.py`
* `invoicing/test_return_note_views.py`
* `invoicing/test_return_note_recovery.py`
* `inventory/test_address_offline.py`
* `requests_app/test_material_operations_ui.py`
* `requests_app/js_tests/document_print.test.cjs` (new)
* This document (new).

Local-only preparation/evidence, not application dependencies:
`local_artifacts/document_presentation_preview.py`,
`document_presentation_browser.cjs`, `document_presentation_translations.py`;
updated `material_operations_preview.py` and `material_tabs_browser.cjs`;
`document_consistency_*.log` and synthetic previews/screenshots under
`local_artifacts/material_operations_preview/`. Do not stage these wholesale.

## Focused validation

All database checks use verified local PostgreSQL 17.11, loopback port 55439,
database `microcom_phase_a_test`, cluster ID `7701700619765861416`, standalone
settings `local_artifacts.phase_a_test_settings`, `--keepdb --parallel=1`.
No Supabase or production connection, live issuance or real document regeneration.

```powershell
.\venv\Scripts\python.exe manage.py test invoicing.test_document_consistency invoicing.test_printing_offline invoicing.test_return_note_pdf invoicing.test_return_note_views invoicing.test_return_note_documents invoicing.test_return_note_recovery invoicing.test_succursale_address invoicing.test_documents requests_app.test_material_operations_ui requests_app.test_material_outcomes requests_app.test_material_documents_postgresql --settings=local_artifacts.phase_a_test_settings --keepdb --parallel=1
.\venv\Scripts\python.exe manage.py test invoicing.test_return_note_services invoicing.test_return_note_concurrency --settings=local_artifacts.phase_a_test_settings --keepdb --parallel=1
node --test requests_app/js_tests/auto_filters.test.cjs requests_app/js_tests/material_operations.test.cjs requests_app/js_tests/document_print.test.cjs
.\venv\Scripts\python.exe manage.py check --settings=local_artifacts.phase_a_test_settings
.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=local_artifacts.phase_a_test_settings
```

Document/UI selection: 155 passed, zero failures/errors/skips. JavaScript: 28
passed. System checks: zero issues; no migration drift. Additional financial
service/concurrency selection: 47 passed, zero failures/errors/skips, recorded in
`document_consistency_financial.stderr.log`. A final overlapping presentation/UI
selection passed 34 checks, including the added previous-revision preservation
case and active HTML language assertion. Results are not summed because selections
overlap; the corresponding log is `document_consistency_supplemental.stderr.log`.
The final PDF-only selection passed 22 checks after the renderer cleanup and
English CDF centime wording check (`document_consistency_pdf_final.stderr.log`).
No full regression run was requested or performed for this checkpoint.

Browser evidence: 20 EN/FR BR selection/preview/detail/history/print combinations
at 390px and 1365px, with no horizontal page overflow and protected PDF Blob
previews visible. Three-tab Material Management checks passed 12 pages / 36 tab
states and cover keyboard navigation,
tab state, mixed/fully returned materials, same-token forms and no extra reloads.
The browser tests use synthetic file fixtures with external network blocked.

## Preservation and deployment impact

No migrations, dependency changes, database configuration changes, feature-flag
changes or production operations. No change to financial/stock services,
numbering, valuation, confirmation signing, replay or financial database guards.
Previous artifacts remain accessible byte-for-byte; new render versions append
new rendition records only when an authorized user explicitly requests them.
Missing frozen addresses are not substituted from current branch data.

Before deployment, manually verify the native print dialog and actual A4 output
in the intended supported browser. Headless rendering and a mocked print call
do not prove OS/printer dialog behavior. Browser policy must allow the built-in
PDF viewer and a `blob:` frame; do not relax server policy without review.
Bulk print retains existing limits but its HTML response contains base64 PDF
bytes (approximately one-third encoding overhead), so review server response and
memory limits. Collect the new static assets through the normal reviewed release
procedure; no deployment is performed here.

The unrelated untracked root `test_return_permission.py` still performs UAT
lookups at import time and caused the preceding broad test-discovery error. It
was not changed or excluded by this presentation milestone. Remote statement
timeouts are not treated as evidence of application defects. Production/UAT
records and native interactive printing have not been reverified here.
