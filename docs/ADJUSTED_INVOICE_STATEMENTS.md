# Adjusted Invoice Statements — implementation and review handoff

Date: 2026-11-11. Base: `42ceeff2c9d8b6c43047cfd8f7e3a70c441fa7e1`.
Worktree: `C:\Users\Administrator\microcom-adjusted-statements`.
Branch: `feature/adjusted-invoice-statements`. No commit, push, staging or deployment.

## Implementation

Authorized users can open a finalized invoice's Adjusted Invoice Statements section, inspect current original/returned/net quantities and values, review exact issued BR references, preview without allocating a number, explicitly confirm issuance, reopen immutable historical statements, and print/download EN or FR PDFs. Invoice detail includes the valuation summary and statement history only when enabled and authorized. No BR means no issuable adjusted statement.

`ADJUSTED_INVOICE_STATEMENTS_ENABLED` is strictly default-off: an absent setting or any value other than boolean `True` disables the feature. Production settings were not edited. Disabled routes return 404 before authentication/model lookups; disabled navigation and sequence-admin checks do not query the new table. Test environments explicitly enable it.

The original invoice, original invoice PDF, BR issuance/finalization and stock services are unchanged. The new SQL snapshot function first calls the existing authoritative `inv_rn_validate` ledger validator. Material returns and monetary amounts are aggregated from finalized BR lines; original quantities/prices/values come from frozen invoice lines. The latest validated BR supplies cumulative returned/net invoice totals. No catalogue repricing or independent quantity-times-price return valuation occurs. Pre-finalization returns remain excluded from the invoice and cannot be counted again.

## Example verified through services, tests and a real isolated browser

| State | Original invoice | Documented returns | Adjusted value | Returned / net quantity |
|---|---:|---:|---:|---|
| First BR | 1,000.00 USD | 200.00 USD | 800.00 USD | 2 / 8 |
| Second BR | 1,000.00 USD | 300.00 USD cumulative | 700.00 USD | 3 / 7 |

The earlier statement still shows 800.00 after the second BR and later statements. Issuing statements does not restore stock, modify invoice totals, create credits or adjust a payment balance. The exact mandatory EN/FR clarification is included in the UI and PDFs.

## Proposed database changes — production NOT migrated

1. `0008_adjusted_invoice_statements`: adds the `ADJUSTED` document-sequence choice and `AdjustedInvoiceStatement` table. Fields include invoice/sequence/issuer protected references, unique permanent number, unique sequence/counter, unique invoice/reconciliation state, DB-stamped issue time, business date, frozen issuer name, unique operation UUID, confirmation digest and complete JSON valuation snapshot.
2. `0009_adjusted_statement_guards`: adds the canonical BR-backed snapshot function, insert validation, immutable UPDATE/DELETE and TRUNCATE guards, issued sequence identity protection, and broadens the existing shared document-reference registry to include `ADJUSTED`. There is no financial-data rewrite, backfill, sequence creation or permission assignment.

Snapshots contain company, succursale, branding, currency, invoice/request references, original invoice total, original/returned/net line quantities and values, original unit prices, movement IDs, and the exact included BR references/dates/totals. The row itself is append-only issuance/audit evidence with issuer identity, timestamp, token and confirmation digest.

3. `0010_adjusted_statement_state_uniqueness`: defines immutable PostgreSQL `inv_as_state_key(jsonb)` and a unique expression index `as_invoice_state_unique` on invoice plus reconciliation identity. The key hashes the frozen invoice identity and sorted immutable issued-BR IDs, independent of preview UUID, actor, language, series, BR-list order or timestamp text formatting. Frozen source documents make this an identity for their complete valuation state, including zero-value BRs that change quantities.

The migration checks for pre-existing duplicate states first and aborts atomically if any exist. It never deletes, renumbers or merges issued history. This was verified against the earlier duplicate-filled synthetic capture database: statements, counters, migration history and function registration were unchanged after rejection. A clean isolated test database applied all three proposed migrations successfully. If another installation already contains duplicates, review is required before migration; no automatic remediation is included.

Migration reversal refuses to remove these guards once statements exist. After issuance use a forward fix or disable the UI; do not delete statement records or fake migration state. Schema downgrade was not executed after issuance: its rejection was tested atomically.

## Permissions and numbering

Grant only designated users/groups:

- `invoicing.view_invoice` plus `invoicing.view_adjustedinvoicestatement` to view.
- Additionally `invoicing.issue_adjustedinvoicestatement` to preview/issue.
- Additionally `invoicing.document_adjustedinvoicestatement` to print/download.

Existing stock-review request scope applies, including existing staff/global-scope rules. Services refresh actor permissions from the database. There is no new automatic employee/group grant; Django's existing superuser semantics remain unchanged.

An authorized administrator must create an independent `DocumentSequence` of type `ADJUSTED`, choose the current company business year and series (default `MAIN`), set its verified starting counter and attest external numbering history through the existing Admin workflow. Suggested format: `EAR/{number:06d}/{year}`. No numbering record is created automatically. The final number is also inserted into the shared global reference registry, preventing collisions with invoice/BR/credit references.

## Integrity and concurrency

Issuance uses an outermost durable READ COMMITTED transaction, the same per-invoice advisory coordinator as BR/credit issuance, invoice/request locks and a sequence lock. Snapshot evidence is rechecked after the preview and by the database at INSERT. A concurrently issued BR either follows a consistent earlier statement or makes the preview stale; no mixed snapshot is accepted.

Signed confirmations bind invoice, actor, series, preview digest, business date and UUID. Exact successful submission retries return the original statement, including retries after confirmation expiry. Separate valid previews for an already-issued state also return that statement before sequence lookup/increment, even for a different authorized issuer or series. A historical matching state is returned after additional BRs or expiry without issuing anything new. Expired/stale/tampered confirmations that would create a new statement still fail. A fresh preview after an additional BR has a different state key and may issue a new immutable statement. The database unique index independently rejects duplicate INSERTs even if model/service validation is bypassed; failed attempts roll back sequence changes. Sequence increments roll back with failed issuance. Negative values, forged snapshots, ambiguous BR ledgers and wrong-source evidence fail closed.

## Isolation and verification

A fresh PostgreSQL 18 cluster was created at `127.0.0.1:55461`. Databases: `microcom_adjusted` and `test_microcom_adjusted`. Its random application role has no superuser, CREATEDB, CREATEROLE, INHERIT, replication, bypass-RLS privileges or role memberships. HBA allows that role only its two databases. A custom backend rejects any other database/host/port/role before connection. No production settings, credentials, backup, media or data were used. Startup verifies actual database identity and role privileges before migrations/tests.

The isolated interpreter uses dependency versions matching repository requirements (Django 6.0.4, psycopg2 2.9.11, ReportLab 5.1.0, pypdf 6.21.2). Playwright 1.64.1 and PyMuPDF 1.26.7 were installed only in its private virtual environment for browser/PDF QA. No production dependency was installed or changed.

### Commands actually executed

Private prefix:

```powershell
$py = 'C:\MicrocomIsolated\adjusted-20261111\venv\Scripts\python.exe'
$manage = 'C:\MicrocomIsolated\adjusted-20261111\manage_isolated.py'
& $py -B $manage migrate --noinput
& $py -B $manage check
& $py -B $manage makemigrations --check --dry-run
& $py -B $manage migrate --plan
```

The combined standard DiscoverRunner invocation was:

```powershell
& $py -B $manage test invoicing.test_adjusted_statements invoicing.test_adjusted_pdf invoicing.test_lifecycle.InvoiceLifecycleTests invoicing.test_list_presentation.InvoiceListPresentationTests invoicing.test_detail_presentation.InvoiceDetailPresentationTests invoicing.test_return_note_pdf invoicing.test_return_note_clock_offline --keepdb --noinput --verbosity 1
```

It ran through the private `run_final.py` harness, which recreated only the isolated test database before invoking that command. **96 tests passed**, zero final failures/errors (41 feature/service/UI tests, four new PDF tests and 51 existing regressions). The fresh database included migration `0010`.

Earlier initial implementation checks (superseded by the combined 96-test run above):

```powershell
& $py -B $manage test invoicing.test_adjusted_pdf invoicing.test_adjusted_statements.AdjustedStatementTests.test_bilingual_pdf_and_historical_values invoicing.test_adjusted_statements.AdjustedStatementTests.test_bilingual_ui_history_and_protected_download --keepdb --noinput --verbosity 1
& $py -B $manage test invoicing.test_adjusted_statements.AdjustedStatementTests.test_stock_and_invoice_unchanged_by_statement --keepdb --noinput --verbosity 1
```

During initial implementation, the layout/UI group passed **6 tests** and the stock/invoice recheck passed **1 test**; these methods also pass in the latest combined run. Seven unchanged existing BR regression method bodies passed during initial implementation (not rerun in this duplicate-state follow-up) via private `run_br_regressions.py`, each using a freshly recreated isolated database instead of unsafe ledger TRUNCATE cleanup. This includes two real independent-connection concurrency cases. The new suite includes three additional real concurrency cases: same-token replay, concurrent separate previews returning one statement/reference and a BR/statement race.

The seven existing BR methods were:

- `test_complete_return_preserves_original_facture_and_stock`
- `test_multiple_whole_movements_round_cumulatively_and_cap`
- `test_precutoff_equal_future_excluded_and_wrong_type_rejected`
- `test_exact_replay_after_expiry_no_duplicate_audit_counter_or_number`
- `test_catalogue_and_company_changes_do_not_reprice_or_change_snapshots`
- `test_same_token_concurrent_exact_replay_commits_once`
- `test_concurrent_stock_return_stales_preview_without_second_inventory_adjustment`

The BR method harness executes the unchanged setup/assertions with `unittest.FunctionTestCase`; it does not claim the original TransactionTestCase suite/flush lifecycle passed. It physically disposes of each dedicated test database, leaving all production audit/immutable guards enabled. New tests use unique committed synthetic fixtures and dispose of the whole isolated database rather than flushing protected ledgers.

Initial development runs found test-fixture/helper mistakes, all corrected. The first duplicate-state run also required changing the existing SQL-tamper test to use a raw INSERT, because the new model constraint correctly rejected its duplicate before reaching the database trigger; the final SQL guard test and 96-test run pass. The first combined run also exposed an existing PDF test's missing `local_artifacts` parent directory; creating that ignored local artifact directory fixed the setup issue without changing the existing test. No remaining failure is classified as pre-existing or hidden. No full application-suite pass is claimed.

Actual Microsoft Edge validation completed EN and FR overview, preview, confirmation, issuance, protected PDF download and historical statement display against the isolated server on port 8027. External browser requests were blocked. The latest EN/FR duplicate-preview browser flows return the exact existing statement URL and PDF, preserve the earlier 800.00 statement, and consume zero sequence numbers. The demonstrated invoice has exactly two states before and after the duplicate requests. At that earlier verification stage, both example PDFs were one-page landscape A4 (superseded by the portrait correction below); every example page was rasterized and text bounds checked. EN/FR rendered pages and screenshots were visually inspected. Large multi-page tables and long descriptions passed automated PDF tests. The physical printer, mobile browsers and production accounts were not exercised.

Direct isolated PostgreSQL probes confirmed statement TRUNCATE and unsafe schema reversal are rejected; record counts remained unchanged, audit triggers stayed enabled and `session_replication_role` remained `origin`. `check` and model/migration consistency passed. The migrated isolated test database has no pending operations, verified with:

```powershell
& $py -B 'C:\MicrocomIsolated\adjusted-20261111\manage_browser_v2.py' migrate --plan
```

The older synthetic capture database intentionally remains at migration `0009` because its legacy duplicates trigger the new safety preflight. No production migration was attempted. Git whitespace and Python syntax checks passed.

## Known limitations / review items

- PDFs are generated on demand from permanent snapshots; PDF bytes are not separately archived. Financial values, included BRs and frozen branding remain immutable. A later renderer change can alter layout, not the saved valuation.
- Exactly one permanent statement is allowed per invoice/reconciliation state. Legacy duplicate history, if present, blocks migration for review; it is never deleted automatically. SHA-256 state identity relies on the existing immutability of invoice and issued BR source records.
- No automatic statement is issued when a BR is issued. A user explicitly reviews/confirms a new statement.
- Statement history currently lists all statements for an invoice; unusually large histories may merit pagination later.
- Database constraints do not replace operator privilege separation: an owner/superuser with DDL rights can change database guards. Review production database role/ownership policy separately.
- No production migration duration/lock impact was measured. Review the additive DDL and shared-reference CHECK constraint against expected production volume before scheduling.

## Proposed deployment procedure — NOT executed

1. Review the complete code/schema/translation/test diff, reference format and state-uniqueness migration preflight. Authorize commit/push separately; neither has occurred.
2. Review in a nonproduction rehearsal, including production-role privileges and representative data volume. Plan a verified PostgreSQL backup and approved change window.
3. Deploy a reviewed release while retaining the default-off gate. Apply `0008`, `0009` and `0010` only under separate production authorization. Verify guards, existing invoice/BR behavior and permissions without fabricating production financial records.
4. Grant only approved users/groups the separate view/issue/document permissions; configure/attest the new ADJUSTED sequence for the business timezone/year/series.
5. Enable `ADJUSTED_INVOICE_STATEMENTS_ENABLED=True` only after explicit production activation authorization and a controlled service restart. No IIS change is required. This feature adds no static asset: it reuses existing `financial_documents.css`; normal release asset verification still applies.
6. Verify authorized navigation, unauthorized denials, no-BR handling, statement totals/references, historic preservation and EN/FR PDF delivery under an approved operational procedure. Do not create demonstration records in production.
7. If necessary, disable the feature and retain issued statements/migrations. Do not reverse/drop the schema once statements exist.

The temporary isolated browser server and PostgreSQL cluster are stopped after verification. Private credentials, profiles, clusters, logs and screenshots remain outside Git. The active release, original application files, IIS and Microcom service were not modified. Only the shared Git branch/worktree registration metadata was created as required to establish this feature worktree.

## Duplicate-state follow-up changes

Only these six project files changed during the duplicate-state follow-up:

- `invoicing/adjusted_models.py`
- `invoicing/adjusted_services.py`
- `invoicing/migrations/0010_adjusted_statement_state_uniqueness.py`
- `invoicing/test_adjusted_statements.py`
- `docs/ADJUSTED_INVOICE_STATEMENTS.md`
- `docs/adjusted-statement-verification.json`

Nine additional feature tests cover sequential separate previews/counter preservation, existing-state lookup across series, historical/expired retries after a new BR, raw-SQL duplicate rejection/rollback, canonical order-independent state identity, current authorization, bilingual duplicate redirects/PDFs, a new zero-value BR, and another authorized issuer. The earlier distinct-preview concurrency test now requires one statement/reference instead of two. Existing repeated-submission and new-BR/history tests remain in the suite.

## Exact changed-file manifest

- `docs/ADJUSTED_INVOICE_STATEMENTS.md`
- `docs/adjusted-statement-verification.json`
- `invoicing/adjusted_access.py`
- `invoicing/adjusted_models.py`
- `invoicing/adjusted_pdf.py`
- `invoicing/adjusted_services.py`
- `invoicing/adjusted_views.py`
- `invoicing/admin.py`
- `invoicing/migrations/0008_adjusted_invoice_statements.py`
- `invoicing/migrations/0009_adjusted_statement_guards.py`
- `invoicing/migrations/0010_adjusted_statement_state_uniqueness.py`
- `invoicing/models.py`
- `invoicing/test_adjusted_pdf.py`
- `invoicing/test_adjusted_statements.py`
- `invoicing/urls.py`
- `invoicing/views.py`
- `locale/fr/LC_MESSAGES/django.mo`
- `locale/fr/LC_MESSAGES/django.po`
- `templates/invoicing/adjusted/detail.html`
- `templates/invoicing/adjusted/error.html`
- `templates/invoicing/adjusted/overview.html`
- `templates/invoicing/adjusted/preview.html`
- `templates/invoicing/adjusted/summary.html`
- `templates/invoicing/detail.html`

- `invoicing/templatetags/adjusted_presentation.py`

- `invoicing/test_adjusted_presentation.py`

- `static/css/adjusted_statements.css`

## French catalogue compiler regression verification

The former ad hoc compiler skipped adjacent PO entries because it relied on blank-line separators. The PO source was preserved byte-for-byte. The generated MO was rebuilt using Django's supported `compilemessages --locale fr --verbosity 2` workflow, with GNU gettext-tools 1.0 from the Django-documented Windows distribution: https://github.com/mlocati/gettext-iconv-windows/releases/tag/v1.0-v1.19 . The portable archive SHA256 matches the GitHub-published digest: `c2f195fc4ed3df4070fb08ff88c2f724afd1eed4e28f859efae1000bb7ba1152`. All native executables and DLLs used from its `bin` directory have valid SignPath Foundation Authenticode signatures and match the verified archive. Unused unsigned .NET helpers were not executed or placed on PATH.

Tooling resides outside Git and application directories, under `C:\MicrocomIsolated\gettext-1.0-iconv-1.19`; PATH was changed only for the compilation subprocess. Neither global configuration nor production Python was changed.

Comparison against commit `42ceeff` confirms all 1,409 baseline translation keys and values remain unchanged, with 42 additional translations matching the PO source and Django runtime EN/FR lookups. Both `Leopard mascot supporting DR Congo` and `This form has expired. Please submit it again.` are restored. GNU gettext omits the source-only `POT-Creation-Date` field from compiled metadata; the PO header itself is unchanged. No translation value changed.

Focused verification passed: 15 existing tests (adjusted statement PDFs, return-note PDFs, French amounts and localized entry dates) through Django DiscoverRunner, plus three explicit catalogue tests through unittest/Django SimpleTestCase. Database setup was skipped and every attempted database connection was prohibited by a fail-fast guard. The earlier 96-test feature/regression run was not rerun for this catalogue-only correction. Private compiler logs and integrity evidence remain outside Git; the summarized evidence is in `docs/adjusted-statement-verification.json`.

## Manual acceptance presentation corrections

The adjusted PDF now follows the canonical `invoicing/pdf.py` invoice renderer: portrait A4, matching margins, Vera fonts, centered title, reference/date metadata, client and frozen branch address, grey table headers, right-aligned totals and ruled page-number footer. It imports the existing font registration, content width and lossless decimal display helper; the original invoice renderer is unchanged. As in the current invoice, frozen branding is validated without drawing a company logo/banner. Original/returned/remaining rows retain every frozen quantity and valuation, with each included BR reference and individual return value shown separately. The EAR and invoice references and explicit non-invoice/non-payment clarification remain prominent. No amount-in-words/payment-due wording was introduced.

Adjusted pages alone load `static/css/adjusted_statements.css`. Display filters group financial digits (1,000.00 USD), preserve meaningful unit-price precision, and suppress opaque request UUIDs in visible text without removing or altering stored identifiers. Existing meaningful request references remain visible. Material names and codes have separate styling. The summary highlights net material value; wide material tables scroll inside a keyboard-focusable region. Print/download remain CSRF-protected POST forms with unchanged permissions and routes; equal-size buttons align horizontally on desktop and stack with spacing below 600px. The download button reuses the existing secondary-button style. Original invoice UI/CSS, financial services, models, migrations, translations and immutable snapshots were not changed by this correction.

Final isolated verification: **17 presentation/PDF/localization tests and five financial-history/duplicate/bilingual service regressions passed**. Four real Microsoft Edge cases (EN/FR at 1440px and 390px) verified overview/preview/history, action dimensions and spacing, absence of page overflow, PDF download, POST printing and print popup, with no JavaScript errors. Twelve genuine web screenshots were captured using synthetic accounts. Final bilingual PDF examples cover one material (1 page), 18 materials (4 pages), extreme long descriptions (6 pages) and 100 BRs (5 pages), with no text outside checked page bounds. Representative canonical/statement and mobile/desktop pages were visually reviewed. Physical printer output was not tested. The unrelated original-invoice delivery test harness still omits the `tz` library required by the baseline template; its earlier failure was not repaired in this scoped change. The earlier full 96-test run was not rerun.

Private review artifacts (not staged, no production data): `C:\MicrocomIsolated\adjusted-20261111\ui-design-review` contains overview/preview/detail EN/FR desktop/mobile PNGs, genuine downloaded PDFs and `browser-verification.json`. `C:\MicrocomIsolated\adjusted-20261111\pdf-design-review` contains identical-input before/after PDFs, canonical invoice examples, page PNGs and `layout-verification.json`. The isolated loopback development server remains available at http://127.0.0.1:8011 with private default-on settings; production defaults remain off. Only the isolated development process was reloaded, not a Windows production service.

These changes are unstaged for review. The previous 24-file index was preserved; the complete feature working-tree manifest now includes three additional presentation files (27 files total). No commit, push or deployment occurred.

## Final GitHub backup verification

Final precommit checks passed: 25 PDF/presentation/localization/original-invoice delivery tests and all 41 adjusted-statement service/UI tests (including concurrent issuance and PostgreSQL uniqueness guards), 66 total. Tests used only the guarded `test_microcom_adjusted` database at loopback port 55461. Django system checks passed. Inspection-only `makemigrations invoicing --check --dry-run` reported no changes. The nine-test original invoice delivery suite contains one known harness issue: `test_toolbar_permissions_status_order_and_bilingual_labels` registers only i18n/static in an isolated Engine, while both baseline `42ceeff` and feature templates require tz. Compilation reproduced the identical missing-tz error in each; the test source is unchanged after line-ending normalization. That case is explicitly excluded from the 25-test passing group, not claimed fixed. Its other eight delivery tests passed.

The reviewed complete feature manifest contains 27 files, including the presentation CSS, template tag library and regression tests. No generated screenshots/PDFs, synthetic database records, private tooling, environment configuration, credentials or recovery files are included. All 1,409 baseline translations and 42 new translations were checked, and the production feature default remains off. This verification authorizes GitHub backup of the feature branch only; migration/deployment/activation and physical printer testing remain separate steps.
