# Excel reporting, step 1

The original Material Report, Dashboard and Graphs remain first, with existing
charts and request-based filters. Five fields are appended after column O:
classification, succursale, existing BC, existing BS and missing-data notes.
No prices, invoice amounts or financial snapshots are queried or exported.

CLIENT branch: not applicable. Unclassified history: classification unavailable.
MICROCOM without branch: missing succursale (synthetic legacy coverage; current
DB classification constraints prevent new occurrences). Missing BC/BS: not
issued. Export only reads existing document records; it never issues documents.

Stock Movements is fourth: timestamp, material, code/category, movement type,
quantity/unit, linked request, actor, existing BC/BS. No incompatible-unit totals.
Movements follow the SAME approved-request selection, including Date Needed
filters. Unlinked movements are included only when q/date/department filters
are all absent. This is deliberately NOT a complete independent ledger of
movements attached to non-approved requests. The scope appears in the sheet and
report page. Dates and month bucketing consistently use Africa/Kinshasa; Date
Needed is a date, not an instant, and is not shifted.

Export filters validate ISO dates, date order, department existence and a
200-character search limit. Invalid input returns 400 before workbook creation.
STOCK_REPORT_EXPORT_MAX_ROWS defaults to 10000 combined detail + movement rows.
Set this Django setting explicitly to adjust it (integer 1..1000000). The
export checks counts before loading, bounds request/movement retrieval, and
rechecks loaded row counts. Exceeding the limit returns bilingual 413 guidance
with a link back to filters. No application environment values are changed.

All text cells in all sheets, including hidden chart data and echoed filter
metadata, are saved as literal strings rather than formulas. Numeric cells stay
numeric. Existing charts reference literal source ranges, not worksheet formulas.
Related branches/documents are loaded in batches. Movements use select_related
and reuse prefetched document references, avoiding per-row lookups. Workbooks
remain in memory; the limit is not a benchmark or a streaming implementation.
Counts and data reads are not a globally repeatable-read snapshot: concurrent
edits can change a report while it is being collected; loaded-size checks fail
closed for growth beyond the limit.

Stock permissions are unchanged: superuser or can_manage_stock, all departments
within this existing central-stock role. Future bookkeeping reports must ALSO
apply existing invoice view permissions and invoice assignment scopes, frozen
prices, quantities and currency-specific totals. Succursales are destinations,
not independent warehouses. No stock, approval or invoice services are called.

Offline runner: local_artifacts/test_stock_export_offline.py. Database-backed
regressions: requests_app.test_stock_report_analytics, requests_app.tests material
export tests, requests_app.test_stock_export_postgresql. Run only on the already
verified disposable local PostgreSQL environment with standalone settings,
--keepdb and --parallel=1; never Supabase. No schema migration is needed.

Bon de retour remains disabled. Stock User Portal remains postponed.

Validation completed locally: 20 offline tests passed with zero connection
attempts. The isolated PostgreSQL selection ran 36 tests: 35 passed, zero
failures/errors, one existing opt-in sample-generation skip. All eight new
integration tests passed. An older legacy-zero-history test was updated to
explicitly assert and follow the existing Phase B BS redirect before checking
its read-only page/Excel behavior. No application change was needed for it.
Database-free system checks, migration-state checks, template compilation and
Python syntax checks passed. No migrations were applied and no Supabase or
production connections were used. Only synthetic disposable test fixtures were
written by tests. Excel export itself was verified to execute SELECTs only.
