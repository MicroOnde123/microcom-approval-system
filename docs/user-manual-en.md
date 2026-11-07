# Microcom User Manual

Version 2.0 — 2026-11-02

REVIEW EDITION — authentic screenshots are partial; workflow discrepancy and deployment verification remain unresolved. Not approved as a final training guide.

Code: `d3eb76641c1bd3efe431f26a4536964a0be1aeaf`

This guide updates the user and administrator guides under docs/manuals/. Screenshots show the actual local Django application using training data.

## A. Access and navigation

Employees use their individual account. Navigation reflects their access; an absent menu is not a reason to share an administrator account.

Prerequisites: Active account; approved application address supplied by your administrator.

1. Open the approved address and enter your username and password on Login. Never use a password-reset link supplied by another employee.
2. Use the dashboard to open Create Request, My Requests or Pending Approvals as appropriate. Review the request reference before acting.
3. Choose English or Français in the language selector. Documents use the current application language; choose it before opening a PDF.
4. Use Logout when finished. An expired session requires signing in again; unsaved form content may be lost.

Expected: your own dashboard and permitted menus. If access fails, ask the administrator to check account activation; never publish passwords or session cookies.

![A · Sign in](manual-assets/en/annotated/login-annotated.png)

1. Username field · 2. Submission control: read the page before confirming

![A · Dashboard and navigation](manual-assets/en/annotated/dashboard-annotated.png)

1. Application navigation and language controls · 2. Dashboard work area

## B. Administrative requests and corrections

A request belongs to its Request For Department, which determines routing. Saving a draft does not submit it for approval.

Prerequisites: Signed-in requester; active request type and applicable workflow.

1. Open Create Request. Select Request Type and Request For Department; enter Description / Reason, Date Needed and any type-specific fields.
2. Add required attachments. Check the selected files and remove inappropriate confidential information before submission.
3. Save as Draft to continue later, or submit the completed request. Record its generated REQ-ADM reference; other configured types have their own stable namespace.
4. Open My Requests and filter by reference, department, type, status or dates. Open the detail page to read comments and approval progress.
5. For a Returned request, read the correction comment, open its edit action, correct the fields and submit again. The request keeps its original reference.
6. Use cancellation only when available for your open request. An approved request cannot be rewritten through the correction process.

Expected: one stable reference, including drafts and resubmissions. A missing workflow blocks submission; contact the administrator rather than changing the department merely to bypass routing.

![B · Create a request](manual-assets/en/annotated/request-create-annotated.png)

1. Request type · 2. Owning department

![B · My Requests](manual-assets/en/annotated/my-requests-annotated.png)

1. Search and filter controls · 2. Record list or material lines

![B · Request draft](manual-assets/en/annotated/request-draft-annotated.png)

1. Page heading and permitted actions · 2. Edit the open request

![B · Edit a request](manual-assets/en/annotated/request-edit-annotated.png)

1. Request type · 2. Submission control: read the page before confirming

## C. Technician material requests

Request only the materials required. Technicians submit and track requests; authorized stock personnel record subsequent reconciliation and physical returns.

Prerequisites: Material request type and available active materials.

1. Select the material request type on Create Request. Confirm the owning department before entering material rows.
2. Add each material, quantity and useful item note. Check units carefully; do not treat a cable length as a number of pieces.
3. Review all rows and submit, or save a draft. A draft does not reserve or deduct stock.
4. Keep the REQ-MAT reference and follow the approval chain in request details. Final stock availability is checked again during approval.

Expected: complete material rows and an approval chain after submission. Correct invalid quantities; never create a second request merely because a response was slow.

![C · Material request entry](manual-assets/en/annotated/material-request-create-annotated.png)

1. Request type · 2. Search/select material by name, code or category

![C · Material and quantity rows](manual-assets/en/annotated/material-request-lines-annotated.png)

1. Search/select material by name, code or category · 2. Requested quantity in the material unit

![C · Pending Approvals](manual-assets/en/annotated/pending-approvals-annotated.png)

1. Search and filter controls · 2. Record list or material lines

## D. Stock classification: deployment discrepancy

RELEASE CHECK: the supplied target workflow allows stock review at any configured step. This checkout still requires it to be the FIRST step. Do not configure the proposed Step 2 example against this version.

Prerequisites: Assigned primary or alternate stock reviewer at the current approval step. A stock-report flag alone does not assign an approval.

1. Open Pending Approvals and the assigned material request. Confirm quantities, purpose and supporting evidence.
2. For CLIENT work, choose CLIENT. No Microcom succursale is required or retained.
3. For MICROCOM work, choose MICROCOM and select a valid succursale. Classification and succursale are mandatory for this approval.
4. Approve only after review. Missing classification blocks approval; returning for correction or rejecting must remain possible under the existing rules.
5. The requested Fiber example is Initial approval → Stock Classification Review → Direction → Finances. It is a target example, NOT a verified configuration supported by this checkout. Ask the application owner to reconcile versions first.

Expected: classification evidence is retained. Never reorder a live workflow or grant administrator access to work around a routing error.

![D · CLIENT classification — control detail](manual-assets/en/annotated/stock-classification-client-annotated.png)

1. CLIENT / MICROCOM classification · 2. Succursale selection for MICROCOM

![D · MICROCOM classification — control detail](manual-assets/en/annotated/stock-classification-microcom-annotated.png)

1. CLIENT / MICROCOM classification · 2. Succursale selection for MICROCOM

![D · Approval workflow configuration](manual-assets/en/annotated/admin-workflow-annotated.png)

1. Stored name · 2. Configured approval steps

## E. Central inventory and material prices

One central warehouse supplies technicians. Succursales identify administrative destinations and billing entities, not independent warehouses.

Prerequisites: Stock-report access for reports; separate staff and model permissions for Django material administration.

1. Open Material Reports to review issued, physically returned and remaining returnable quantities, alongside ledger status.
2. Authorized administrators open Inventory → Materials in Django Admin. Select an existing item to review code, category, unit, stock and minimum level.
3. When adding a priced material, verify the proposed USD selection or choose CDF/EUR. Editing retains the saved currency; there is no automatic currency conversion.
4. Enter an unknown price as blank, not zero. Zero means an explicit legitimate price. Save only approved catalog changes.
5. Do not edit stock balances to simulate an issue or a return. Use the approved operational process and investigate inconsistent movement history.

Expected: prices and currencies are deliberate. Catalog changes do not rewrite finalized invoice snapshots. A historical discrepancy requires stock administrator review, not deletion of movements.

![E · Material Reports](manual-assets/en/annotated/material-reports-annotated.png)

1. Search and filter controls · 2. Record list or material lines

![E · Material catalog](manual-assets/en/annotated/admin-materials-annotated.png)

1. Administration search · 2. Authorized records

![E · Unit price and currency — control detail](manual-assets/en/annotated/admin-material-annotated.png)

1. Unit price; blank means unknown · 2. Stored price currency

## F. Approvals, corrections and stock deduction

Only the current assigned approver or permitted alternate acts. Request status and your own approval action are different pieces of information.

Prerequisites: A submitted request assigned to the signed-in approver.

1. Open Pending Approvals, then the request. Read attachments, quantities and previous comments.
2. Choose Approve, Return for correction or Reject as appropriate and provide the required comment. Do not approve incomplete evidence.
3. An approval advances to the next configured step. At final material approval, the application validates and deducts stock exactly once.
4. Use Approval History to review your actions and the overall request status. The requester corrects a Returned request through its edit/resubmit flow.
5. If final approval fails, report the displayed validation message and request reference. Do not manually deduct stock or repeatedly submit different operations.

Expected: the approved request retains its approval history and exactly one issuance per material. Printing, reconciliation and reporting must not repeat this deduction.

![F · Pending Approvals](manual-assets/en/annotated/pending-approvals-annotated.png)

1. Search and filter controls · 2. Record list or material lines

![F · Approval History](manual-assets/en/annotated/approval-history-annotated.png)

1. Search and filter controls · 2. Record list or material lines

![F · Approved material request](manual-assets/en/annotated/approved-request-annotated.png)

1. Page heading and permitted actions · 2. Related operational and document actions

## G. Bon de commande and bon de sortie

BC is an internal material order, not supplier purchasing. BS documents the authorized issue. Both use the existing issue-note layout, with different titles and references.

Prerequisites: Approved material request, confirmed stock deduction and material rows; requester, assigned approver, stock user or superuser access as permitted.

1. Open the approved request and choose BC or BS in its document actions.
2. For first issuance, verify the request reference on the confirmation page. Cancel leaves it unissued; opening this page alone assigns no number.
3. Choose Confirm & Print only when authorized. This POST assigns a permanent BC/0001/YYYY or BS/0001/YYYY reference using independent annual counters.
4. Use the print view controls and browser print dialog; Save as PDF is a browser option where supported.
5. Reopen the same document for a reprint. Its reference remains unchanged and no stock is deducted again. Material-report bulk printing does not allocate official references.

Expected: at most one BC and one BS per request. Their annual rollover uses Africa/Kinshasa. Do not confuse the request reference with either document reference.

![G · BC first-issuance confirmation](manual-assets/en/annotated/bc-confirm-annotated.png)

1. Original material request reference · 2. Submission control: read the page before confirming

![G · BS first-issuance confirmation](manual-assets/en/annotated/bs-confirm-annotated.png)

1. Original material request reference · 2. Submission control: read the page before confirming

## H. Internal invoices

A facture is on-demand bookkeeping for one eligible MICROCOM request, not a sale or a stock movement. CLIENT work does not require an internal Microcom invoice.

Prerequisites: Approved MICROCOM request with actual OUT evidence, confirmed succursale and physical address, compatible material prices, verified company settings, and a verified annual INVOICE series for finalization. Explicit invoice action permissions and stock-review scope are required.

1. Open Invoices and select an eligible candidate request, or use the permitted invoice action associated with the request. Select the currency and create its draft.
2. Review material descriptions, net billable quantities, currency and unit prices. Catalog prices are copied into the draft when currencies match; unknown or mismatched prices remain incomplete.
3. An authorized editor may correct draft prices or explicitly refresh quantities. Review the history; a refresh may record that no quantity or price changed.
4. A draft has a Draft #ID label and a provisional sum only when all lines are priced. It has no official invoice number or finalized total.
5. Choose Finalize invoice, review the configured series and confirm only after verifying all evidence. Finalization freezes the branch name/address, company data, material labels and financial values. Do not use this training manual to issue live financial documents.
6. For a finalized invoice, use Print Invoice. The active-language PDF opens in the private viewer with Print and Download fallback controls. Existing artifacts remain immutable and checksummed.
7. For combined printing, enter both From and To official issue dates in Invoices, refine search/status, then print filtered invoices. Only authorized finalized matches across all pages are included, subject to the configured maximum.

Expected: official FAC/0001/YYYY numbering only at finalization. New years require verified financial sequences; never reset a counter. After an error, reload and request administrator review without changing guards or frozen values.

![H · Invoice list and filters](manual-assets/en/annotated/invoices-annotated.png)

1. Official issue-date and invoice filters · 2. Record list or material lines

![H · Invoice draft](manual-assets/en/annotated/invoice-draft-annotated.png)

1. Page heading and permitted actions · 2. Record list or material lines

![H · Invoice finalization — configuration check](manual-assets/en/annotated/invoice-finalize-annotated.png)

1. Document or administration page heading · 2. Protected confirmation form

## I. Credit notes: supported boundary

The repository contains credit models, allocations, reservation audit and financial guards. No employee credit creation/issuance/PDF route is present in invoicing/urls.py. A complete credit-note workflow must not be inferred from model permissions or Django Admin.

Prerequisites: Administrator or finance review of the supported business process; no documented self-service credit action.

1. If a monetary credit or refund is needed, stop and contact the responsible finance administrator.
2. Do not use a physical return receipt or financial Material Return Note as a credit, refund or payment adjustment.
3. Do not create or edit protected credit records manually to bypass the missing issuance workflow. Active credit allocations exclude financial return-note evidence for the entire invoice, in both directions.

Expected: escalation rather than an invented menu or unsafe financial workaround. Credit creation screenshots are not applicable to this checkout.

## J. Material Management, physical returns and receipts

Use the existing three-tab Material Management workspace. Reconciliation records outcomes; a physical return restores central stock; RCP acknowledges actual returns; invoice-linked BR values eligible returns without changing stock or the original invoice.

Prerequisites: Approved material request with confirmed deduction; authorized stock personnel. Financial BR additionally needs its enabled gate, explicit permissions, scope, finalized invoice and eligible post-finalization returns.

1. Open Material Management from request details or Material Reports. Overview shows issued, CLIENT-installed, MICROCOM-used, physically returned and retained/testing quantities.
2. In Reconcile, record technician-reported outcomes for every material. Use split quantities where needed, select the responsible technician and give the reason. Returned quantities come from actual movements and are not invented in this editor.
3. Review and save a revision. The original classification, approvals, OUT movements and BC/BS stay unchanged. Open revision history to inspect previous reports. A stale edit requires reloading and reviewing the latest revision.
4. Receive and verify the physical materials before opening Returns & Receipts. Enter an allowed quantity and reason; review and confirm the return. No separate return approval lifecycle is introduced. The protected service restores stock exactly once.
5. Do not exceed the remaining quantity. Fully returned materials have no active return action. Historical stock discrepancy — review required means stop and ask the stock administrator; never delete movements or edit balances.
6. Select recorded, undocumented RETURN movements and confirm Generate Bon de retour to issue the NONFINANCIAL RCP receipt. It works for CLIENT, MICROCOM and requests without invoices. Reprints keep the RCP reference and do not restore stock again.
7. Use View PDF or Print on an issued receipt. The current application language is used. A PDF failure does not undo the recorded physical return or receipt; retry the PDF only.
8. For financial BR, use the finalized invoice return-note action only when enabled and authorized. Select complete eligible RETURN movements strictly after invoice finalization; preview their frozen valuation, enter a reason and confirm once.
9. An uncertain BR outcome must be retried using the SAME retained confirmation handle and issuance token. Do not start a new preview as a substitute. If the session is lost, inspect issued-note history and contact support before attempting another operation.
10. Financial BR leaves the original facture unchanged, with cumulative caps, rounding and credit exclusivity enforced. The signed preview lasts two hours but the application session still times out after 15 minutes.

Expected: auditable outcome revisions and stock restoration only for accepted physical returns. The isolated rehearsal keeps financial BR disabled; issuance, financial PDFs and recovery screenshots remain pending.

Representative example: a CPE initially requested for MICROCOM testing is installed at the CLIENT site; unused cable and power supply are physically received back into stock. Record the returns, then reconcile mixed outcomes. The original MICROCOM classification remains unchanged. This feature supports every stock-managed material, not just CPEs.

![J · Material Management — Overview](manual-assets/en/annotated/material-overview-annotated.png)

1. Overview tab · 2. Issued quantities and outcomes

![J · Material Reconciliation editor](manual-assets/en/annotated/material-reconcile-editor-annotated.png)

1. Reconcile tab · 2. Outcome editor; expand the material row

![J · Physical return editor](manual-assets/en/annotated/material-return-editor-annotated.png)

1. Returns & Receipts tab · 2. Physical return form; receive materials first

## K. Administrator reference

Administrative access is separate from operational stock and financial permissions. Never grant staff status merely to permit a scoped stock action.

Prerequisites: Authorized staff account and the relevant model/action permissions.

1. In Django Admin, maintain active users, departments and roles. Use individual identities and review stock-report and administration-report flags separately.
2. Maintain request types and applicable workflows by owning department and amount range. Set primary and alternate approvers and unique step order. Test routing with approved rehearsal data before operational use.
3. STOP: this source currently permits one designated stock-review step and requires it first. The desired any-step configuration must be reconciled with the application owner before publishing that procedure.
4. Maintain succursale name, code, active status and physical address. New succursales require an address; legacy blank records can remain, but new Microcom invoice finalization requires a valid address.
5. Review Company and document settings, save approved details and use Attest current company information. Changing those details invalidates the current content attestation for future issuance.
6. Review Document sequences for type, year, series, format, next counter and verification evidence. Use the existing verification action; never reset a used counter. Financial invoice preparation does not silently attest a new year.
7. Inspect request, reconciliation, receipt and invoice histories. Report protected-record errors instead of modifying immutable records. Requests cannot be added through Django Admin; create them through the application.

Expected: permissions and attestations are explicit. Do not expose private PDF paths, reset links, logs containing credentials or signed confirmations in support tickets or training screenshots.

![K · Administration modules](manual-assets/en/annotated/admin-annotated.png)

1. Authorized administration modules · 2. Account and session actions

![K · User management](manual-assets/en/annotated/admin-users-annotated.png)

1. Administration search · 2. Authorized records

![K · Approval workflow list](manual-assets/en/annotated/admin-workflows-annotated.png)

1. Administrative list and actions · 2. Authorized records

![K · Approval workflow configuration](manual-assets/en/annotated/admin-workflow-annotated.png)

1. Stored name · 2. Configured approval steps

![K · Succursale name and address — control detail](manual-assets/en/annotated/admin-succursale-annotated.png)

1. Stored name · 2. Succursale physical address

![K · Company and document settings](manual-assets/en/annotated/admin-company-annotated.png)

1. Company settings, not the invoice PDF heading

![K · Business timezone and numbering preference](manual-assets/en/annotated/admin-company-timezone-annotated.png)

1. Africa/Kinshasa business timezone · 2. Invoice numbering preference; sequence verification is separate

![K · Verified financial sequences](manual-assets/en/annotated/admin-sequences-annotated.png)

1. Administrative list and actions · 2. Document or administration page heading

## L. Reports, exports and troubleshooting

Reports respect your permitted dataset. Filters narrow that dataset; they do not grant access to other departments or financial values.

Prerequisites: Material Reports flag or superuser; separate financial invoice permission/scope for bookkeeping values. Administration Report uses its own flag.

1. Set search, department and dates as offered. Use Reset to clear filters. Invalid dates display errors and no results rather than an unfiltered report.
2. Review issued, returned and remaining quantities and the movement status. Open request details or history for evidence; an inconsistency disables further return actions.
3. Export Excel using the active filters. Authorized financial users receive eight worksheets; stock-only users receive seven without Bookkeeping. The four existing charts are retained.
4. Review Material Report, Dashboard, Graphs, Stock Movements, Succursale Summary, Material Group Summary and Monthly Statistics. Bookkeeping uses finalized snapshots only and is added only where authorized.
5. Keep currencies and units separate. Blank historical prices mean unknown, never zero. CLIENT activity remains in stock statistics but internal facture coverage is not applicable; MICROCOM invoices are on demand.
6. An export exceeding the configured row limit (default 10,000) must be narrowed using filters. Exports never issue BC/BS, invoices or stock movements.
7. For support, provide the request/document reference, timestamp, action, language and sanitized displayed error. Never send passwords, session cookies, confirmation tokens or complete confidential documents.

Expected: localized, read-only reports. Missing access requires an authorized permission review, not another employee’s exported workbook.

![L · Material Reports](manual-assets/en/annotated/material-reports-annotated.png)

1. Search and filter controls · 2. Record list or material lines

![L · Invalid date filter — safe error state](manual-assets/en/annotated/material-filter-error-annotated.png)

1. Correct the invalid start date · 2. Validation error: no unfiltered results are shown

![L · Invoice list and filters](manual-assets/en/annotated/invoices-annotated.png)

1. Official issue-date and invoice filters · 2. Record list or material lines

## Quick troubleshooting

- Missing approval controls: check current assignment and status, not just stock-report access.
- Missing price: complete the draft using authorized evidence; never replace an unknown value with zero.
- Missing sequence/company verification: contact the administrator; never change counters or guards.
- PDF failure: return to the issued document and retry only generation, not issuance.
- Uncertain financial issuance: retain the same confirmation; inspect history if the session was lost.
- Historical over-return or ambiguous OUT: stop returns and request a ledger review.

## Glossary

- Succursale — Administrative destination/billing entity; not a warehouse.
- BC — Internal material order.
- BS — Authorized material issue note.
- FAC — Immutable finalized internal bookkeeping invoice.
- RCP — Nonfinancial receipt linked to actual physical RETURN movements.
- BR — Invoice-linked returned-material valuation; no refund, credit or stock operation.
- Reconciliation / Régularisation — Append-only report of actual material outcomes.
- Africa/Kinshasa — Business timezone used for annual numbering and operational reporting.
