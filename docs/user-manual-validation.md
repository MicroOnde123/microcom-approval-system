# November 2026 user-manual validation

Date: 2026-11-09. Source revision: `72b527b739d2e42a0ead10d17af4ec571876dfc8`.

The owner reports that this release is deployed. This documentation update inspected source files only: no application sessions, production queries, migrations, services, accounts or business records were used. The previous deployment work reported 19 passing currency tests and 26 passing address/Administration/Bon d’accès checks. Those results are scoped evidence, not a complete application-suite result or manual acceptance.

## Deliverables and design

The existing portrait guide renderer, Microcom logo, embedded Arial fonts, blue/amber styling, chapter order, glossary and numbered footer are retained. The November source overlays the existing 25 chapters and adds four bilingual chapters for material registration, existing receipts, entry drafts and notifications. The finalized text edition removes empty illustration pages and pointer plans while retaining every procedure, warning and expected result. The invoice chapter describes the new request-first page order and separate invoice filters. Both PDFs have 35 pages, 29 synchronized chapters, a revised contents list with actual chapter page references and version 3.0 dated 2026-11-09.

`docs/update_november_manuals.py` builds candidates in `docs/manual-assets/november-2026-review/`. It does not replace the published local PDFs. Candidates were checked before promotion; previous PDF bytes are retained under `docs/manual-assets/previous-edition/`. No deployed manual directory was accessed.

## Implementation trace and verification scope

| Workflow | Relevant implementation | Documented behavior / limitations | Code inspected | Automated evidence | Manual/runtime follow-up |
|---|---|---|---|---|---|
| Login, dashboard, navigation | `config/urls.py`, `core/views.py`, `templates/base.html`, login template | Individual accounts; language and permission-dependent navigation | Yes | Not rerun for documentation | Confirm role menus and session behavior |
| Roles and administration | `accounts/models.py`, `accounts/admin.py`, `workflows/admin.py`, `workflows/models.py` | Staff/model permissions differ from stock/report flags; active assignments control approval | Yes | Existing tests inspected; not rerun in this phase | Review each role using approved synthetic accounts |
| Material registration and initial stock | `inventory/entry_forms.py`, `inventory/entry_views.py`, `inventory/entry_services.py`, entry/review templates | New identity plus positive initial receipt; verify before confirmation; one IN movement | Yes | No new runtime test | Capture new form, review, errors and completion |
| Existing stock receipt | Same entry modules; `templates/inventory/receipt_confirmation.html` | Estimated balance before receipt; historical recorded balance after confirmation; no technician-request link | Yes | No new runtime test | Confirm units, snapshots and receipt navigation |
| Entry drafts | `inventory/entry_drafts.py`, `inventory/models.py`, draft templates | Creator ownership, version checks, resume/cancel; saving does not affect stock; completed drafts cannot be cancelled | Yes | No new runtime test | Capture save success, resume, stale version, cancellation |
| Catalogue pricing | `inventory/admin.py`, `inventory/pricing.py`, `inventory/price_views.py`, `inventory/entry_forms.py`, price-dialog template | Authorized change plus reason; stale revision rejection; immutable audit; distinct receipt/price operations | Yes | Earlier 19 currency tests passed | Capture price dialog/history and permission differences |
| Currency defaults | Same pricing/admin files; `core/models.py`, `inventory/models.py` | Admin uses existing currency, otherwise company/USD; receipt creation initially USD; blank submitted currency with price uses company/USD | Yes | Earlier 19 currency tests passed | Confirm bilingual labels and displayed defaults |
| Submission and sequential approval | `requests_app/forms.py`, `requests_app/views.py`, `requests_app/services.py`, approval templates | Draft versus submitted; only current assigned step acts | Yes | Broader suite not claimed | Full technician-to-final-approval scenario |
| Classification | `workflows/models.py`, `workflows/admin.py`, `requests_app/services.py` | At most one designated stock review at any position; CLIENT needs no branch; MICROCOM needs active succursale | Yes | Focused currency tests do not verify routing | Capture stock review at Step 2 and final position |
| Correction/resubmission | `requests_app/resubmission.py`, `requests_app/services.py`, `requests_app/approval_attempts.py`, previous-attempt templates | Prior rows archived; material routing restarts; General Permission resumes only with unchanged reliable evidence and workflow | Yes | Not rerun for documentation | Compare unchanged and changed General Permission scenarios |
| Deduction, BC/BS | `requests_app/services.py`, `requests_app/material_documents.py`, request/report templates | Final approval deducts once; official issue requires approved/deducted evidence; references allocated on issuance | Yes | Not rerun | Validate printed layouts and repeat access |
| Invoices and branch | `invoicing/forms.py`, `invoicing/permissions.py`, `invoicing/services.py`, `invoicing/views.py`, invoice templates | One eligible MICROCOM request; action permissions plus request scope; company/series/address checks; frozen final values | Yes | Prior address tests are limited evidence | Finance acceptance of creation, verification, finalization and access |
| Credit boundary | `invoicing/models.py`, `invoicing/views.py`, `config/urls.py` | No employee credit-note issuance procedure is presented as available merely because models/guards exist | Yes | No runtime claim | Confirm any future screen before extending guide |
| Physical returns, reconciliation, RCP | `requests_app/stock_services.py`, `requests_app/material_outcomes.py`, `requests_app/return_receipt_documents.py`, request templates | Physical RETURN restores stock; reconciliation records usage; RCP is nonfinancial evidence | Yes | Not rerun | Stock-team acceptance using synthetic return scenarios |
| Valued return note | `invoicing/return_note_services.py`, `invoicing/return_note_access.py`, `invoicing/permissions.py` | Invoice-linked valuation of already-returned items; not a credit or new stock return | Yes | Not rerun | Gate/permissions, preview, expiry and document checks |
| Notifications | `requests_app/notifications.py`, `requests_app/notification_views.py`, notification templates, `accounts/admin.py` | Owner-scoped read state; mark-read does not approve; badge counts active unread approval notices; optional workflow emails controlled by administrator | Yes | Not rerun | Live refresh and email delivery require environment checks |
| Reports and Bon d’accès | `requests_app/views.py`, stock-report modules, permission-document template | Permission-scoped reporting; approved Administration permission requests use dedicated Bon d’accès | Yes | Earlier 26 checks include Bon d’accès template/denials | Verify paper layout and role visibility |

## Discrepancies and boundaries

- Old manuals incorrectly required stock review first and described lost approval history. These claims are replaced with any-position designation and archived attempts. Pre-feature missing history is not reconstructed.
- Classification designation remains optional in code. Administrators must include the designated review in material workflows; the manual does not claim configuration enforces its presence.
- The Admin material currency default follows company settings; new-material receipt form currency initially uses USD. These interfaces are documented separately.
- Opening an unassigned-currency form is read-only. Saving its displayed currency can create an audited currency change and require a reason. Explicitly submitting blank currency with a price uses company/USD rather than preserving a previous EUR/CDF value.
- Direct Admin stock edits do not produce traceable incoming receipts. The manual directs delivery operations to Material Entries.
- Material-return notes and RCP receipts do not automatically issue credits, refund payments or rewrite finalized invoices.

## Screenshot inventory

No application screenshots exist in the available PDFs or asset directories: each original PDF has only one embedded image, the Microcom logo. The newer landscape generator references absent `annotated/*.png` files and a different manifest schema; running it would not preserve a usable illustrated guide. The existing portrait generator is therefore reused.

No screenshots were replaced or fabricated. The owner authorizes finalization as text-based guides without an isolated rehearsal environment. There are no screenshot placeholders in the final PDFs or Markdown. All 28 primary illustration targets per language remain missing, plus the supplementary states listed in `manual-screenshot-checklist.md` and `capture-manifest.json`. The logo is retained. Pointer plans exist only in the separate future-capture checklist. Updated stock-review, draft, pricing, receipt, notification and Bon d’accès screens are specifically included. A future illustrated edition requires real sanitized EN/FR captures with numbered arrows and pointers. This does not block the text-based release.

## Validation performed

- Built both candidates with the project virtual environment; generation imports no Django and performs no database/network operations.
- Ran the updated existing `docs/manual-assets/validate_guides.py` on candidates and final local files.
- Parsed both PDFs, checked page numbering, nonblank pages, current version/date, all chapter contents references, embedded-image availability and text baselines inside page bounds.
- Checked identical bilingual chapter structure, Markdown links, SVG XML and absence of Unicode replacement characters. French accents extract correctly.
- ReportLab completed without layout exceptions. These structural checks do not replace visual review at normal reading size; raster page rendering/printer checks were not available in this environment. No image-quality claim is made for absent screenshots.
- No complete 805-test-suite result is claimed. For this finalization, the 27 invoice presentation, offline display and filter/printing regressions passed on the verified isolated test_microcom_db. Django system checks passed. No production records were used, and no migrations were applied.

Both updated PDFs are final text-based user guides. Screenshots remain a nonblocking improvement. Paper-printer checks and full role-based workflow acceptance remain deployment follow-up activities; they are not claimed by the structural PDF checks.


## Finalization checks and Git scope

- Final text edition: 35 pages and 29 chapters in each language; the previous 64-page drafts included visual planning pages that have been removed.
- Invoice-page changes are limited to the template and its focused regression tests. The candidate request form remains permission-gated; its hidden filter controls retain HTML form association inside the live-refresh region so JavaScript filtering remains compatible.
- The invoice presentation test checks the new section order in both English and French. Existing permission, filtering, printing and pagination tests are also included in the 27-test run.
- Genuine application screenshot count: zero. Logo: retained. Missing image targets: 28 primary screens plus 46 supplementary states per language, tracked outside the guides.
- Candidate PDFs were validated before replacement. Original PDF backups remain local and are excluded from the proposed commit, as are generated candidate directories, pending SVG panels and recovery files.
- Source provenance names the base Git revision; the invoice template improvement is an accompanying reviewed working-tree change that will enter the proposed commit with these guides.
