# Phase B: BC and BS

Local implementation; migration 0019 is not applied. No database was contacted
for implementation/validation. Bon de retour stays disabled; Stock User Portal
remains postponed. Deployment is blocked pending isolated PostgreSQL validation.

BC is an internal material order, BS an authorized material issue document.
Both require an approved material request with stock_deducted=true and material
rows. Neither issuance nor printing performs inventory or financial operations.
Existing requester/assigned-approver/stock-manager/superuser visibility is reused.

The shared existing HTML/A4 print layout renders both types with only title and
official reference differing. Request reference and all original information
remain. Existing administration printing is unchanged. Browser Print / Save as
PDF, one/two copies, and the six-item two-copy fallback remain available.

Print links open GET confirmation on first use. CSRF-protected POST allocates
then redirects to the permanent GET print route. GET never allocates. Repeated
POST, response loss and reprints reuse the same request/kind record. Copy links
retain document kind through the route. No editable document draft is introduced.

Numbering uses independent type/year counters, initialized by an atomic upsert.
A single PostgreSQL clock instant determines Africa/Kinshasa year and timestamp.
Request lock precedes sequence allocation. Unique constraints prevent duplicate
request/kind and kind/year/counter allocations. Failure rolls back the counter.
Minimum width is four digits, with expansion above 9999 and safe bigint exhaustion.
Records/references are immutable and counters cannot decrease or be deleted.
Migration reversal fails closed after any numbering evidence exists.

Historical request references and previously printed files are not changed or
backfilled. First on-demand issuance allocates a new BC/BS reference in its
current business year, not the request's approval year. Existing bulk printing
remains a legacy request-reference report: it does not allocate official BC/BS
references. Eligibility now requires approved, stock-deducted material requests.

Only references/allocation metadata are frozen. As in the existing layout,
material labels, current available stock, people/departments and editable issue
remarks remain live; byte-identical historical reprints are not promised. No
invoice artifact/snapshot behavior is changed and no new PDF storage is added.

Offline validation:

    .\venv\Scripts\python.exe local_artifacts/test_material_documents_offline.py

Deferred isolated PostgreSQL module: requests_app.test_material_documents_postgresql.
It covers concurrency, rollover, replay, rollback, access, stock neutrality,
immutability, expansion and exhaustion. It has NOT been executed. Also rehearse
0019 on representative legacy approved requests, test CSRF/browser printing,
unused reversal and used-reversal refusal, and rerun existing printing and stock
regressions. Existing copy-limit and issue-note print fixtures now confirm stock
deduction and issue BS through POST before checking the rendered print view.

Review and authorize an isolated rehearsal before applying 0019 anywhere. Do not
deploy source ahead of its schema. No migrations, Supabase tests, commits or
deployment are authorized by this document.

Completed database-free validation: 20 focused BC/BS tests and 33 existing Phase A
offline tests passed, with zero database/network connection attempts. Six
templates compiled. Synthetic Django system checks and migration-state checks
passed (no changes detected). Eight new PostgreSQL integration tests and the
updated existing database-backed print tests remain unexecuted.
