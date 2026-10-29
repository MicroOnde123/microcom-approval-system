# Checkpoint D — material request reference verification

## Finding

The authoritative existing request reference is `requests_app.Request.request_number`
(`requests_app/models.py:36`), a unique CharField. Normal creation assigns its existing
REQ-prefixed value in `requests_app/views.py:269`; request notifications, lists and
the approved document use that same field. Its generation is unchanged.

Invoice finalization already freezes `request.request_number` into
`invoice.request_reference_snapshot` (`invoicing/services.py:328`). The detached PDF
projection reads this snapshot (`invoicing/documents.py:83`); the bilingual renderer
prints the projected value (`invoicing/pdf.py:92`). It does not use a request PK,
derive a reference from a UUID, query a mutable request number or allocate a number.

The reviewed sample's UUID-looking reference originated in the general synthetic
stock fixture: `requests_app/test_stock_safety.py:42` explicitly sets request_number
to str(uuid4()). It was the synthetic request's actual reference, not an internal
identifier substituted by the renderer. The sample therefore exposed unrealistic
fixture data, not an incorrect finalization mapping or a renderer defect.

No existing application database was queried. This finding concerns the code,
previous synthetic samples and new disposable regression records; it does not certify
all persisted development/staging/production invoice references.

## Targeted changes and tests

Only the PDF tests' local factory now assigns realistic synthetic REQ-SYNxxx
references at request creation. The shared stock fixture and real request-number
generation remain unchanged. No application, renderer, finalization, pricing,
numbering, permission, stock or approval code was changed in this pass.

Two added regression tests verify:

1. The finalized snapshot equals the original existing request_number and both
   English/French PDF reference labels display it, not the request primary key.
2. Changing only a synthetic source request after finalization does not change the
   invoice snapshot or either PDF's reference. No finalized invoice is edited.

All **20 PDF tests passed**, no failures/errors/skips, in50.591 seconds on a fresh
identity-guarded disposable PostgreSQL18.6 cluster at127.0.0.1:15491,
database test_microcom_checkpoint_d_reference, role microcom_checkpoint_d_reference_test.
The checks also cover private storage, permissions, concurrency/retries, stock and
financial state preservation, formatting, frozen content and bilingual/multi-page PDFs.
System checks, migration consistency and protected source/translation checks passed.
No migration, dependency or translation-catalogue change was required. The complete
non-PDF suite was not rerun because no application behavior changed.

New English/French single-page samples display **REQ-SYN002**. The 66-line sample
displays **REQ-SYN003**. These are explicitly synthetic source request references,
not new references invented during invoice generation. Actual Windows.Data.Pdf
previews of the English/French single pages and the many-line first page were inspected.
Earlier samples are retained unchanged; no finalized snapshot or old artifact was
rewritten. Evidence: `local_artifacts/checkpoint_d_reference_evidence_0d994bfc/`.

## Historical safety boundary

If an actual finalized snapshot is independently found to contain an internal UUID
instead of its original human-readable request reference, stop that correction path.
Do not overwrite it, bypass immutability, regenerate numbering or silently fall back
to the current request row. First verify the original reference against independent
evidence. An explicitly approved, audited append-only correction/addendum mechanism
could preserve both the original issued content and the correction; its design and
authorization would be separate work. No such mechanism or data repair is implemented.

## Files and cleanup

Modified: `invoicing/test_documents.py` only (test fixture and two regression tests).
Created: this document; `local_artifacts/test_checkpoint_d_reference_runner.py`;
the evidence directory listed above, with PDFs/previews/text, test results,
verification summary and cleanup evidence.

The runner dropped its synthetic test database and stopped its owned cluster.
Only its explicitly identified disposable directory is removed after workspace-path,
reparse-point and absent-postmaster-PID checks. No production access, existing/shared
database connection, commit, push or deployment occurred. Ready for review; stop here.
