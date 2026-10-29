# Bookkeeping and stock statistics

Local implementation. No migration required. No Supabase/production connection,
deployment, permission grant or financial model/lifecycle change is included.

The original Material Report, Dashboard, Graphs and Stock Movements stay first.
The original charts and Date Needed/request filters stay intact. Every new sheet
uses the same filtered request selection, not a new financial date-range filter.

Financial access requires existing invoicing.view_invoice permission AND the
existing invoicing.permissions.request_scope. Staff manage_all_invoices and
superuser behavior are unchanged. Only authorized finalized invoices are loaded.
Without financial access (including empty assignment scope), Bookkeeping and ALL
financial measures/headers are absent; filenames and chart data are stock-only.
Partial financial access means totals cover only the authorized subset, explicitly
labelled as such, even though stock measures still cover the stock-report scope.

Bookkeeping is fifth when authorized: official invoice reference/date, frozen
request/branch/material/unit, current category (labelled current), frozen net
quantity/price/currency, stored line total and evidence status. No current material
prices are read as financial history. Explicit zero stays numeric zero; missing
values are Unknown. Requests without a finalized valuation get a status row,
never editable draft values. This coverage count describes absence of finalized
valuation; it does not mean every CLIENT request requires an invoice.

Succursale Summary, Material Group Summary and Monthly Statistics follow. For
stock-only users these are sheets 5–7; authorized users receive eight sheets.
They use long-form Grouping/Measure/Unit-or-Currency/Value rows to avoid repeated
counts and mixed-unit/currency totals. Branch groups use frozen identifiers when
authorized finalized evidence exists, otherwise current assignment identifiers;
missing frozen identifiers are kept distinct by invoice. Category codes prevent
duplicate category names from merging. Missing category history cannot be
reconstructed: categories are explicitly current.

Issued quantities come from recorded OUT movements, not requested quantities.
Material counts are distinct. Central stock balances are counted once per
material, by unit, for materials represented in the selected data; this is not a
complete inventory valuation or a succursale warehouse balance. Unknown units
stay separate per material code. Currency conversion is never performed.
Stock movement/category labels and units use current material metadata because
movements do not store historical unit/category snapshots. They must not be
mistaken for the frozen units/descriptions in the financial worksheet.

Branch/month financial totals SUM the stored invoice.total once per invoice;
category financial totals SUM stored line_total. They never multiply/reprice
finalized lines. Totals are labelled known authorized values, with missing-value
and no-finalized-valuation counts separately reported. Returns before invoice
finalization are already reflected in frozen net quantities. Later returns and
credits are not netted from original invoice amounts. This report is not a refund,
credit, payment, sales or purchasing ledger.

All instant-based month buckets use Africa/Kinshasa: request approval time,
movement time, document allocation time and invoice finalization time. The
original official invoice.issue_date remains unchanged in Bookkeeping, even
if a historical invoice used a different business timezone. Missing dates remain
explicit. Existing BC/BS records are counted, never issued by exports.

The existing 10000 combined source-row cap now includes bookkeeping detail and
missing-valuation rows, in addition to material detail and movements. Derived
summary rows reuse this bounded data. Large Decimal values exceeding Excel's
15-significant-digit precision are exported as exact text. All text cells, in
all sheets, are literal text, including formula-like financial descriptions.

Financial data is batched, with no per-line branch/price lookups. Export reads are
SELECT-only, but there is no globally repeatable-read report snapshot. Concurrent
edits can yield an inconsistent report across queries; use a quiet period for
reconciliations. Memory/visual spreadsheet review remains necessary at scale.

Validation: 35 offline checks passed with zero connection attempts. In the existing
verified disposable PostgreSQL cluster, 79 tests ran: 78 passed, zero failures or
errors, one existing opt-in sample-generation skip. This includes nine new
bookkeeping tests, prior Excel/analytics tests and invoice lifecycle/list tests.
The initial run exposed missing STATICFILES_DIRS in isolated settings, preventing
invoice fixture logo discovery; only the standalone static paths were corrected.
No invoice guard was changed. Test fixtures alone create synthetic records;
export itself was verified to perform reads only and preserve evidence/stock.

Bon de retour stays disabled; Stock User Portal stays postponed. Ready for
controlled development validation after review, not an automatic deployment.

Coverage clarification: CLIENT requests show "Internal invoice not applicable";
they remain included in material consumption and stock activity. Only MICROCOM
requests without a finalized invoice contribute to the neutral "invoices not
issued or not finalized (on demand)" count. This is not an error or missing-value
warning: invoices are issued on demand. Unclassified historical requests show
"Classification unavailable" and retain stock classification warnings, without
being counted as missing invoice valuations. Missing frozen values are counted
only for actual finalized invoice evidence. No overall financial-coverage ratio
is calculated. Existing finalized evidence remains visible even if inconsistent
historical classification is encountered; export never rewrites it.

CLIENT coverage correction validation: 37 offline checks passed with zero
database/network attempts; 27 isolated PostgreSQL reporting tests ran, with 26
passed and one existing optional skip. Django system checks reported no issues.
The PostgreSQL selection covers bookkeeping, secure export and stock analytics,
including SELECT-only export preservation. No migration was needed or applied.
