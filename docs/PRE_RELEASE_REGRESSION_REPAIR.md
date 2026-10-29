# October 29 regression repair

Scope: repair test setup and obsolete assertions, without changing runtime
business behavior. All database execution uses the verified disposable local
PostgreSQL 17 cluster, never Supabase or production. No migration is added.

## Root causes and repairs

- Invoice PDF tests depended on an absent private storage directory and an
  external evidence setting. Each test now creates a unique synthetic directory
  under the isolated storage parent and retains its files for inspection.
  Production storage validation is unchanged.
- PDF assertions still expected the removed issuer heading or physical address.
  They now verify the approved client-only layout while asserting that issuer
  and address snapshot evidence remains intact. Cache checks accept and require
  Django's stronger private/no-store/no-cache response directives.
- A source-reference test tried to update a persisted immutable reference. It
  now asserts database rejection, verifies the stored value, and supplies an
  altered in-memory relation to catch live-reference rendering fallback.
- Mocked return-note HTTP tests used synthetic users with real database-backed
  context processors. Their template configuration now excludes those unrelated
  processors only within the unit tests. Real permissions and context processors
  remain covered by integration tests. The feature gate remains disabled.
- The orphan diagnostic unit test now owns its synthetic evidence directory
  rather than depending on an externally supplied setting.
- French expectations contained mojibake while runtime catalogues were correct.
  Encoding-only test literals were repaired; catalogues were not changed.
- The department printing fixture lacked material-type/deduction eligibility.
  It now uses the authorized BC/BS POST and redirect workflow, retaining all
  department-content assertions and exercising eligible bulk printing.
- A historical migration test compared old records with fields added by later
  approved migrations. It now compares every original column and separately
  requires NULL legacy allocation metadata. Historical references are included
  in the original-column comparison.
- Repeated --keepdb runs retained references in the unmanaged global registry.
  Direct SQL fixtures now use unique synthetic references. Concurrency tests
  still deliberately race for the same reference within each run and require
  exactly one winner. No registry constraint or guard was bypassed.

## Repository preparation

Review the complete application/migration/template/test/documentation change set
together. The generated candidate manifest is a review aid, not a staging list.
Do not bulk-stage local_artifacts: it contains logs, generated documents, old
evidence, local settings and cluster helpers. Keep environment files, credentials,
media, virtual environments, collected static files and caches excluded. No
files have been staged or deleted by this repair.

requirements.txt remains unchanged. Its UTF-16 encoding is readable by pip but
produces a binary Git diff. A separately reviewed conversion to UTF-8 should
preserve the exact 13 package/version pairs and pass pip check before committing.

## Validation

Baseline: 713 tests, 671 passed, nine failures, 32 distinct errored tests
(52 error reports including subtests), one existing optional skip.

Affected rerun: 111 passed, zero failures/errors. All seven offline runners
passed: 215 test executions with overlapping coverage. Full-suite results are
recorded in the local regression_repair_full logs and final result evidence.

Full rerun: 713 tests in 796.273 seconds, 712 passed, zero failures/errors,
one existing opt-in stock-report sample-generation skip. No failing test was
disabled or skipped to obtain this result. The isolated database was retained.

No runtime defect requiring a business-rule change was established by these
failure groups. A green synthetic regression run does not replace manual browser,
deployment configuration, production backup or operational readiness review.
