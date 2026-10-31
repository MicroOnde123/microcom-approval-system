# Stock classification review at any approval position

Base revision: d3eb76641c1bd3efe431f26a4536964a0be1aeaf. Local, uncommitted implementation; no deployment or production access performed.

## Root cause

workflows.models.validate_stock_review_steps required the review to have the minimum step_order. Both the standalone step admin form and the workflow inline formset invoke this validator. Request approval services independently required review to be the first row and blocked ordinary steps even when they preceded that review. Invoicing's evidence validator also required the classification approval to be the first row.

The PostgreSQL financial guard in invoicing/migrations/0002_financial_guards.py checks the designated approved classification evidence, not its first position; it needs no SQL change. Classification permissions/forms already use the saved requires_stock_classification flag rather than a hard-coded order.

## New behaviour

- Zero or one designated stock review remains supported for legacy compatibility. Multiple designations are rejected.
- A designated review can have any step order. Admin validation never inserts, moves or renumbers steps.
- Ordinary preceding steps approve normally without classification. Every preceding step must be completed (APPROVED or existing SKIPPED state) before a later approval can succeed, even if its current-step pointer is inconsistent.
- Only the saved designated primary/alternate can classify at its actionable step. Valid CLIENT/MICROCOM input is mandatory on approval; MICROCOM requires an active succursale; CLIENT rejects a selected succursale.
- Later steps require the designated review's approval and a valid classification, then continue in configured order. Rejection/return behaviour remains available without classification.
- Final stock deduction still uses the existing locked, transactional, flag-protected stock service; it was not rewritten.
- Invoice eligibility accepts the designated completed review at any position while preserving existing request, actor, stock and financial evidence checks.

## Correction history and retries

Resubmission now locks and rechecks the request's stored status. A stale Returned instance cannot rebuild an already-resubmitted request again.

Before rebuilding active approvals, the service writes APPROVAL_HISTORY_ARCHIVED in RequestAuditLog with a versioned JSON snapshot of **all database fields** of every previous approval, including original IDs, workflow-step/primary/alternate/actor IDs, classification flag, statuses, comments and timestamps. Snapshot and chain rebuilding share the existing transaction; a failure rolls back both. Earlier audit entries are not removed.

This deliberately retains the existing active-relation/retry model: old live RequestApproval rows are still replaced, so earlier cycles are preserved in the request Audit Log rather than added to the rebuilt Approval Timeline or the personal Approval History query. No approval-cycle schema or automatic data conversion was introduced. Previously deleted history cannot be reconstructed. This is complete field-level archival evidence, not a new immutable history viewer.

## Exact change set

| File | Change |
|---|---|
| workflows/models.py | Allow any position, retain uniqueness validation, update translated help text |
| workflows/migrations/0004_stock_review_position_help.py | Help-text state alignment only |
| requests_app/services.py | Relative-position gates, preceding-step check, locked resubmission and full prior-cycle audit snapshot |
| invoicing/services.py | Remove first-position assumption from classification evidence |
| locale/fr/LC_MESSAGES/django.po | Updated French help/validation messages |
| locale/fr/LC_MESSAGES/django.mo | Recompiled catalog, all 943 entries round-trip checked |
| requests_app/test_stock_classification.py | Replace old later-step rejection expectations; retain duplicate/role-only rejection |
| requests_app/test_stock_review_positions.py | Position, admin POST, classification/access, invoice evidence, archive/retry/rollback and localization regressions |
| config/test_stock_review_settings.py | Standalone in-memory SQLite test settings; never imports production settings or .env |
| docs/STOCK_REVIEW_ANY_STEP.md | Change, validation and deployment notes |

Existing untracked training-guide/PDF/assets files from the earlier documentation task are separate and were not rebuilt or included in this fix. They remain drafts tied to the earlier source behaviour and need revision before distribution.

A separate comment-only edit in config/settings.py appeared during the task (removal of an outdated return-note activation comment). It was not made by this fix, was left untouched, and is excluded from the change set above.

## Validation performed

Command, using the existing rehearsal virtual environment but current workspace source:

    C:\MicrocomRehearsal\venv\Scripts\python.exe -m django test requests_app.test_stock_review_positions requests_app.test_stock_classification.StockClassificationTests requests_app.test_stock_safety.StockSafetyTests requests_app.tests.ReturnedMaterialRequestEditTests.test_reused_resubmit_token_only_resubmits_once --settings=config.test_stock_review_settings --noinput --verbosity=1

Result: **63 tests passed**, 9.772 seconds; Django system checks: zero issues. Database was disposable in-memory SQLite with migrations disabled; no external database or production .env was used.

Coverage includes:

- Stock review first, second and final; four-step sequential progression and exactly one deduction.
- Real Django admin workflow-change POST saving Step 2 with IDs/order/actors unchanged; duplicate designations rejected.
- Missing/invalid classification, inactive/missing MICROCOM branch, CLIENT with/without branch, unauthorized and preceding/later-step classification.
- Legacy approval snapshots and already-classified requests, first-step compatibility and named primary/alternate checks.
- Resubmission complete archive, fresh classification confirmation, stale object/reused HTTP token rejection, rollback on failure.
- Invoice evidence from review at each tested position and English/French validation.
- Existing stock-safety functional tests, including return caps/retries and rollback.

Additional checks: git diff --check clean; database-free migration autodetection found no model-state drift; sqlmigrate of the new help-text migration emitted a no-op under the isolated settings. French PO/MO entries were round-trip verified.

An initial 33-test run exposed the stale compiled French message; it was corrected before the passing runs. A subsequent 60-test run passed, followed by the final expanded 63-test run above.

**Not established:** PostgreSQL concurrent locking/deadlock behaviour, actual SQL-trigger execution, authenticated rehearsal-browser acceptance or the full suite. No claim is made that the 805-test suite passed. Before production release, repeat focused tests in an approved isolated PostgreSQL environment with production-equivalent migrations/guards and perform the Fiber workflow rehearsal.

## Migration requirements

0004 is an AlterField for help_text only. No table/column/data change or backfill is needed; runtime behaviour does not depend on applying it. Include it to keep Django's migration state aligned with the model. No existing migration was edited and no database migration was executed here.

During separately authorized deployment, review and record the metadata migration through the normal process. Do not run an unrestricted migrate against production as part of testing.

## Windows Server deployment and acceptance

1. Review the code/PO/MO/migration change set above separately from the unrelated untracked training artifacts. Preserve the current deployed release for rollback using the approved release process.
2. Apply to rehearsal first with the matching application dependencies; run focused PostgreSQL tests using approved standalone test settings and disposable data. Never use config.settings or the production database for these tests.
3. In a running approved rehearsal, open Material Request Fiber with existing ordered steps: Initial approval → Stock lady → Direction → Finances. Mark Step 2 Stock Classification Review, keep its active named primary/optional alternate, and save. Confirm no row order/actor changed. No automated configuration update is supplied.
4. Submit synthetic CLIENT and MICROCOM requests. Complete Step 1, verify Step 2 cannot approve without valid classification and branch rules, then finish Direction/Finances. Check one OUT per material, repeat-action rejection, invoice eligibility and archive/retry behaviour after correction.
5. Deploy the reviewed application files, compiled French catalog and metadata migration via the existing authorized Windows release mechanism. Record the metadata migration only when separately approved. No static asset change requires collectstatic for this patch.
6. Arrange the normal separately authorized application reload/recycle so Python and translation caches load the new release. No Windows service was restarted or reconfigured by this task.
7. An authorized administrator can then save the intended Step 2 designation manually. This task does not change any production workflow record.
8. Monitor validation errors and application logs during initial use. Roll back by the approved release process if necessary; do not undo approved stock movements or rewrite request classifications to simulate rollback.

## Pending-request risks

Existing pending requests retain their saved approval snapshots; changing a workflow does not retrofit their review designation or assignments. A legacy request with no designated classification remains legacy; an already-designated first-step request remains first-step. Requests already classified remain usable, and invoice checks now accept valid designated evidence at later positions.

No mass conversion/backfill is included. If a specific in-flight request needs reassignment/rebuilding, plan that separately with the owner; do not edit snapshots automatically. The new preceding-step check can block previously inconsistent current-step pointers. Such records require investigation, not forced approval.
