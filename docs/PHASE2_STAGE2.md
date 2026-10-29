# Phase 2 Stage 2: first stock review and classification

## Administrator configuration

In the existing workflow admin, mark the first step of each applicable material
workflow as **Stock classification review**. Assign an active explicit primary
user and, optionally, an active alternate using the existing assignment fields.
This assignment serves requests across departments without department-local role
lookup for the stock reviewer. Existing role resolution on other steps is unchanged.

Only one step may be designated, and it must have the lowest configured step
order. Invalid configurations are rejected in both workflow admin interfaces and
before generating approval rows. No steps are added, removed or reordered.
There is no minimum of two steps. A sole stock reviewer is the final approver.
Unmarked workflows retain their existing behavior; administrators must explicitly
enable the designation on applicable workflows.

## Approval and correction

At submission, each generated approval snapshots whether it requires stock
classification. Changing a workflow later does not retrofit pending approvals.
All existing approval snapshots default to false; historical requests receive
NULL classification, succursale, classification actor and classification date.

The designated primary or alternate reviewer must explicitly choose CLIENT or
MICROCOM when approving. MICROCOM requires a currently active succursale; CLIENT
must have no succursale. The service rechecks activity under a row lock. Rejection
and return for correction require no classification and ignore these extra inputs.
Later reviewers cannot change classification or bypass a pending stock review.
The classification fields are read-only in request admin.

Classification, actor/date, a STOCK_CLASSIFIED audit event, approval transition
and any final deduction share the existing atomic approval transaction. Failure
rolls these changes back together. For multiple steps, first approval does not
deduct stock. For one step, approval classifies and deducts exactly once.
Material prices remain optional and are never used for classification/routing.

resubmit_request() is unchanged: it deletes and rebuilds approval rows, as before.
Previous classification values remain visible for reference, with a pending
confirmation label. The rebuilt stock-review step requires a fresh posted choice,
even when confirming the same values. It updates the actor/date and appends a
new audit event; choosing CLIENT clears the previous succursale. There are no
approval cycles or retained historical approval rows. Existing audit logs remain.
As before, resubmission uses the workflow configuration applicable at that time.

## Migrations and release risks

- workflows/0003_approvalworkflowstep_is_stock_review adds an opt-in flag defaulting
  to false. It does not assign any user or designate any existing step.
- requests_app/0017_request_classification_request_classified_at_and_more adds
  nullable classification metadata, a protected succursale relationship and an
  approval snapshot flag. A CHECK permits legacy NULL/NULL, CLIENT/NULL or
  MICROCOM/non-NULL pairs. Actor deletion follows the existing SET_NULL convention.
- No data migration infers historical classifications or assigns succursales.
- Migration 0017 depends on inventory Stage 1 and workflow 0003. Requests_app
  migrations 0015/0016 and stock_services.py are unchanged.

Schema locks, foreign-key indexes and CHECK validation require a separate
production migration/backup review. Reversal would discard new classification
metadata and policy flags; do not reverse after use without an explicit recovery
plan. Direct SQL, privileged ORM scripts and existing broad administrative edits
to approval status are outside the normal approval endpoint's safeguards.

This stage adds no branch balances, issuance action, invoice or PDF generation.
Tests use synthetic data and a disposable verified PostgreSQL 18.6 cluster;
this remains same-major-version evidence, not exact PostgreSQL 18.4 verification.

## Files introduced or changed in this stage

- workflows/models.py
- workflows/admin.py
- workflows/migrations/0003_approvalworkflowstep_is_stock_review.py
- requests_app/models.py
- requests_app/services.py (resubmit_request and workflow selection unchanged)
- requests_app/classification.py
- requests_app/approval_forms.py
- requests_app/views.py
- requests_app/admin.py
- requests_app/migrations/0017_request_classification_request_classified_at_and_more.py
- requests_app/test_stock_classification.py
- requests_app/test_stock_classification_migrations.py
- inventory/test_stage1_migrations.py (pin its pre-Stage-1 requests migration state)
- templates/requests_app/approval_detail.html
- templates/requests_app/request_detail.html
- locale/fr/LC_MESSAGES/django.po
- locale/fr/LC_MESSAGES/django.mo
- docs/PHASE2_STAGE2.md
- local_artifacts/stage2_translations.py
- local_artifacts/test_stage2_runner.py
- local_artifacts/stage2_guard.json
- local_artifacts/stage2_evidence_b541dc19/pg18-regression-results.json
- local_artifacts/stage2_evidence_b541dc19/stage1-migration-results.json
- local_artifacts/stage2_evidence_b541dc19/stage2-migration-results.json

## Local verification

PostgreSQL 18.6, 127.0.0.1:55442, database test_microcom_stage2_regression,
role microcom_stage2_test. The launcher verified version, data directory and
connection identity before writes. Full suite: 225 run, 224 passed, no failures
or errors, one optional workbook sample-generation skip. Migration rehearsal
preserved all existing fields in four legacy requests/approvals and six movements
(including a zero pair and NULL retry tokens). Workflow migration: 0.180 seconds;
request migration: 0.564 seconds on tiny synthetic fixtures, not production timing.
Both took schema locks. Disposable databases/clusters were removed after testing.

Source comparisons confirmed resubmit_request(), workflow selection,
stock_services.py and requests_app migrations 0015/0016 unchanged in this stage.
No production access, installation, commit, push or deployment occurred.
