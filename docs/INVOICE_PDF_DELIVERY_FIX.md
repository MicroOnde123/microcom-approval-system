# Invoice PDF delivery and action toolbar

Review date: 2 November 2026. Local implementation only; no deployment, production database access, .env edits, migrations, financial issuance, service restart, commit or push.

## Evidence and diagnosis

The inspected implementation used:

1. POST /invoices/{id}/print/ to authorize the invoice, create/reuse an artifact and checksum-verify its bytes.
2. print_delivery.print_response to embed those bytes as base64 JSON in an HTML shell.
3. static/js/document_print.js to construct a Blob URL, set the iframe source and assign the download link's href, then call the iframe's print function.

**Confirmed implementation weakness:** the HTML shell has no PDF source or usable download destination without successful JavaScript initialization. JavaScript also catches iframe print errors without presenting a new error. Missing/blocked/stale JavaScript or browser-specific iframe printing can therefore leave exactly the reported empty viewer and ineffective controls. The old single-invoice shell does not request an authenticated PDF URL; it relies on an in-memory Blob.

**Not confirmed:** the exact production trigger. No production response, console log, static-file result, artifact row or invoice was inspected. No assertion is made that storage, permissions, CSP or X-Frame-Options caused that particular incident. If the production shell comes from this exact source, reaching it implies the handler already read verified PDF bytes; that is a source-based inference, not a production artifact audit.

The private root checks, renderer, frozen snapshots, artifact checksum verification and append-only creation/reuse logic were inspected and left unchanged. The storage path supplied by the owner is treated as established context, not a reason to rewrite .env or ACLs.

## Corrected delivery

| Operation | Endpoint and behaviour |
|---|---|
| Print Invoice | CSRF-protected POST /invoices/{id}/print/: existing invoice authorization/final status gate; generate/reuse current-language artifact; redirect to protected GET |
| Read PDF | GET /invoices/documents/{artifact_id}/download/: existing permission plus object scope and checksum; application/pdf, inline |
| Download PDF | CSRF-protected POST /invoices/{id}/download/: same guarded artifact preparation; redirect to attachment endpoint |
| Save attachment | GET /invoices/documents/{artifact_id}/file/: same authorization/checksum checks, application/pdf and Content-Disposition attachment |
| Filtered invoice printing | Existing guarded selection/merge, returned directly as inline PDF rather than JavaScript HTML |

Print now opens the native browser PDF viewer at a top-level authenticated URL. Use that viewer's print control or Ctrl+P; automatic cross-frame print invocation is intentionally removed. Browser preferences may download PDFs instead of displaying them.

GET delivery never generates a document. Permissions are checked again after the redirect, including revocation/scope changes. Missing IDs return 404; damaged/missing stored content returns a controlled 409 error without silently generating another artifact. POST preparation retains existing artifact reuse/failure-attempt behaviour. Repeated print/download preparation does not reissue invoices or allocate new financial numbers.

PDF responses retain private/no-store and nosniff and now include no-referrer. Attachment selection is a server route argument, not a client-supplied filesystem path. No public URL, filesystem exposure, frame exemption, CSP relaxation, snapshot mutation, artifact deletion or rendering-version change was introduced.

The existing language-specific generation endpoint remains compatible. Receipt/valued-return-note print helpers still use their existing delivery path; this change does not redesign their workflows or financial logic.

## Toolbar

Before: return history and issuance links preceded a secondary-styled print button in nested wrapping groups.

After:

- Primary Print Invoice and outlined Download PDF together.
- Secondary Issue material return note, then tertiary/outlined history navigation.
- Existing invoice-list/back navigation stays in the page header.
- Existing FINALIZED, can_read and can_issue gates are preserved.
- Desktop alignment and spacing; responsive stacking; minimum 44px targets.
- Existing English/French labels and design-system classes; no new UI framework or JavaScript dependency.

## Exact files for this task

| File | Purpose |
|---|---|
| invoicing/views.py | Redirect single-invoice preparation to private GET; attachment disposition; direct merged PDF delivery |
| invoicing/urls.py | Guarded download-preparation and attachment routes |
| templates/invoicing/detail.html | Ordered responsive toolbar and explicit download action |
| static/css/invoice_actions.css | Invoice-scoped responsive styling |
| invoicing/test_invoice_pdf_delivery.py | HTTP, private artifact, error, authorization, language and toolbar regressions |
| invoicing/test_printing_offline.py | Update single/bulk delivery expectations and template static-library registration |
| inventory/test_address_offline.py | Register static tags when compiling the updated invoice template |
| invoicing/check_invoice_browser.py | Database-free synthetic template/PDF preparation and headless Edge layout checks |
| docs/INVOICE_PDF_DELIVERY_FIX.md | Evidence, verification boundaries and deployment instructions |

Existing material-currency changes, config/settings.py comment edit, .env backup files and training-guide drafts are outside this patch and were not altered by this task. No secrets or .env contents were read.

## Tests and browser evidence

Executed:

    C:\MicrocomRehearsal\venv\Scripts\python.exe -m django test invoicing.test_invoice_pdf_delivery invoicing.test_printing_offline invoicing.test_filter_printing_offline invoicing.test_document_consistency --settings=config.test_stock_review_settings --noinput --verbosity=1

**59 tests passed**, 2.849 seconds on the final run. Django checks: zero issues. These tests use mocked ORM/financial services or synthetic temporary PDFs, with standalone settings that do not import deployed settings/.env. No production or external database was connected.

Coverage includes valid EN/FR PDF content, direct inline/attachment headers, authenticated redirects, object-scope denial before reading, checksum/missing-file failure, safe errors, POST/CSRF boundaries, cache controls, artifact reuse without rendering/issuance, frozen snapshot preservation, merged PDFs, limits and toolbar visibility/order/translations.

Earlier failures in the new test setup were corrected: mocked error-template context processors, static tag registration and prefix-overlapping URL assertions. The passing result above is after those corrections.

The native Edge browser was exercised with local synthetic renders of the actual invoice detail template and actual CSS at exact 1440px and 390px viewports, EN and FR. All four combinations passed checks for no horizontal overflow, four authorized controls, 44px touch targets, controls inside the viewport and primary print-first order. Desktop controls share a row; mobile controls stack. Screenshots were inspected at desktop and French mobile sizes.

Evidence: local_artifacts/invoice_pdf_delivery/browser-results.json and toolbar-{en,fr}-{1440,390}.png. These are synthetic template/browser checks, not authenticated deployed screenshots for the employee manuals. Initial CLI captures were rejected as mobile evidence because Edge's minimum window width did not equal 390px; final checks use DevTools exact viewport emulation.

**Remaining browser limits:** no Playwright installation was available. Edge's headless native-PDF screenshot was blank and does not establish native viewer success. Native print dialogs, actual saved-browser downloads, Chrome/Firefox and the authenticated Windows deployment remain manually unverified. PDF parser success and FileResponse tests are not proof of those browser actions. PostgreSQL financial triggers/full-suite regression were not run.

## Read-only production diagnostics if needed

Use an authorized normal browser session; do not create invoices, new returns or financial transactions for diagnosis.

1. Record the deployed build identity, browser/version and exact failing URL.
2. On the old print shell, inspect Network for document_print.js/CSS status, MIME type and version, and Console for JavaScript/CSP/frame errors. Do not copy base64 invoice data or customer information into reports.
3. Inspect response Content-Type, Content-Disposition, Cache-Control, CSP and X-Frame-Options. Verify the current session is not being redirected to login or denied scope. Do not disable security headers.
4. If an authorized operator already knows an existing READY artifact ID, GET its protected inline URL directly. This reads/verifies the artifact and does not generate one. Compare status/content type with what the viewer received. Record only technical status/headers, not private contents or filesystem paths.
5. Review sanitized application/reverse-proxy/static delivery errors. If artifact metadata is needed, an authorized operator can inspect only ID, status, language, rendering version and creation time using an established read-only process. No production ORM query was run by this task.

## Windows Server deployment

No database migration is required.

Perform these actions only during the separately approved release:

1. Review the task-specific files above; exclude unrelated workspace edits, .env backups, browser profiles, local_artifacts and generated manuals. Keep a rollback copy of the current application/template/static release. Do not delete private PDF storage or artifacts.
2. Deploy the reviewed views, URL routes, invoice template and CSS together into the actual service application directory using the normal release mechanism. Keep .env, permissions, snapshots and numbering untouched.
3. From that deployed directory, using its existing virtual environment:

       .\venv\Scripts\python.exe manage.py check
       .\venv\Scripts\python.exe manage.py collectstatic --noinput

   collectstatic is needed for the new invoice_actions.css and production static manifests. Do not run migrate for this patch. If the service uses an external virtual environment, substitute that approved interpreter path.
4. Arrange the normal separately authorized application reload/recycle so Waitress loads the new Python/routes/templates. No service command was executed here. Keep all browser security headers intact.
5. In isolated rehearsal, verify an existing authorized finalized sample invoice opens from Print Invoice with a redirect to inline application/pdf. Save with Download PDF and inspect the saved file. Reprint/download should reuse the valid current renderer artifact; confirm snapshots/number unchanged.
6. Repeat EN/FR on Edge, Chrome and Firefox, desktop/mobile. Check native print controls, attachment filenames, unauthorized/scope-revoked access and damaged-artifact errors. Confirm draft actions remain hidden and return issuance/history conditions match before deployment.
7. After those checks, use the normal authorized production acceptance process. If reverting, restore application/template/static files; do not undo financial records, delete PDFs or reset counters.

Implementation/testing stopped here for review. The exact production failure trigger and remaining native-browser acceptance must be verified before claiming all acceptance criteria are complete.
