# Phase 2 / Stage 3 / Checkpoint C

Local invoice lifecycle implementation. No production/shared/existing development database
was used. No deployment, commit, push, dependency installation, PDF rendering,
credit issuance, payment processing or automatic tax calculation was performed.

## Initial compatibility review

Reviewed the Checkpoint B documentation, financial models/migrations/tests,
company/document configuration, approval/classification/stock services and existing
permission/UI conventions before editing. No unsafe schema change was required.
All Checkpoint B financial guards remain enabled and unchanged.

Existing constraints retained:

- One invoice per request, nullable unnumbered drafts, protected evidence links.
- Unique positive OUT / unique request-material line attribution, net quantities,
  whole pre-invoice RETURN exclusions, bounded future credit schema.
- Append-only audit/attestation records and finalized parent/child immutability.
- READ COMMITTED financial writes and shared global final-reference uniqueness.
- A draft already requires a company-verification reference under Checkpoint B.
  This precondition was preserved; finalization requires a **current** attestation.
- Currency is selected when creating the draft; ordinary editing changes prices
  and the invoice note. No currency-change, void or deletion workflow was added.

## Services and transaction behavior

`invoicing/services.py` provides:

1. `create_draft`: permission/object-scope check; request row lock; approved MICROCOM
   classification confirmation and conservative OUT/RETURN validation; current
   company verification; explicit supported currency; financial lines/allocations/
   exclusions and draft audit event created atomically. Matching-currency catalogue
   prices may be copied; missing or different-currency prices remain NULL. No
   conversion, request amount change, catalogue price update or number allocation.
2. `edit_draft`: locks the invoice/request, validates the signed user-bound revision
   and exact line IDs, validates all prices before saving, recalculates line totals
   and records before/after state. NULL is unknown; zero is explicit. Negative,
   non-finite, float and excessive-precision inputs are rejected. Note length is
   bounded. A stale form cannot overwrite a newer price/note state.
3. `refresh_draft`: explicit authorized POST action; revalidates evidence and
   recomputes net quantities exclusively on the server. Existing material and OUT
   identities must match. Entered prices are retained, totals recomputed, whole
   return exclusions replaced while still draft, and before/after audit recorded.
   There are no editable source-identity or quantity fields in invoice forms.
4. `finalize_invoice`: locks the invoice/request, checks permissions and returns an
   already-finalized invoice idempotently. For a draft it verifies the signed
   revision, approval/classification, every OUT/RETURN allocation, exact net
   quantities, supported single currency, prices, current company attestation and
   Africa/Kinshasa configuration. Changed returns block finalization until explicit
   refresh/review; no number is consumed.

Finalization recalculates every rounded line total using Decimal ROUND_HALF_UP to
two places and sums the rounded totals. It freezes company, succursale, request,
material/unit/price, rounding and French amount wording snapshots. The existing
static logo is read once into an embedded base64/SHA-256/content-type snapshot
(2 MiB configured-file limit); no new logo file or PDF is generated. An explicitly
blank logo uses a frozen no-logo strategy. Missing/unsupported assets block issuance.

The finalization transaction locks the configured invoice sequence for the business
year/series, validates its external-history attestation, uses/increments its next
counter, writes the finalized invoice, refreshes the database-stamped timestamp,
and appends the final audit event. The invoice also freezes sequence configuration
and verification evidence in its audit metadata. Any validation, uniqueness,
snapshot or audit failure rolls back the counter and all financial writes.

Lock order within invoice editing/finalization is invoice, request, company,
succursale/materials where needed, sequence. Draft creation locks its request first;
it checks for an existing invoice without acquiring that invoice's row lock.
Financial writes serialize on the invoice. The existing stock return service's
request lock serializes against finalization; the finalization/return race test
confirms a waiting return becomes post-invoice evidence. Stock services are unchanged.

## Numbering and business calendar

No MAX+1, draft numbers, automatic invoice creation or unverified counter fallback.
Administrators explicitly configure and attest an INVOICE sequence for the desired
series/business year and starting value, based on external numbering history.
No new annual sequence is silently created or assumed to start at one.

The clock comes from PostgreSQL, never the browser, OS timezone or submitted date.
An aware instant is converted to Africa/Kinshasa; Django TIME_ZONE remains UTC.
The sequence selector checks the business year again after obtaining its lock.
The unchanged DB guard independently stamps current time and checks issue date/year.
A December/January mismatch aborts safely for retry; it cannot consume a number
or persist a backdated invoice.

Repeated and concurrent finalization of one invoice consumes one counter and
records one final event. Different invoices sharing a sequence receive distinct
references. A shared DB unique registry additionally prevents collisions across
types/series/years. Misconfigured overlapping formats fail rather than skip numbers.

Boundary tests simulate clock inputs to the sequence selector and validate
December31 22:59:59 UTC versus 23:00:00 UTC (January1 in Kinshasa), independent annual
starting counters, and a year change while waiting. They do not modify the real
PostgreSQL clock or pretend to issue actual future-dated documents. Existing DB
date/backdating guards are tested separately and remain enforced.

## Authorization and administrator setup

No permission is granted automatically to stock-report users, technicians,
request submitters, existing roles or groups.

- Viewing requires `invoicing.view_invoice` and request-level scope.
- Creation additionally requires `invoicing.add_invoice`.
- Editing/refresh additionally requires `invoicing.change_invoice`.
- Finalization additionally requires `invoicing.finalize_invoice`.
- Normal object scope is the designated stock-review approval's primary,
  alternate or actual actor. A later non-stock approver does not qualify.
- Active superusers have global scope. Other administrators require active staff
  status plus `invoicing.manage_all_invoices`, as well as the relevant action
  permissions. An unrelated employee does not acquire object access merely from
  global add/view/change/finalize permissions.

The Django invoice admin is read-only, including for superusers: no add, change,
delete or bulk-delete operation is available there. Authorized management uses the
audited lifecycle UI/services. Company attestations are read-only in admin.

Company settings include an explicit attestation action requiring both normal
configuration-change access and `invoicing.add_companyverification`. Sequence admin
supports configured starting values and a separate history-attestation action under
explicit sequence-change permission. Counters are read-only in admin. Used sequence
configuration/evidence is read-only; database guards still prohibit used-scope
configuration edits and counter rewinds. No financial administrative bypass exists.

## Interface and bilingual behavior

New `/invoices/` routes provide scoped listing, eligible-request review/creation,
draft pricing/note editing, explicit evidence refresh, detail/audit history,
finalization confirmation and read-only finalized display. Existing base styles and
navigation are reused; the invoice link is permission-gated. Mutations require POST
and CSRF protection. Server checks enforce authorization even for forged requests.

Signed revisions represent the same loaded line/note values displayed on the form;
they bind user, invoice and state with a two-hour expiry. Quantities and source
movement IDs are never ordinary editable form inputs. Finalized displays use frozen
financial snapshots and stored wording rather than live catalogue/company values.

177 distinct explicit invoicing/config-admin/template messages have French catalogue
entries. Existing PO/MO translations are retained. Tests exercise actual English and
French create/edit/finalize flows, errors, success messages and read-only displays,
not only catalogue compilation. Audit event codes remain stable; displayed labels
are localized and structured audit details remain available to authorized users.

## French amount wording

`invoicing/words.py` uses a dependency-free traditional French, long-scale cardinal
implementation. It covers exact nonnegative two-decimal amounts through
999999999999999999.99, including zero, hundreds, thousands, millions/milliards/
billions/billiards, currency agreement and subdivisions:

- USD: dollar(s) américain(s), cent(s) américain(s).
- CDF: franc(s) congolais, centime(s).
- EUR: euro(s), centime(s).

It rejects floats, non-finite values, negatives, excess fractional precision and
out-of-range amounts; it does not silently round wording inputs. Final totals are
already rounded by the pricing service. Wording is stored once at finalization and
never recalculated when viewing an invoice. No third-party dependency was installed.

Grammar reference: [Académie française — number spelling/agreement](https://www.dictionnaire-academie.fr/article/QDL057).
Traditional spacing/hyphens and the different agreement before mille versus million
are covered by tests. Currency references: [BCC denominations](https://www.bcc.cd/la-banque/billets-et-monnaie/billets-en-circulation),
[ECB euro denominations](https://www.ecb.europa.eu/euro/coins/html/index.fr.html),
[US Mint dollar subdivision](https://kids.usmint.gov/about-the-mint/dollar).
These references informed wording only; no exchange-rate lookup or conversion is used.

## Migration and verification

New `invoicing/0003_alter_invoice_options.py` depends on invoicing0002. It adds the
two custom Invoice permission definitions to Django model metadata. sqlmigrate is
BEGIN / no-op / COMMIT: no physical financial-table DDL or data backfill. Django's
post-migrate creates permission records but assigns them to nobody automatically.
Synthetic financial/source rows and existing grants survived application/reversal
unchanged; measured metadata migration time was 0.194875 seconds.

All previous migrations, approval/classification/stock service sources and request
reference behavior were preserved; protected SHA-256 checks are in the evidence.

Final complete suite: **300 run, 299 passed, zero failures/errors, one existing
optional sample-generation skip**, 175.564 seconds on isolated PostgreSQL **18.6**.
This includes 38 new Checkpoint C tests, four of which cover French wording, plus
the existing Phase1 / Stage1 / Stage2 / CheckpointB regressions. System checks,
dry-run migration consistency and whitespace checks passed. PostgreSQL18.4 was not
tested; this is an 18.6 result, not exact production-minor-version verification.

New coverage includes eligibility/legacy ambiguity, actual net return exclusions,
NULL/zero/invalid prices, single currency/no conversion, half-up sum-of-rounded
totals, company re-verification, immutable catalogue-independent snapshots,
stale/forged forms, scoped permissions, read-only admin, actual administrator setup
actions, annual sequence boundaries, counter/audit rollback, idempotence,
concurrent draft creation, concurrent same/different invoice finalization, and the
stock-return race. No PDF or credit-note lifecycle coverage is claimed.

The runner uses fresh isolated localhost PostgreSQL18.6 data directories, port55442,
role `microcom_checkpoint_c_test`, DB `test_microcom_checkpoint_c`, random ephemeral
credentials and staging-only settings overridden before Django setup. It never
loads the normal repository .env. Host/port/version/role/database/data-directory/
postmaster identity checks run before writes and on new connections. Existing
staging55440 and shared databases are not used.

After the successful final run, the runner dropped the disposable test database
and stopped PostgreSQL. Five explicitly identified checkpoint-created cluster
directories were removed after absolute workspace-path, reparse-point and absent
postmaster-PID checks. An exclusive localhost bind verified port55442 was unused.
Only the listed nonsensitive evidence was retained; existing services, staging
directories and earlier work were preserved.

## Exact file manifest

Modified existing files:

- `invoicing/models.py` — custom permission metadata only.
- `config/urls.py` — isolated invoice URL namespace.
- `core/admin.py` — explicit company attestation action.
- `templates/base.html` — permission-gated invoice navigation link.
- `locale/fr/LC_MESSAGES/django.po`
- `locale/fr/LC_MESSAGES/django.mo`

Created files:

- `invoicing/permissions.py`
- `invoicing/words.py`
- `invoicing/services.py`
- `invoicing/forms.py`
- `invoicing/views.py`
- `invoicing/urls.py`
- `invoicing/admin.py`
- `invoicing/migrations/0003_alter_invoice_options.py`
- `invoicing/test_words.py`
- `invoicing/test_lifecycle.py`
- `invoicing/test_c_migrations.py`
- `templates/invoicing/list.html`
- `templates/invoicing/create.html`
- `templates/invoicing/edit.html`
- `templates/invoicing/detail.html`
- `templates/invoicing/finalize.html`
- `local_artifacts/checkpoint_c_guard.json`
- `local_artifacts/test_checkpoint_c_runner.py`
- `local_artifacts/checkpoint_c_translations.py`
- `docs/PHASE2_STAGE3_CHECKPOINT_C.md`

Retained nonsensitive evidence:

- `local_artifacts/checkpoint_c_evidence_98d4b723/pg18-regression-results.json`
- `local_artifacts/checkpoint_c_evidence_98d4b723/checkpoint-c-migration-results.json`
- `local_artifacts/checkpoint_c_evidence_98d4b723/checkpoint-b-migration-results.json`
- `local_artifacts/checkpoint_c_evidence_98d4b723/stage1-migration-results.json`
- `local_artifacts/checkpoint_c_evidence_98d4b723/stage2-migration-results.json`
- `local_artifacts/checkpoint_c_evidence_98d4b723/verification-summary.json`

## Remaining limits and review gates

- No PDF, credit issuance, payments, taxes or automatic invoice generation. PDF
  font/layout/access/storage/rendering verification belongs to a separately
  authorized Checkpoint D. Frozen logo bytes/checksum are available for that work.
- Currency is fixed on draft creation; no void/delete/currency-correction workflow
  is introduced. Operators must verify the chosen currency before creating a draft.
- Explicit permission grants, verified company contents and externally checked
  annual sequence configuration are prerequisites for real operations. Missing
  new-year configuration blocks issuance safely rather than assuming numbering
  history is empty.
- Privileged database owners can still disable guards or use DDL/TRUNCATE; runtime
  role separation and production privilege review remain required. No database
  roles/privileges were changed. Uncoordinated privileged stock SQL remains outside
  the existing stock-service locking guarantees.
- Only synthetic historical fixtures were tested. Production opening balances,
  external adjustments, legacy reconciliation and production security review are
  separate outstanding work; no historical production-data claim is made.

Recommendation: **GO for Checkpoint C review**. No production deployment is
authorized. Stop here and await review before Checkpoint D.
