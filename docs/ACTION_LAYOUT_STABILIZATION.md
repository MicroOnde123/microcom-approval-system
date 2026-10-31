# Application action layout stabilization — 31 October 2026

## Audit and conventions

Inspected all 50 existing user-facing templates, four shared stylesheets and
three frontend JavaScript files before editing. Baseline hashes and action
contracts are retained locally in `local_artifacts/action_layout_baseline.json`.
Authentication, dashboards, request forms/details, review/history, reports,
Material Management, invoices, BR/RCP, BC/BS confirmations, print templates and
error/empty states were included. There are no additional custom administration
templates beyond the inspected reporting and workflow screens; Django Admin was
not redesigned.

Findings and corrections:

* Request details had Material Management above the title and document actions
  mixed with review/back navigation. The title/review/navigation remain in the
  header; contextual operational and document actions now sit together below it,
  with their original eligibility checks. Permanent cancellation is visually
  destructive; edit and document navigation are secondary.
* Invoice details scattered BR actions and printing among financial metadata.
  Finalized document actions now share a toolbar ahead of the unchanged data.
  List navigation is tertiary, edit secondary and finalization primary. Draft
  edit/finalize tables have keyboard-focusable horizontal scroll wrappers.
* Request and invoice form footers used different structures. Existing controls
  remain in their original forms inside reusable `form-actions` groups. Draft
  save, submission, resubmission and confirmation parameters are unchanged.
* Report/filter actions now use aligned wrapping action rows. Filter is primary;
  print/export/document access is secondary. Buttons retain every URL, query
  parameter, HTTP method and data attribute used by live filtering.
* Filled Print/Download buttons competed with issuance and submission. Secondary
  styling now consistently identifies these supporting actions; no actions were
  removed, duplicated or moved into dropdown menus.
* Material Management inherited arbitrary word breaking. Badges, including
  “Régularisé”, no longer shrink or break; short table headers have suitable
  minimum widths. The existing three tabs and form-local submit controls remain.
* Dashboard cards reuse restrained action groups. Navigation, confirmations and
  error/empty screens use the shared button/focus/spacing treatment where they
  inherit the application shell. Standalone authentication layouts were inspected
  and tested without replacing their existing design.

The single new stylesheet is scoped to `.app-container` inside `@media screen`.
It supplies header alignment, contextual toolbars, form footers, primary/secondary/
tertiary/destructive button hierarchy, 42px minimum button height, visible focus,
readable badges and responsive wrapping. Existing layout JavaScript is unchanged.
No print stylesheet or printable/PDF template loads these application-only rules.
No new UI strings were introduced; request status now uses the existing translated
model display label instead of a raw status code.

## Complete checkpoint file list

New files:

* `static/css/action_layout.css`
* `requests_app/test_action_layout.py`
* `docs/ACTION_LAYOUT_STABILIZATION.md`

Modified templates:

* `templates/base.html`
* `templates/core/dashboard.html`
* `templates/invoicing/create.html`
* `templates/invoicing/detail.html`
* `templates/invoicing/edit.html`
* `templates/invoicing/finalize.html`
* `templates/invoicing/list.html`
* `templates/invoicing/return_notes/detail.html`
* `templates/invoicing/return_notes/history.html`
* `templates/invoicing/return_notes/pdf_error.html`
* `templates/invoicing/return_notes/select.html`
* `templates/requests_app/administration_reports.html`
* `templates/requests_app/approval_detail.html`
* `templates/requests_app/approval_history.html`
* `templates/requests_app/create_request.html`
* `templates/requests_app/edit_request.html`
* `templates/requests_app/material_document_confirm.html`
* `templates/requests_app/material_outcomes.html`
* `templates/requests_app/material_reports.html`
* `templates/requests_app/my_requests.html`
* `templates/requests_app/pending_approvals.html`
* `templates/requests_app/receipt_pdf_error.html`
* `templates/requests_app/request_detail.html`
* `templates/requests_app/return_material_to_stock.html`
* `templates/requests_app/partials/list_filters.html`

Local-only evidence/helpers: `local_artifacts/action_layout_preview.py`,
`action_layout_browser.cjs`, `action_layout_baseline.json`,
`action_layout_contracts.json`, `action_layout_*.log` and synthetic screenshots /
browser measurements under `local_artifacts/material_operations_preview/`.
These are not application dependencies and should not be staged wholesale.

This manifest describes this checkpoint only. Earlier uncommitted document,
financial, reconciliation and reporting changes remain intact.

## Verification

```powershell
.\venv\Scripts\python.exe manage.py check --settings=local_artifacts.phase_a_test_settings
.\venv\Scripts\python.exe manage.py test requests_app.test_action_layout requests_app.test_list_filters requests_app.test_ajax_filters requests_app.test_material_operations_ui invoicing.test_return_note_views invoicing.test_return_note_recovery invoicing.test_list_display_offline invoicing.test_filter_printing_offline --settings=local_artifacts.phase_a_test_settings --keepdb --parallel=1
node --test requests_app/js_tests/auto_filters.test.cjs requests_app/js_tests/material_operations.test.cjs requests_app/js_tests/document_print.test.cjs
git diff --check
```

* Focused Django selection: 92 passed, zero failures/errors/skips.
* Frontend JavaScript: 28 passed, zero failures/skips.
* All user templates compile with database connections blocked.
* System checks: zero issues. `git diff --check`: passed.
* Checked white-background contrast: primary/tertiary `#123d6b` 11.02:1,
  destructive `#991b1b` 8.31:1 and focus `#2563eb` 5.17:1.
* Pre/post contract comparison across all modified templates: no differences in
  form methods/targets, control names/values, CSRF counts or URL destinations
  (presentation classes/styles are deliberately ignored). Existing JavaScript
  and shared stylesheets retain their baseline hashes.
* The owned Edge browser matrix uses synthetic data with external network
  blocked, testing EN/FR at 390, 768, 1024 and 1440px. It checks page overflow,
  overlapping/clipped visible actions, competing primary actions, badge wrapping,
  actual shared stylesheet activation and visible keyboard entry focus. The
  final result is in `action_layout_browser_results.json`: 82 EN/FR page/tab
  states, 328 width checks passed. This includes all three Material Management
  tabs, mixed/fully returned materials, long lists, invoice editing, recovery,
  authentication, empty results and invalid filters. Overlap checks include
  below-the-fold controls and respect intentional scroll-container clipping.

Initial browser harness problems (a malformed local asset URL, an incorrectly
encoded French test selector, CSS flex-item computed-display expectations,
same-file tab navigation and intentional nested-scroll clipping)
were corrected in local-only helpers before final verification. They were not
treated as application defects.

## Preservation and limitations

No changes to backend views/endpoints, business services, models, migrations,
permissions, feature flags, financial calculations, snapshots, document numbering,
PDF renderers, print/download behavior or stock operations in this checkpoint.
No Supabase/production connections or changes, migrations, commits, pushes or
deployment. Database-backed tests used the existing isolated local PostgreSQL
settings; no full remote regression run was performed.

Browser evidence is synthetic Edge coverage, not exhaustive live role/data UAT,
screen-reader certification or a guarantee for every OS/browser/native dropdown.
DOM order remains the visual/keyboard order; no CSS ordering or layout JavaScript
was introduced. Retain a final human keyboard/screen-reader and supported-browser
check, particularly on long real-world French data. Older browsers without
`:has()` may show an empty contextual toolbar border; actions remain accessible.
The new stylesheet needs normal static-file collection during a separately
approved release; that operation was not performed here.
