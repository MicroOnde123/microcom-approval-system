# Invoice browser viewing and bulk printing

Implemented locally; no real records were read or PDFs generated from them.

## Storage setup required

The ignored local `.env` now supplies:

    INVOICE_DOCUMENT_ROOT=C:\MicrocomPrivateDocuments\Invoices

Shared settings remain environment-driven. No directory or ACL outside the
workspace was created or changed. The storage service now requires an existing
directory; it will not silently create the root with unreviewed inherited ACLs.
It retains public-media/static separation, no symlink/junctions, opaque exclusive
file creation, append-only artifact records and checksum verification.

An authorized operator should run the following PowerShell commands, elevated
only if needed. Verify this is a new/intended private directory and not an IIS
site, alias, share or reparse point. If it already contains documents, inspect
ownership/access before changing ACLs; do not overwrite, move or delete them.

```powershell
$invoiceRoot = 'C:\MicrocomPrivateDocuments\Invoices'
New-Item -ItemType Directory -Path $invoiceRoot -Force
$invoiceAccount = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
icacls $invoiceRoot /inheritance:r
icacls $invoiceRoot /grant:r "${invoiceAccount}:(OI)(CI)M" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F'
icacls $invoiceRoot
```

Use the account that actually runs Django; an elevated terminal under a different
account must not accidentally substitute its identity. Do not grant Everyone,
Users or IIS identities unless independently required and authorized. Restart
the Django server normally after setup so `.env` is reloaded. Do not add a public
route for this folder. Existing artifact references must continue resolving to
their original private storage; this checkpoint found no previously configured
root in the inspected development environment.

## Behavior

- Detail: one **Print Invoice / Imprimer la facture** POST action opens a new tab.
- `/invoices/<id>/print/` uses the existing active Django language (LocaleMiddleware /
  `django_language` cookie), normalizing French variants to `fr`, otherwise `en`.
  It creates/reuses a finalized invoice's artifact, then redirects to the protected
  GET `/invoices/documents/<artifact>/download/` endpoint, now served inline.
- Existing explicit-language POST PDF routes remain for compatibility; no separate
  language buttons are shown. All downloads still authenticate/authorize.
- List: the Rapport matériel GET form conventions are reused (Search, Date From,
  Date To, Filter/Clear, responsive grid and table). Status adds All/Draft/Finalized.
  Search covers invoice number, request reference and frozen succursale code/name;
  drafts also search the linked branch because no issued snapshot exists yet.
  Dates are inclusive official invoice issue dates; drafts have NULL issue dates
  and are excluded by date filters. Invoice pagination remains 25 rows, with
  filters retained in navigation. Rapport matériel itself has no pagination and
  filters request Date Needed; those behaviors cannot be copied for invoices.
- **Print Filtered Invoices / Imprimer les factures filtrées** posts the applied
  filters to the existing `/invoices/print-selected/` route in a new tab (the route
  name is retained for compatibility; it no longer accepts checkbox selection).
  Both issue dates are mandatory. The server validates dates/order/status/search,
  rebuilds the authorized scope and prints ALL matching FINALIZED invoices,
  independent of pagination or supplied IDs/counts. A Draft status filter yields
  no printable matches. Results sort by issue date, official number, then PK.
- A batch is limited to 20 invoices, 50 MiB of source/combined bytes and 200 pages.
  An oversized result is rejected in full with a bilingual narrowing instruction;
  nothing is silently truncated. Empty results have a bilingual explanation.
  Every selected invoice is authorized and checked for finalization before any
  PDF generation. Source generation and download also revalidate access.
- Existing valid current-renderer/language artifacts are reused. The merger reads
  only checksum-verified generated sources, retains all their pages, and starts
  each invoice on a new page. It does not import annotations/actions/attachments.
- The combined PDF is transient in memory, not a new financial document or stored
  artifact. Individual source artifacts remain append-only. A failed later batch
  step may leave valid newly generated individual renditions; it changes no invoice.
- PDF responses use `inline`, `private, no-store`, and `nosniff`. The browser's PDF
  viewer provides print/save controls; no forced download or automatic print dialog.
- Permission behavior is unchanged: `view_invoice` plus existing object scope.
  CSRF protects generation POSTs. No finalization or stock service is called.
- Storage, database and merge failures show sanitized bilingual messages. No private
  path, token, SQL or document content is included in those error messages.

`pypdf==6.21.2` is pinned in requirements and installed in the local venv. It is
used solely to combine trusted generated documents. Other environments must
install the pinned dependency through their normal deployment procedure.

## Offline validation

    .\venv\Scripts\python.exe -B local_artifacts/test_invoice_printing_offline.py

Synthetic settings, blocked database/network calls, mocked permissions/ORM and
actual in-memory EN/FR PDFs cover language selection, protected POST/GET routes,
CSRF, inline headers, selection/draft/authorization rejection, limits, page order,
storage path safety, checksum checks and existing rendition reuse. These tests do
not prove real database permissions, transaction/file coordination or browser UX.

The original printing implementation passed 68 offline checks. The filter update
adds focused form, scope, date, all-page selection, limit, translation and template
checks. These mocked checks do not establish actual PostgreSQL filtering behavior.
Updated result: **81 passed, 0 failures/errors**, including 13 filtered-printing
checks and the 18 prior printing checks. Six changed/new Python files compile;
25 filter/printing messages have French catalogue entries and matching
interpolation placeholders. PostgreSQL query compilation is checked without
opening a connection. All application/database settings remain untouched.
Database/network connection attempts during validation: **zero**. Two synthetic
temporary test directories from an initial Windows cleanup failure were verified
and removed; no existing artifacts or disposable PostgreSQL folders were touched.

## Manual development verification after operator setup

1. Sign in as an authorized invoice viewer; keep Bon de retour disabled.
2. Open the existing finalized invoice. In French, click **Imprimer la facture**:
   confirm a French inline PDF and working browser print/save controls.
3. Switch the application to English and repeat; expect an English rendition.
4. Repeat the same-language action: verify existing valid rendition reuse rather
   than another READY artifact (through separately authorized read-only inspection).
5. Apply both official issue dates, optional search and status on the list, then
   print filtered invoices; verify all authorized matches, issue-date/number
   order, all pages, and a fresh page for each invoice. Test one if only one exists;
   do not create financial records solely for this check without authorization.
6. Confirm missing/invalid/reversed dates are rejected, no-match filters explain
   the result and ranges over 20 matches require narrowing. With approved security
   testing, verify client IDs/counts/pages cannot override filters or permissions,
   and drafts/unauthorized invoices are never included.
7. Verify unauthenticated direct artifact URLs require login, protected downloads
   recheck access, and the filesystem path is not exposed by any public URL.
8. Confirm invoice references, totals, snapshots, stock and audit history remain
   unchanged. PDF rendition metadata is expected to be created on first printing.

Database-backed integration/concurrency, actual directory ACL/IIS checks and
browser tests remain outstanding. No migrations, commits or deployment included.
# Client-only invoice layout (renderer v4)

Newly requested renderings use `invoice-a4-v4-rl5.1.0`. The visible document
omits company name, company address, contacts, and succursale address. Client
identification uses only the finalized branch-name snapshot: `Client: ...` in
English and `Client : ...` in French. Company data remains in the immutable
snapshot; PDF author metadata is blank. Snapshot validation and frozen-branding
integrity checks remain in force.

Artifact reuse is scoped by invoice, language, and renderer version. Old PDF
artifacts remain unchanged and downloadable by their existing protected URLs.
A separately authorized future print request can append a v4 artifact; it does
not replace a v3 file or change financial records. Bulk printing uses the same
versioned generation service.

Safe verification now: run `venv\Scripts\python.exe
local_artifacts/test_invoice_printing_offline.py`. It uses synthetic settings,
blocks database/network connections, and renders synthetic PDFs in memory.
Real invoice printing and database integration checks remain separate,
explicitly authorized steps.
