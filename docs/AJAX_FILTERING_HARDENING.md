# Shared AJAX filtering audit

Scope: My Requests, Pending Approvals, Approval History, Administration Reports,
Material Reports and Invoices. The existing full-HTML GET views remain the
fallback when JavaScript is disabled. No new AJAX-only authorization path exists.

## Preserved page differences

- My Requests starts with the authenticated submitter's queryset; dates use
  creation time in Africa/Kinshasa. History starts with existing actor/legacy
  assignment rules and selects the latest visible action before filtering.
  Overall request status and the user's action remain separate.
- Pending Approvals retains primary/alternate/current-step constraints and
  Date Needed filtering. Material Reports retains stock permissions, approved
  requests/material rows and Date Needed filtering.
- Administration Reports retains its dedicated access flag, configured request
  type and creation-date filters. Invoices retain explicit permissions and
  request scope; dates mean official invoice issue dates, never request dates.
- Pagination is enhanced where already present; no pagination was invented for
  Pending Approvals or Material Reports. Filtering does not allocate references.

## Confirmed repairs

- Search is debounced at 350ms and uses replaceState rather than adding a history
  entry for every search. Discrete filters, Clear and pagination use pushState.
  Duplicate URLs do not add another entry.
- Every new intent invalidates old requests. Back/Forward also cancels pending
  debounce timers. Stale responses, including redirects, cannot replace results.
- Failed HTTP/network/non-HTML/missing-container responses hide stale results,
  display a translated status and let the explicit Filter action use normal GET.
- Controls stay mounted so typing focus survives. Keyboard pagination returns
  focus to the refreshed table. Server validation messages and ARIA attributes
  refresh without replacing controls. Loading/status text is translated.
- Bulk print actions are disabled while results are stale or failed; existing
  disabled state is preserved. No permission is granted by a successful refresh.
- Material Select All remains delegated to document events and handles replaced
  checkboxes. Changing results clears old selections. Export links and the bulk
  return URL synchronize with visible filters and successful AJAX updates.
- Invoice hidden POST filters synchronize on editing, AJAX updates and submit,
  excluding pagination. Server date-range, limit and permission checks remain
  authoritative. Financial calculations and print services are unchanged.
- Pending Approvals had a department template expression split across lines;
  Django rendered it literally. It is now a single expression with explicit
  accessible label/control associations.
- The user separately approved fail-closed filter validation for Pending
  Approvals and Material Reports. Malformed dates/IDs and reversed date ranges
  produce visible bilingual messages and no results. Query authorization and
  existing date meanings are unchanged. No schema migration is required.

## Validation boundaries

Node tests use the built-in test runner and a fake DOM, without dependencies.
They also execute the existing inline material-selection/export and invoice-print
scripts. They do not prove all native-browser behavior.

Actual headless Edge checks use isolated profiles, synthetic local files and a
blocked HTTP proxy. Eight EN/FR desktop/mobile renders showed no horizontal
overflow at 390/1365 CSS pixels. Two actual-browser synthetic AJAX checks showed
EN/FR errors replacing old results with one fetch and no page reload. These are
not authenticated end-to-end browser tests of all six real pages.

Manual checks still needed: native popup/keyboard behavior on target browsers,
authenticated session expiry, real rapid network changes, browser Back/Forward,
material selection after filtering and real authorized print/export navigation.
Do not equate the earlier user-reported browser checks with automated evidence.

No dependencies installed; no commit, push, deployment, new schema migration or external
database access. Bon de retour remains disabled. Local evidence and browser
profiles are not release source files.

## Recorded results

- Focused Django selection: 80 passed. Final date/list/permission selection:
  13 passed, including two cases added after the broad run started.
- Node contract tests: 21 passed. Invoice/offline presentation suite: 82 passed,
  zero database/network attempts. PO has no duplicate msgids; the MO loads and
  the new French messages have correct accents.
- Full isolated run: 730 tests, 723 passed, six failures, zero errors, one existing
  optional sample-generation skip. Four presentation assertions were then repaired
  and passed in the 82-test offline rerun: legitimate scripts are allowed while
  a unique injected script remains escaped; totals are checked independently of
  template line wrapping. No assertion about values or permissions was removed.
- Two pre-existing financial fixture assertions remain unmodified:
  test_failures_after_counter_update_roll_back_every_financial_write expects the
  entire unmanaged reference registry to be empty; and
  test_final_credit_immutability_and_global_reference_uniqueness expects that
  registry to contain only the current test's two references. The retained test
  database contained earlier synthetic references. Do not erase evidence, weaken
  constraints or claim a clean full run. A separate test-fixture repair should
  compare the pre-existing baseline or scope assertions to the current operation.
- Post-run system checks: zero issues; no model/migration drift or pending
  migrations. Existing migration regression tests ran only in the isolated test
  database. No new application migration was generated.

Date-filter repair passes. Overall release sign-off remains blocked by the two
financial test-harness assertions and authenticated cross-browser manual checks.
