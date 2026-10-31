# Material Management / Gestion du matériel

The feature applies to all stock-managed materials. The mixed CPE, radio cable
and power supply example is one regression scenario, not a feature restriction.

## Interface

The existing approved-request page and Material Reports link to Material
Management / Gestion du matériel, with exactly three functional tabs:

1. Overview / Vue d’ensemble: request summary, quantities and material status.
2. Reconcile / Régulariser: the Material Reconciliation editor and collapsible
   revision history.
3. Returns & Receipts / Retours et bons de retour: inline physical returns,
   nonfinancial receipt issuance and protected PDF access.

Only one tab panel is displayed. Switching tabs does not reload the page or
discard unsaved edits. ARIA state, roving focus, arrow/Home/End keys, and browser
Back/Forward are supported. Without JavaScript, the same tab links use a validated
`tab` query parameter and the server displays only the selected panel. Invalid
submissions select the tab containing their errors; successful POSTs return to
the corresponding tab.

Each material has a compact expandable row. A quick destination selector assigns
all nonreturned quantities to CLIENT-installed, MICROCOM-used or retained/testing.
Split mode supports partial quantities and multiple outcomes. Editing installed
or used quantities suggests the remaining retained quantity using integer
hundredths. This is a browser convenience; services remain authoritative.
Physically returned quantities come from actual stock movements and are read-only.
Invalid or stale posted values are retained for review rather than silently fixed.
New physical returns mark the last reconciliation as needing review.

The browser displays a text-only quantity summary before saving a revision, and
a selected-movement confirmation before issuing a permanent RCP reference.
Cancel does not submit. Confirmation retains the same operation token and revision.
No business data, signatures or storage paths are embedded in JavaScript.

Return-to-stock pages show the authoritative remaining quantity and a matching
HTML maximum. A fully returned item has an informational state instead of an
active form. Direct POSTs still use the original protected service: an excessive
return fails, while an exact committed-token replay succeeds without restoring
stock again. A stale page cannot override service checks.

The unified Returns & Receipts tab also renders the existing ReturnToStockForm
inline. Its CSRF-protected POST calls `return_material_stock` unchanged, retaining
the same signed item/actor/operation token and service-owned atomic transaction.
No second stock-restoration mechanism is introduced. The original standalone
return route remains available for existing links. Fully returned rows have no
active return form, and committed-token retries remain safe.

Receipts have one compact language selector with View PDF and Print actions.
Both open an authorized inline PDF; printing uses the browser's PDF print control.
An explicit language selection is validated, and the selected language survives
a generation failure and retry. Existing protected artifact URLs remain valid.

## Boundaries

The UI redesign adds no migration and changes no stock, financial, reference
allocation or reconciliation service. The separately approved additive migration
`requests_app.0020_material_reconciliation_return_receipts` belongs to the preceding
implementation and still requires controlled production review/application.
No production access or activation is performed by this checkpoint.

The existing invoice-linked financial Bon de retour remains distinct from the
nonfinancial RCP receipt. `MATERIAL_RETURN_NOTE_UI_ENABLED` remains false.
No technician portal or additional return approval lifecycle is introduced.

## Validation and evidence

- Synthetic isolated PostgreSQL UI tests cover one/many materials, partial and
  full returns, stale reconciliation data, POST validation, exact replay, CSRF,
  unauthorized access, receipt controls, PDF language/recovery and escaping.
- Existing stock safety, receipt, reconciliation and concurrency suites remain
  part of focused and full regressions.
- Node tests cover quantity arithmetic and existing AJAX filtering behavior.
- Synthetic EN/FR template previews prohibit database and network connections.
  Their Edge screenshots and browser results are retained in
  `local_artifacts/material_operations_preview/` and must not be committed.
- Browser checks cover 390px mobile, 768px tablet and 1365px desktop layouts,
  expanding sections, split quantities, review/cancel/confirm and retained tokens.

Synthetic browser evidence is not an authenticated deployed-browser acceptance
test. Production CSS/static collection, private-storage ACLs, database migration
state, service identity and backup/recovery remain operational checks.

### October 30 verification results

The following full-suite result is the baseline before the three-tab refinement.
The refinement was then verified with 68 passing isolated PostgreSQL tests, 27
passing JavaScript checks and actual Edge browser checks: 12 synthetic EN/FR
pages at 390px and 1365px, exercising all three tabs (36 tab renders). Assertions
cover exactly three tabs, one visible panel, no page reload on switching,
keyboard navigation, Back/Forward, preserved edits/tokens, inline return review,
receipt confirmation and no horizontal overflow. The full suite was not repeated
for this subsequent UI-only refinement.

Current browser results: `local_artifacts/material_operations_preview/three_tab_browser_results.json`.
Current focused logs: `local_artifacts/material_tabs_focused.*.log`.

- Full isolated PostgreSQL suite: **763 run, 762 passed, 0 failures, 0 errors,
  1 existing opt-in sample-generation skip**, 2123.181 seconds.
- Final focused UI, material outcome, stock-safety and migration-restoration run:
  **66 passed**, 40.790 seconds. This ran after the final UI refinements.
- JavaScript: **27 passed** (six material-operation arithmetic checks and 21
  existing AJAX filtering checks).
- Synthetic Edge: **18 responsive EN/FR renders**, no horizontal page overflow;
  six mixed-outcome interaction scenarios also verify native keyboard expansion,
  partial arithmetic, review/cancel/confirm, unchanged tokens and empty receipt
  selection feedback. Screenshots are local evidence, not production data.
- Ten synthetic page renders completed with database/network access prohibited;
  no translated source labels were missing from the French catalogue.
- Django system checks: zero issues. Migration consistency: no model drift and
  no pending operations in the isolated database after the final focused run.
- The older Phase A reversal test now restores all migration leaves, including
  0020; it still requires post-use reversal rejection and preservation of evidence.
- `git diff --check` passed. Protected tracked stock, invoice, financial return-note,
  BC/BS service and default feature-flag files compare unchanged with HEAD.

Database execution used only the verified PostgreSQL 17.11 cluster at
127.0.0.1:55439, system identifier 7701700619765861416, disposable database
`microcom_phase_a_test`, dedicated role `microcom_test_runner`. Its ACL, process
identity and fail-closed standalone settings were verified before execution.
No Supabase/production connection, production migration, deployment, flag change,
commit or push was performed. The UI is ready for review; production deployment
and operational sign-off remain separately authorized actions.

## Files changed in the UI checkpoint

- `requests_app/material_outcome_views.py`
- `requests_app/views.py` (return-form context and browser maximum only)
- `templates/requests_app/material_outcomes.html`
- `templates/requests_app/return_material_to_stock.html`
- `templates/requests_app/receipt_pdf_error.html`
- `templates/requests_app/request_detail.html`
- `templates/requests_app/material_reports.html`
- `static/css/material_operations.css`
- `static/js/material_operations.js`
- `locale/fr/LC_MESSAGES/django.po`
- `locale/fr/LC_MESSAGES/django.mo`
- `requests_app/test_material_operations_ui.py`
- `requests_app/test_material_outcomes.py` (canonical feature-name assertion)
- `requests_app/test_references_postgresql.py` (restore all migration leaves)
- `requests_app/js_tests/material_operations.test.cjs`
- `docs/MATERIAL_OPERATIONS_UI.md`

Local-only evidence helpers: `local_artifacts/material_operations_preview.py`,
`local_artifacts/material_operations_browser.cjs` and the catalogue preparation
helper `local_artifacts/material_outcome_translations.py`. Application code has
no dependency on these helpers. Do not stage local evidence or browser profiles.
The three-tab checks additionally use `local_artifacts/material_tabs_browser.cjs`
and the one-time local template-edit helper `local_artifacts/build_material_tabs.py`.

## Manual sign-off checklist

Use authorized sample users and synthetic requests in an isolated environment.
Repeat in English and French, including a narrow mobile viewport.

1. Open an approved request with one material and another with many materials.
   Confirm the request reference, technician and issued quantities. Before any
   reconciliation, usage is unknown rather than asserted as historical fact.
2. Expand a material row. Choose a single destination, then split quantities
   between CLIENT-installed, MICROCOM-used and retained/testing. Check the review
   summary. Cancel and verify nothing was saved; confirm and inspect history.
3. Record a partial physical return. Verify its remaining maximum and success
   message. Reload the reconciliation: the previous revision needs review and
   the physical return quantity is read-only. Record a new revision without
   rewriting the previous one.
4. Return the remaining quantity. Confirm the fully-returned explanation is
   prominent and no active return form remains. A crafted excess POST must fail;
   replay of the original successful token must not add stock a second time.
5. Select actual returned movements and generate a receipt. Cancel its review
   first; confirm no RCP reference was issued. Confirm issuance, then repeat the
   same submitted operation and verify the same receipt/reference is returned.
6. View and print that receipt in both languages. Check private inline delivery,
   the RCP reference, original request, quantities and unchanged stock. Simulate
   PDF unavailability in the test environment and verify retry retains language.
7. Check unauthorized direct workspace/PDF access and CSRF rejection. Verify
   no invoice, credit, BC/BS, approval or original-classification change occurred.
