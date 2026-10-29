# Phase 2 / Stage 3 / Checkpoint D

The subsequent [PDF design refinement](PHASE2_STAGE3_CHECKPOINT_D_REFINEMENT.md)
replaces the logo-bearing layout described below with a compact text-only v2 design.

Local professional invoice PDFs and protected downloads. No production, shared or
existing development database is used. No commit, push, deployment, invoice lifecycle,
approval, stock-service or prior migration change belongs to this checkpoint.

## Snapshot and layout design

The renderer accepts a detached dictionary of finalized snapshot values. It never
follows company, material, succursale, actor or catalogue relations. Company name,
address/contact, branch code/name, request reference, line code/description/unit,
quantities/prices/totals/currency, issue date/number, note and French words are frozen
by Checkpoint C. The renderer formats stored Decimal values; it does not price,
sum, convert currencies, calculate taxes or regenerate French words.

The A4 portrait layout includes verified company information and proportionally
scaled frozen logo, invoice heading/reference/date, succursale/request references,
four-column material table, amount payable/currency, stored French “Nous disons”
on both languages, comments and localized Stock Department / Service Stock label.
This is a department identification, not a fabricated named employee or signature.
There are no invented addresses, registration/tax identifiers or payment instructions.
Repeated table headings and page-number/reference footers support multiple pages;
exceptionally long descriptions can split within a row. The summary stays together
when it fits on one page.

Snapshot version 1 is required. Incomplete snapshots fail with administrator-review
messages; they are never repaired or reconstructed from live settings. Embedded
PNG/JPEG/WebP branding is decoded from the frozen bytes with size, signature,
content-type and SHA-256 checks. A deliberately frozen no-logo strategy stays blank.
Missing font glyphs block rendering rather than silently substituting squares.

## Dependencies and fonts

Existing Windows x64 Python 3.14.4 and Django 6.0.4 are retained. Only these packages
were added to the existing local venv and pinned in requirements.txt:

| Package | Version | License |
| --- | --- | --- |
| reportlab | 5.1.0 | BSD |
| pillow | 13.0.0 | MIT-CMU |
| charset-normalizer | 3.5.2 | MIT |

The latter two are required ReportLab dependencies. The resolver selected compatible
Windows/Python 3.14 wheels; no existing dependency or pip was replaced, and no global
software, PDF viewer, commercial ReportLab product or optional acceleration package
was installed. requirements.txt retains its original UTF-16 encoding.

ReportLab's bundled Bitstream Vera regular/bold fonts are subset-embedded; no Windows
proprietary font is copied. Accented French, œ, curly apostrophes, em dash, € and $
are covered. The bundled font copyright/permission notice is retained in the package
and included in PDF subject metadata. Other writing systems/unsupported glyphs need
a separately reviewed font and renderer revision. Dependency pin changes require
renderer-version review and regression testing.

Assessment sources: [PyPI metadata](https://pypi.org/project/reportlab/5.1.0/),
[ReportLab installation](https://docs.reportlab.com/install/open_source_installation/).
Exact resolver/install reports and wheel hashes are retained under local_artifacts.
No claim of exhaustive third-party vulnerability certification is made.

## Artifacts, permissions and retries

Finalization remains unchanged. A separate CSRF-protected POST generates/downloads
the chosen English/French rendition. The generator rejects any outer transaction
and accepts only an already-finalized invoice; its endpoint explicitly opts out of
ATOMIC_REQUESTS. Thus it cannot render within an uncommitted finalization transaction.

A separate durable transaction locks the existing invoice row to serialize rendition
requests across processes. An intact READY artifact for the invoice/language/renderer
version is reused. A missing/damaged file permits a new rendering-only attempt.
Different languages also serialize conservatively. Ordinary approval/stock services
do not acquire this invoice lock and were not altered.

DocumentArtifact remains append-only. Each completed attempt appends READY or FAILED;
there is no mutable PENDING-to-READY update. Records include owner, language, renderer
version, opaque relative filename, checksum, creator and time. FAILED uses an empty
content digest and a reserved filename with no downloadable content. No financial
audit event, number, sequence, total, snapshot or inventory record is changed.
An error is raised after committing the FAILED attempt so a controlled retry can
append a new attempt. SQL/connection failure can still prevent recording an attempt.

Generation and each download require the existing view_invoice permission AND the
existing request-level scope. No new grants or alternative admin bypass exist.
Download lookup accepts only numeric artifact IDs, never client-supplied paths.
Files are read only after authorization, with a 25 MiB bound and checksum verification,
and served as attachments with private/no-store and nosniff headers. Anonymous,
unscoped, permission-less, forged, missing and corrupt artifact requests fail closed.

## Required private storage configuration

INVOICE_DOCUMENT_ROOT is an explicit absolute directory setting (environment value
in normal config.settings), disabled by default. Do not point it at the repository,
an IIS site root, a public directory or a network share served to users. The service
rejects media/static overlap, symlink/junction components and non-opaque references.
No route exposes this root through MEDIA_URL or static handling.

Before any future real-environment enablement, an operator must create a private
directory outside all IIS/web roots, grant only the application identity and
authorized backup/operators filesystem access, configure the setting, and verify
IIS has no alias/virtual directory exposing it. This checkpoint does not alter IIS,
services, ACLs or existing local/staging configuration. Tests override the setting
to private disposable directories and never load normal .env.

Privileged filesystem/database owners remain outside application access controls.
DB and filesystem commits cannot be one atomic operation: a crash or DB failure
after writing can leave an opaque private orphan without a READY row. Such a file
is not downloadable through these endpoints. Retention/orphan cleanup needs a
separately approved operational procedure; append-only evidence is not deleted here.
Back up DB and private artifacts together. Do not overwrite finalized financial
snapshots to fix rendering problems. A new render can differ in PDF creation metadata
and checksum while retaining the identical stored financial content.

## Verification and scope

The guarded runner creates a fresh PostgreSQL 18.6 cluster, random ephemeral role
credentials and synthetic-only test database. It verifies database, role, localhost
address/port, data directory, server version and postmaster identity before writes
and on new connections. Existing staging port55440 and other databases are unused.
This is PostgreSQL18.6 coverage, not exact production18.4 verification.

PDF tests cover actual content extraction, UTF-8/French labels and words, prices,
amounts, stored logo, mutable catalogue/config independence, access/CSRF, checksums,
tampering/missing files, duplicates/concurrency, failed renderer/storage retries,
commit boundaries, zero-price EUR, 66 real lines and oversized descriptions. They
compare complete synthetic request/approval/movement/material, invoice, sequence
and financial audit states before/after rendering.

Visual checks use Windows.Data.Pdf through the built-in Windows Runtime; no viewer
dependency was installed. Actual rendered page PNGs are inspected and retained,
alongside PDFs, extracted text and guarded PostgreSQL test/migration reports.
The test-only PDF text reader supports ReportLab's emitted syntax, not arbitrary
untrusted PDFs. The final test counts and retained evidence paths are appended below.

No new migration is required. Existing guards, lifecycle, correction/resubmission,
stock operations, Bon de sortie, reports and Excel behavior remain unchanged.
Production privilege review, historical stock reconciliation, operational private
storage/backup configuration and separately authorized deployment remain outstanding.
Checkpoint E is not implemented or authorized by this work.

## Exact checkpoint file manifest

Modified: config/settings.py; requirements.txt; invoicing/views.py;
invoicing/urls.py; templates/invoicing/detail.html;
locale/fr/LC_MESSAGES/django.po and django.mo.

Created: invoicing/pdf.py; invoicing/documents.py; invoicing/pdf_test_tools.py;
invoicing/test_documents.py; templates/invoicing/pdf_error.html;
local_artifacts/test_checkpoint_d_runner.py;
local_artifacts/checkpoint_d_translations.py;
local_artifacts/checkpoint_d_render_preview.ps1;
local_artifacts/checkpoint_d_verify.py;
local_artifacts/checkpoint_d_retain_evidence.py; this document;
local_artifacts/checkpoint_d_dependency_plan.json and checkpoint_d_dependency_install.json.

All other pre-existing tracked and untracked work is preserved.

## Final recorded results

- Complete suite: **317 run, 316 passed, zero failures/errors, one existing optional
  sample-generation skip**, 438.843 seconds on disposable PostgreSQL18.6.
- After the last PDF spacing/summary and failure-cleanup refinements: **17/17 PDF
  tests passed**, 69.620 seconds on another fresh disposable PostgreSQL18.6 cluster.
- System checks, dry-run migration consistency, pip dependency checks, protected
  source/migration hashes and whitespace checks passed. All 42 PDF-related source/
  template messages checked have French catalogue entries; actual EN/FR PDF content
  and validation tests also pass. The original PO/MO entries are retained.
- Final PDFs were rendered with Windows.Data.Pdf and inspected: English/French
  single-page layouts, pages3/4 of the four-page 66-line invoice, pages4/5 of the
  five-page French long-description invoice and page2 of its English counterpart.
  Accents, œ, €, $, escaped literal text, logo proportions, alignment, repeated
  headings, complete ending text, totals, wording and footers were readable.
- Retained evidence: `local_artifacts/checkpoint_d_evidence_f8b25508/`, containing
  full-suite-results.json, final-pdf-results.json, four existing migration reports,
  dependency reports, verification-summary.json, cleanup.json, port-checks.json,
  five synthetic PDFs, their rendered page PNGs and extracted EN/FR text.
- All seven checkpoint-created disposable directories were removed after checking
  resolved workspace paths, no reparse points and absent postmaster PID files.
  Each started cluster had been stopped successfully by pg_ctl. Exclusive binds
  confirmed localhost ports15486/15487/15488 and55443 free. Port55442 could not be
  rebound; earlier inspection showed an unrelated outbound client connection using
  that port. It was not modified or mistaken for an owned PostgreSQL process.
  Existing staging55440 and all system services remain untouched.

Recommendation: **GO for Checkpoint D review**, not production deployment.
Configure and independently verify private storage/ACL/IIS/backup safeguards before
any real use. Historical production reconciliation and database privilege review
remain separate outstanding requirements. Stop before Checkpoint E.
