# Excel reporting foundations — Stage 2

The existing HTML report, workbook sheets, request filters, invoice permissions
and stock calculations remain unchanged. No new worksheets are enabled.

## Independent scopes

`ExportFilterForm` retains search, Date Needed (`date_from`, `date_to`) and
destination department filters for approved requests. Existing request-linked
movement export semantics are preserved, including the documented treatment
of unlinked movements in unfiltered exports.

`WarehouseActivityFilterForm` independently validates optional ISO dates:

* `warehouse_receipt_from`, `warehouse_receipt_to`: inclusive receipt
  `received_on` dates, not recording timestamps.
* `warehouse_movement_from`, `warehouse_movement_to`: inclusive business dates
  using `StockMovement.created_at` in Africa/Kinshasa; implemented with a
  half-open timestamp interval ending at next-day midnight.

Invalid warehouse dates return a translated HTTP 400 from Excel exports.
These parameters do not alter the existing request worksheets or HTML page.
They are foundations for future warehouse worksheets, not a new filter UI.

`reporting_scopes(user, approved_requests, validated_warehouse_filters)` accepts
an already filtered approved-request queryset. Warehouse receipts and movements
do not inherit request search, department or Date Needed filters. Inventory is
always current and includes inactive catalogue materials. No historical balance
is inferred. Scope projections omit catalogue prices and financial data; invoice
access continues exclusively through the existing bookkeeping authorization.

## Quantity interfaces

`aggregate_quantities(user, approved_items, movements)` executes two grouped
SELECTs. Approved items are restricted to APPROVED requests. Movement queries
are explicitly supplied by the caller, never implicitly restricted by request
dates. `request_material_reconciliation(user, approved_requests, movements)`
restricts both sources to the selected approved-request cohort.

Both return a dictionary keyed by `(request_id, material_id, current_unit)`.
Values expose Decimal `approved`, `received`, `issued`, `returned`, calculated
`net_issued`, and `out_records`. `out_records == 0` distinguishes missing issuance
evidence from a recorded issue. Warehouse movements with no request use a null
request key. Units are current catalogue metadata, not historical snapshots.

`quantity_evidence(approved_rows, movement_rows)` is the database-free primitive.
Inputs are grouped primitive rows. Reconciliation outcomes, invoice quantities,
current stock and return-note amounts are never physical movement inputs.

## Export budgets

The existing detail default remains `STOCK_REPORT_EXPORT_MAX_ROWS = 10000`.
Existing request lines, movements and authorized bookkeeping evidence continue
to share this budget, with count checks before loading and loaded-row rechecks.

`plan_export_budget(...)` prepares future detail source budgets: request items,
the union of movement IDs, optional inventory and receipt lines, reconciliation
output and financial rows. Receipt metadata is a distinct detail source; its
linked movement is counted only once even when referenced by multiple sheets.
Named `ExportBudget.reserve()` calls replace earlier reservations for that same
source rather than charging twice. Callers must not assign different names to
the same source. Unused future worksheets are not charged in today's export.

Derived summary rows and chart-support rows have independent cumulative limits:
`STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS` and
`STOCK_REPORT_EXPORT_MAX_CHART_ROWS`, each defaulting to 10000. Every limit must
be an integer from 1 through 1000000. Exceeding any limit returns HTTP 413 before
workbook delivery. There is no silent truncation. Static headers and formatting
are not detail rows. Shared charts backed by one support table charge that table
once. Future sheet builders must reserve their source and derived output budgets.

All export text still passes through literal-text formula-injection protection.
No writes, migrations, new prices, currency conversion or stock reconstruction
are introduced.

## Deferred decisions

Warehouse filter controls and worksheet placement are deferred to Stage 3.
Catalogue-price visibility and inventory valuation need their own approved
permission policy. Historical stock reconstruction remains unsupported because
legacy/Admin changes can lack movement evidence. A consistent cross-sheet
database snapshot and production-sized memory benchmarks remain separate work.

## Stage 3A extension: current inventory

The workbook now appends `Current Stock Inventory` / `Stock actuel` after all
existing sheets. Existing names, positions, request filters and calculations are
preserved. No receipt or issuance/reconciliation worksheet is enabled yet.

The worksheet uses the Stage 2 inventory scope, including inactive materials and
category names in one projected query. It contains code, name, category, unit,
active status, stored quantity, minimum stock level and stock status. No price,
currency or valuation is loaded by this scope or added to this sheet. The export
still applies existing financial permissions separately to Bookkeeping.

Stock-status rules, independent of active status:

* quantity below zero: Negative stock;
* quantity equal to zero: Out of stock;
* positive quantity at or below the minimum: Low stock;
* quantity above the minimum: In stock.

Current quantities are never reconstructed from movements, nor interpreted as
historical balances. Request and warehouse activity dates do not filter the
inventory. The sheet states its scope and Africa/Kinshasa generation time.

Each material is one detail row in the shared configured export budget. A count
check precedes a bounded load and a loaded-row recheck; financial evidence uses
the remaining budget after inventory. Inventory does not consume the summary
budget. Oversized exports return HTTP 413 without delivering a partial workbook.
Narrowing request filters cannot reduce the warehouse-wide inventory count; a
catalogue that alone exceeds the configured limit requires a separately approved
limit/export strategy. No silent truncation or new inventory filtering is added.

## Stage 3B extension: material entries

`Material Entries` / `Entrées de matériel` is appended after Current Stock
Inventory. Existing worksheet names and positions remain intact. Its French
title uses an Excel-specific gettext context, preserving the Material Entries
navigation translation elsewhere in the application.

Each detail row is an actual MaterialReceiptLine, ordered by receipt business
date and line ID. Columns: receipt reference, business receipt date, recording
timestamp, material code, material name, category, unit, quantity received,
recorded stock after receipt, recorded transaction type, movement database ID,
movement type, movement quantity, receipt creator, supplier, delivery reference,
notes, material-evidence source and linked-movement evidence status.

Only `warehouse_receipt_from` and `warehouse_receipt_to` filter these rows,
inclusively against `MaterialReceipt.received_on`. Request search, department,
Date Needed and warehouse movement dates do not affect receipt selection.
The sheet explicitly shows these date bounds and scope. Recording timestamps
are converted to Africa/Kinshasa; receipt dates remain actual Excel date values.

Version-1 descriptive material snapshots are preferred when complete and typed.
Missing or malformed snapshots use clearly labelled current catalogue details,
including inactive materials. Only descriptive JSON keys are projected: the
price/currency fields within receipt snapshots are neither loaded nor exported.
Missing transaction type, supplier or delivery reference is explicit, never
inferred from current stock, receipt references or hashes.

Each recorded receipt line requires a protected one-to-one StockMovement link.
The worksheet shows its database ID (there is no separate movement reference
field), type and quantity. Inconsistent type/material/quantity links are flagged,
not repaired or excluded. IN movements without receipt lines are not invented
into receipt records; they remain movement evidence in their existing scope.

Receipt lines consume the shared detail budget after request lines, existing
movement rows and inventory, before authorized bookkeeping evidence. Movement
IDs referenced in receipt rows are not charged again as movement records.
Count-before-load and loaded-row checks reject oversized output with HTTP 413,
without truncation. Supplier, notes and all other text still pass through the
whole-workbook literal-text protection. Exports issue SELECTs only.

Issuance/returns and dashboard integrations remain deferred to Stages 3C/3D.

## Stage 3C extension: issuance and returns

`Issuance and Returns` / `Sorties et retours` is appended after Material Entries.
It reconciles the selected approved-request cohort by request ID, material ID
and current catalogue unit. Existing sheets and warehouse date meanings do not
change. Request search, destination department and Date Needed choose requests;
all recorded OUT/RETURN dates for those requests are included. Warehouse dates
never truncate this reconciliation. Unlinked movements and outside requests are
excluded rather than mixed with request evidence.

Columns: request reference, status, Date Needed, approval timestamp, requesting
department, destination department, classification, succursale, material code,
material name, current unit, approved quantity, actual OUT quantity, actual
RETURN quantity, net issued quantity, issuance-evidence status, OUT movement
IDs, RETURN movement IDs, verified return references, reconciliation status,
and material database ID. Succursales are classifications, not warehouses.

The Stage 2 Decimal quantity-evidence helper consumes already loaded request
lines and physical movements. Each movement ID is processed once. Quantities
are not inferred from stock, invoices, return-note amounts, outcome metadata,
approval flags or reference strings. Repeated request material lines are summed
at request/material level and flagged as having no reliable per-line movement
allocation. Movement-only materials have unknown approved quantity, not an
invented authorization of zero.

Missing OUT rows are distinct from a recorded zero OUT total. Partial and full
issuance/returns remain separate from authorization. Non-positive quantities,
returns exceeding issues, issues exceeding approval, repeated lines and invalid
document links are flagged without repairs. Signed legacy/correction quantities
are retained as recorded and flagged; there is no inferred reversal, replacement
or latest-record policy. Net issued is always recorded OUT minus RETURN.

One projected batch query loads operational ReturnReceiptLine links. A return
reference is shown only when the linked receipt request and recorded line
quantity match the physical RETURN. The reference is paired with its movement
ID. No financial return-note or credit data is queried. Missing references are
explicit, and invalid links do not suppress the actual physical quantity.

Each reconciliation output row consumes the shared detail budget before
bookkeeping. Already loaded movement IDs are not charged again. References
exceeding Excel's 32767-character cell limit cause HTTP 413, never truncation.
The new sheet retains whole-workbook literal-text protection and contains no
prices, currencies or valuation. Metadata and current units are not frozen
historical catalogue snapshots. No business workflow or schema changes occur.

Dashboard, summary and graph changes remain deferred to Stage 3D.

## Stage 3D: operational dashboard, summaries and graphs

Existing worksheet names and positions are unchanged. The original approved
request KPI cards and demand tables remain. Their scope labels now explicitly
refer to selected requests and destination departments, rather than implying
physical delivery. Additional dashboard sections show independent scopes:

| Scope | Metric | Definition |
| --- | --- | --- |
| Request cohort | Approved requests | Unique selected approved request IDs |
| Request cohort | Approved material lines | Selected request-line count |
| Request cohort | Requests with recorded issuance | At least one OUT record, including flagged legacy zero records |
| Request cohort | Requests missing OUT evidence | At least one approved material has no OUT record |
| Request cohort | Requests with recorded returns | At least one RETURN record |
| Request cohort | Reconciliation exception rows | Unique request/material/unit rows with one or more review flags |
| Inventory | Total catalogue materials | All current materials, including inactive ones |
| Inventory | Active/inactive materials | Current catalogue status, counted separately |
| Inventory | Strictly below minimum | Stored quantity strictly less than minimum; includes zero/negative stock when below minimum |
| Inventory | Zero stock | Stored quantity equal to zero; can overlap below-minimum count |
| Receipts | Receipt transactions | Distinct receipts with included receipt lines |
| Receipts | Received material lines | Included actual receipt-line count |
| Physical movements | OUT/RETURN counts | Distinct recorded movement IDs by type in the independently selected movement period |

Request filters still mean search, destination department and Date Needed.
Reconciliation uses full linked movement history. Current inventory is never
date-filtered. Receipts use business received_on dates, not creation dates.
Warehouse physical activity uses created_at business dates in Africa/Kinshasa,
including request-linked, outside-cohort and unlinked OUT/RETURN evidence.
Dashboard scope notes and date bounds make these differences explicit. No IN
movement is counted as an OUT/RETURN or invented into a receipt transaction.

The warehouse loader projects operational fields only. Its count check and
bounded load reserve only movement IDs absent from the existing movement detail
source; reused IDs are not charged twice. Reconciliation and receipt evidence
are reused from their already-budgeted sources. Additional derived rows consume
the cumulative summary/chart budgets before workbook delivery. No truncation or
implicit limit increase is introduced. Decimal evidence too large for Excel's
15-digit precision is written as text using the existing exact-number helper.

### Graphs

The four existing demand/time chart positions remain. When selected materials
have mixed or missing units, the first chart explicitly uses approved-request
counts per material. Its new hidden support table is AI:AJ. Single-known-unit
selections retain the approved-quantity chart. Original per-material quantity
tables remain available; there is no grand total across units.

Four additional count charts use separate hidden support tables:

* AN:AO — current stock-status counts, from the entire inventory snapshot;
* AR:AT — receipt transactions and receipt lines by received_on month;
* AV:AX — physical OUT and RETURN records by Kinshasa movement month;
* AZ:BA — reconciliation exceptions by category.

Empty sources do not produce misleading empty charts. Exception categories can
overlap; a row with multiple flags counts once in the dashboard total and once
per applicable category in the chart. Flags include missing OUT, unapproved
materials, repeated lines, non-positive quantities, excess returns, over-issuance,
unverified return documents and partial issuance. Charts use counts rather than
combining quantities from different units. Print regions extend through row 86.

### Summaries and financial compatibility

Legacy operational summary measures retain their definitions. Explicitly named
new rows add approved demand, returned quantity and net issued for the request
cohort; current central stock for the entire catalogue; receipt-date quantities;
and warehouse movement-date quantities/counts. Units and category codes remain
separate. Missing units use material-code-specific labels rather than forming a
single unknown-unit quantity bucket. Monthly approved demand uses approval time,
receipts use business date, and physical movements use Kinshasa creation time.
Succursales remain transaction destinations/classifications, never warehouses.

To satisfy the Stage 3D financial boundary, authorized financial summary totals
and coverage measures move from the three operational summary sheets into a
panel at Bookkeeping N:R. Financial authorization and request-assignment scope
are unchanged; frozen invoice values and currency-specific buckets are unchanged.
Existing invoice detail columns A:L, header row 2 and first detail row 3 remain.
Consumers of old financial summary locations must now read this panel. The new
panel is itself summary-budgeted and included in Bookkeeping's print area. No
price or financial total is written into any operational summary or chart cache.

Receipt analytics reuse the receipt detail snapshot/fallback helper, so legacy
units and category names cannot be interpreted differently between the two.
Inventory and movement category labels are current catalogue metadata; receipt
snapshots remain historical evidence where recorded. No historical stock is
reconstructed and no financial valuation or currency conversion is introduced.

### Manual review and remaining limits

Before release, open representative EN/FR workbooks in the deployed Excel
version and review long chart titles, localized month/category labels, legends,
print previews and the Bookkeeping side panel. Verify independent receipt and
movement date filters using the existing query parameters; no new HTML controls
or report redesign is introduced. The exporter has bounded row budgets but no
cross-sheet repeatable-read snapshot: concurrent transactions can appear between
separate SELECTs. Production-scale memory/time profiling remains separate work.
