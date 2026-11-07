# Material Reports performance and explicit selections

HTML reports display 25 approved requests per page, with a total count and stable
finalized/submitted/primary-key ordering. Related material lines and movement
histories are loaded only for the visible page. Unused HTML approval prefetches
are removed. Excel and CSV retain the full filtered scope and existing financial
and row-limit rules; no migration or index change is introduced.

Return-note navigation uses one fresh actor/permission snapshot plus bounded
request-scope and finalized-invoice queries for the visible page. The original
return-note endpoint authorization remains authoritative and unchanged.

## Selection behavior

Individual selections persist across pagination in the same filter scope using
sessionStorage (current browser tab), bound to a non-secret HMAC context for the
current authenticated session. The context also includes a tab browsing-context name to reject cloned storage
from a newly opened tab; an existing window name is preserved. Selected request IDs, normalized filter scope and opaque context identifiers are
stored, never full request-detail payloads or authentication tokens. Search/date/department/status scope changes clear all
IDs, including Back/Forward transitions to another filter scope. Page changes do
not clear selection. Select All applies only to visible rows. Clear Selection
clears all pages. AJAX failures prevent bulk submission until valid results load.
Without JavaScript, selection is limited to the current page, with a visible notice.
If sessionStorage is unavailable, in-memory selection survives AJAX pagination
only, not a full reload. Normal browser storage/session lifecycle still applies.

The existing print endpoint accepts explicit IDs, deduplicates and validates them,
rechecks stock-manager access and approved/stock-deducted/material eligibility,
and rejects the whole selection if any requested ID is ineligible or missing.
Signed report filter proofs additionally revalidate the current filter scope;
existing explicit-ID callers without that new proof retain the existing global
stock-manager eligibility scope. Existing per-request two-copy item limits remain.
There is no new adjustment, invoice issuance, or stock mutation path.

## Local benchmark (not production measurements)

Verified isolated local PostgreSQL; all synthetic inserts rolled back. Two warm
samples per variant, median instrumented view+render time. The pre-change view
and original template were reconstructed in memory, not saved over working files.
Return-note navigation was enabled. Each request had three material lines, three
approval records and six stock movements; the stock user had no financial access.

| Requests | Before queries | After queries | Before ms | After ms | Before HTML bytes | After HTML bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20 | 71 | 12 | 310.08 | 168.66 | 177757 | 174599 |
| 100 | 311 | 12 | 1893.25 | 281.19 | 819131 | 214341 |
| 500 | 1511 | 12 | 7717.97 | 315.32 | 4028840 | 214541 |

These measurements exclude browser layout, network transfer and production
contention. Total-count DISTINCT queries, sorting and very deep OFFSET pages can
still grow with database size. A single request with unusually large material or
movement history remains expensive. Index/Exists/keyset/lazy-history changes need
separate evidence and approval. Export workload is unchanged.

## Windows Server rollout and rollback considerations

Do not deploy before review. Record the current release and existing uncommitted
work; preserve a complete application/static/translation rollback artifact. This
change needs no migration, database backup restoration, global DEBUG, or database
configuration changes. Follow the existing Windows deployment procedure for a
coherent application/static/compiled-translation release and any required worker
reload; do not assume hot code replacement updates every worker. Browser caches
must receive the new selection JavaScript. Verify the new module, helper and
pagination partial are packaged.

Acceptance: compare TTFB/response size for the same account/filter; verify page
totals, three-page selection, Select All, clear/filter/Back/Forward behavior, stale
ID rejection, read-only versus issue links, two-copy fallback, EN/FR, and complete
filtered Excel output. Keep existing endpoint permissions and financial guards.
If rollback is needed, restore the matching prior application/static/translations
as a unit using the established procedure. No data rollback is required. Reload
open report tabs to discard incompatible selection UI; clear this report's tab
selection key if necessary, without clearing unrelated browser storage.
