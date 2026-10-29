# Checkpoint E-R3 — Material Return Note interface and bilingual PDF

Status: implemented behind a disabled activation gate; database-free validation
only. E-R2 remains database-unvalidated. Neither checkpoint is approved for
activation by the results recorded here. No E-R4 work was performed.

## Business behavior and integration

Bon de retour is an optional valuation of materials already physically returned
through the existing stock-return workflow. Creating/viewing/rendering a note
never calls that workflow or creates another stock movement. It is not a credit,
payment adjustment or refund. Original facture/request/approval/stock evidence
and financial calculations are unchanged by this checkpoint's implementation.

When activated separately, authorized staff can open issuance/history from a
finalized facture, the existing Return to Stock form, or request detail. The
physical-return POST, stock service, success messages and redirect remain exactly
as before. Document creation is a separate explicit action, never an automatic
side effect of returning materials. Links on older pages issue no additional
ORM/permission queries while the feature is disabled.

## Activation and authorization

`MATERIAL_RETURN_NOTE_UI_ENABLED = False` is explicitly set in application
settings. Access helpers also default to false if the setting is absent. No
environment variable is read for activation. It was not enabled in any deployment
or development environment. Offline tests mock the gate function; they do not
set the feature setting to true. Every new route returns 404 while disabled,
including PDF generation and direct downloads. Public document service entry
points also enforce the gate. No roles or permissions are granted.

E-R2's fresh staff/action/stock-review authorization is reused. Read access
requires `view_invoice` and `view_materialreturnnote`; selection/issuance require
`issue_materialreturnnote` and `add_materialreturnnote` as well. Document access
additionally requires existing `view_materialreturnnote_document`, checked both
when generating and when downloading, including direct artifact URLs. The new
`document=True` authorization option is backward compatible; invoice action
authorization and E-R2 financial logic were not modified.

History first authorizes the original facture scope and paginates note IDs,
then retrieves each displayed note through E-R2. Detail and PDF snapshots use
E-R2 retrieval, with document permission rechecked after the rendering lock wait.
History is limited to 25 notes per page; fresh per-note authorization may add
queries, which remains a performance item for later database validation.

## Routes and pages

All paths are beneath the existing `/invoices/` include:

| Method | Path | URL name |
| --- | --- | --- |
| GET | `<invoice_id>/return-notes/new/` | `return_note_select` |
| POST | `<invoice_id>/return-notes/preview/` | `return_note_preview` |
| POST | `<invoice_id>/return-notes/issue/` | `return_note_issue` |
| GET | `<invoice_id>/return-notes/` | `return_note_history` |
| GET | `return-notes/<note_id>/` | `return_note_detail` |
| POST | `return-notes/<note_id>/pdf/<language>/` | `return_note_pdf` |
| GET | `return-note-documents/<artifact_id>/download/` | `return_note_download` |

Selection shows E-R2 eligibility decisions and translated ineligibility reasons,
whole quantities, return dates and frozen facture descriptions. Staff choose
complete eligible movements, mandatory reason and a verified annual series.
There are no editable quantity/price/currency/total fields. Empty eligibility or
missing verified numbering disables preview, while existing history remains
available. Page templates use existing responsive table wrappers, buttons and
messages; checkbox labels support keyboard/screen-reader use.

## Confirmation and replay

All financial decisions are delegated to E-R2: eligibility, preview, cumulative
rounding/caps, credit exclusivity, issuance/replay and finalized retrieval. Views
perform no financial arithmetic. Display-only joins remain request-scoped and
use frozen facture descriptions, not current catalogue prices.

Server-side session storage retains original submitted arguments, E-R2 signature
and issuance UUID. The browser receives only a random opaque 32-hex handle,
CSRF token, acknowledgement and an explicit allowlist of display data. Signatures,
issuance tokens, state digests and raw audit payloads are not sent to templates,
URLs, messages or logs. Client-submitted financial fields are ignored. Cookie-
stored session backends are rejected; known server-side session engines are
allowlisted. No `set_expiry` call or global lifetime change was introduced.

The existing 900-second session timeout is preserved. E-R2 still checks its
two-hour signature age for a new issuance. A successful submission retains its
session handle so a lost response/double submit can pass the exact original
payload to E-R2. Views do not recheck current eligibility or reject old signatures
before E-R2's committed-replay decision. Success redirects to immutable detail.

Independent tabs receive independent handles; storage is bounded at 32 handles.
The oldest handle is evicted on overflow, causing a safe unavailable-preview
message. Missing/expired session handles direct users to facture history before
starting again. Stale/expired E-R2 previews require another preview; permission
changes deny access. Concurrent writes to an actual session backend can lose a
handle under last-writer-wins behavior. The result fails closed with history
recovery, but concurrent multi-tab persistence is not proven by mocked tests.

Issuance/selection/preview and generation views are non-atomic request boundaries,
allowing E-R2 and artifact services to own durable transactions. CSRF middleware
and POST-only routes protect mutation endpoints. Private pages use no-store
caching. Internal storage/database exceptions are translated or sanitized.

## PDF and protected artifacts

Separate English and French A4 documents follow the existing logo-free facture
style: centered company header, black/grey table, embedded Vera fonts, repeated
table headings, page numbers and document-reference footer. French accents,
escaped descriptions, fractional quantities, four-decimal prices, zero values
and multiple pages are covered by synthetic rendering checks.

The document includes note number/date; original facture number/date/value;
request reference; frozen company/contact/branch snapshots; material descriptions,
return movement references and whole quantities; original frozen prices/currency;
this note's value; cumulative returned value and adjusted net material value as
of issuance; reason; explicitly labelled French amount wording; Stock Department.
There is no total-payable heading or computed payment balance. Original French
amount wording is retained in both languages. Frozen branding integrity is
checked where present, but no logo or external asset is drawn/fetched.

Rendering consumes detached immutable values only, without following mutable
material/company relations or recalculating valuation. Artifact ownership uses
the existing E-R1 `MaterialReturnNoteArtifact`; no migration was needed.

Private storage reuses existing validated `INVOICE_DOCUMENT_ROOT`, under a
`return-notes` child directory. It rejects links/junctions, traversal and nonopaque
references; UUID filenames are created exclusively without overwriting existing
files. Downloads verify READY status, PDF header, size limit and SHA-256 checksum
after authorization, and send private/no-store and nosniff headers.

Generation serializes by note, reuses a valid language/version artifact, and
creates append-only READY/FAILED attempts. Rendering occurs after issuance has
committed. A PDF failure never reissues a note or changes numbering. Partial files
or a file left after metadata commit failure may remain as private orphans; no
automatic cleanup is implemented and no download can access one without a READY
artifact row. Real filesystem/transaction coordination remains unvalidated.

## Exact implementation files

Created:

- `invoicing/return_note_access.py`
- `invoicing/return_note_forms.py`
- `invoicing/return_note_views.py`
- `invoicing/return_note_documents.py`
- `invoicing/return_note_pdf.py`
- `invoicing/templatetags/__init__.py`
- `invoicing/templatetags/return_note_navigation.py`
- `invoicing/test_return_note_views.py`
- `invoicing/test_return_note_documents.py`
- `invoicing/test_return_note_pdf.py`
- `templates/invoicing/return_notes/links.html`
- `templates/invoicing/return_notes/select.html`
- `templates/invoicing/return_notes/preview.html`
- `templates/invoicing/return_notes/detail.html`
- `templates/invoicing/return_notes/history.html`
- `templates/invoicing/return_notes/pdf_error.html`
- `local_artifacts/checkpoint_er3_static_review.py`
- `local_artifacts/checkpoint_er3_translations.py`
- `docs/PHASE2_STAGE3_CHECKPOINT_E_R3.md`

Modified:

- `config/settings.py` (only the default-off feature assignment/comment)
- `invoicing/permissions.py` (additional document-access option)
- `invoicing/urls.py`
- `invoicing/views.py` (facture-detail navigation context only)
- `templates/invoicing/detail.html`
- `templates/requests_app/request_detail.html`
- `templates/requests_app/return_material_to_stock.html`
- `locale/fr/LC_MESSAGES/django.po`
- `locale/fr/LC_MESSAGES/django.mo`

New evidence includes `local_artifacts/checkpoint_er3_baseline.json`, standalone
offline run logs, JSON results and synthetic PDFs/text under
`local_artifacts/checkpoint_er3_evidence`. Existing E-R2 evidence and cluster were
not queried, modified, stopped or deleted. New synthetic file-test directories
are retained; no existing development files were removed.

## Validation actually completed

Final standalone offline run: **31 passed, 0 failures, 0 errors, 0 skipped**.
Nine templates compiled. All 76 literal messages across the return-note modules
and templates have matching French PO/MO entries (identical EN/FR terms such as
Page/Succursale are valid translations). Syntax and whitespace checks pass.

The runner configures standalone synthetic Django settings without importing
`config.settings`, loading `.env`, supplying database settings or changing
environment variables. It uses standard unittest, not Django's database runner.
Database connection and outbound-socket attempts are blocked and counted: zero.
No PostgreSQL processes, SQL commands, tests or migrations were executed.

Tests cover disabled routes/services/navigation, HTTP methods/login, CSRF rejection,
opaque confirmation privacy, saved-payload forwarding and replay, independent
handles/cookie-backend refusal, permission denial, empty eligibility and bilingual
messages, history's E-R2 retrieval, document permission before bytes, sanitized
errors, immutable snapshot detachment, checksum/header/path checks, artifact
reuse/failure handling, and synthetic bilingual PDF contents/pagination/precision.

The initial offline harness had 19 passes and nine errors caused by missing
synthetic STATIC_URL and Python mkdtemp's restrictive Windows ACL. The fixture
now creates unique workspace directories with ordinary inherited ACLs; no ACL
was changed. The next run passed 28 tests; three additional boundary tests bring
the final run to 31. Earlier run results are preserved, not presented as final.

Baseline hashes verify existing stock/request business code, E-R2 financial
services/tests, models, migrations and invoice financial/PDF services remain
unchanged. This is source preservation, not empirical database preservation.

## Outstanding validation and activation boundary

E-R2's 42 database test methods and remaining boundary coverage, E-R1/E-B suites
and full regressions remain outstanding. E-R3 additionally needs real database
HTTP/session/permission integration, exact replay after response loss, session
concurrency, artifact row locks/concurrent rendition requests, metadata commit
failure and filesystem recovery, and source-data preservation assertions.

Browser visual/accessibility checks at actual responsive viewport sizes and
production private-storage permissions remain pending. Synthetic PDF text/layout
tests are not a visual sign-off or proof of real data correctness. No schema,
dependency, stock-workflow or invoice-calculation deviation was introduced.
Activation and database testing require separate authorization and successful
validation. The E-R2 disposable-cluster recovery issue remains unresolved.
