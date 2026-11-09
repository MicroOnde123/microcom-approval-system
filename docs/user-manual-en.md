![Microcom](manual-assets/microcom-logo.png)

# Microcom Approval System

## Employee Training Guide

**NOVEMBER 2026 — TEXT USER GUIDE**

Version 3.0 · November / novembre 2026 · 2026-11-09

Source: 72b527b739d2e42a0ead10d17af4ec571876dfc8

Final text edition. Follow the numbered procedures for your authorized role. Application screenshots are a separate future improvement.

[Validation](user-manual-validation.md) · [Capture checklist / Liste des captures](manual-screenshot-checklist.md) · [EN/FR](user-manual-fr.md)

## Contents

- [0. Using this guide](#guide-start)
- [1. Sign in](#01-login)
- [2. Navigate the dashboard](#02-dashboard)
- [3. Create an administrative request](#03-administrative)
- [4. Create a technician material request](#04-material)
- [5. Classify at the designated stock-review step](#05-classification)
- [6. Select the succursale](#06-succursale)
- [7. Approve, reject or return](#07-decisions)
- [8. Correct, resubmit or cancel](#08-correction)
- [9. View availability and stock reports](#09-stock)
- [10. Maintain materials, prices and currencies](#10-catalog)
- [11. Understand automatic deduction](#11-deduction)
- [12. Issue BC and BS](#12-bcbs)
- [13. Create and prepare an invoice draft](#13-invoice-draft)
- [14. Verify and finalize the invoice](#14-invoice-issue)
- [15. Credit notes: availability boundary](#15-credit-boundary)
- [16. Record a physical stock return](#16-physical-return)
- [17. Reconcile material usage](#17-reconciliation)
- [18. Issue a nonfinancial RCP return receipt](#18-receipt)
- [19. Issue an invoice-linked valued return note](#19-return-note)
- [20. Follow approvals and audit records](#20-audit)
- [21. Manage users and permissions](#21-users)
- [22. Configure approval workflows](#22-workflows)
- [23. Configure verified company/document information](#23-company)
- [24. Print and download documents](#24-print)
- [25. Troubleshoot without duplicate operations](#25-errors)
- [26. Register a new material and initial stock](#26-entry-new)
- [27. Receive an existing material](#27-entry-existing)
- [28. Save, resume and cancel an entry draft](#28-entry-drafts)
- [29. Use workflow notifications and email preferences](#29-notifications)
- [A. Glossary and references](#glossary)

<a id="guide-start"></a>

## 0. Using this guide

November 2026 release. Procedures reflect the current implementation and the invoice-page presentation update. No production records were used to prepare this guide.

Microcom has one central stock. Succursales are administrative/billing entities, never warehouses. Request For Department owns/routes the request; it is not a billing succursale. Original stock classification is distinct from later usage outcomes. CLIENT requests are excluded from internal invoicing; eligible MICROCOM requests can have an individual invoice created when needed.

Read prerequisites, follow the numbered steps, then check the expected result. Important checks explain permissions, errors and safeguards. Examples use synthetic references.

| Role / Rôle | Access / Accès |
|---|---|
| Employee / technician | Own submissions, own Draft/Returned editing, own open cancellation and permitted approved documents; department needed to create. |
| Primary / alternate approver | Current assigned pending step only; permitted assigned-request access. Later approvers wait. |
| Stock personnel | can_manage_stock or superuser: reports, physical returns, reconciliation, RCP and approved material issue notes. No invoice grant implied. |
| Administration report reader | can_view_administration_reports or superuser: approved configured-type report across departments; no ordinary detail/approval grant. |
| Invoice operator | view_invoice plus action permission and stock-review assignment scope; superuser or staff + manage_all_invoices for global scope. |
| Administrator | Staff/model permissions and explicit financial attestations. Role names alone are not blanket permissions. |

Draft/request → submit → designated stock review at its configured position (when configured) → ordered approvals → final approval and one stock deduction. Then issue BC/BS and, for eligible MICROCOM, create/review/finalize the invoice. Later: physical return restores stock; reconciliation records outcomes; RCP documents physical returns; invoice-linked note values returns. None automatically creates an accounting credit.

<a id="01-login"></a>

## 1. Sign in

**Before you begin** — Use your own active account and the application address supplied by IT.

### Do this

1. Open the approved application address and check that you are on the intended system.

2. Enter username/password and use the login button.

3. For a forgotten password, use the reset link and registered email; contact IT if delivery or the link fails.

> **Important check** — Never capture a populated password. Session expiry requires signing in again and can lose unsaved edits.

> **Expected result** — Dashboard opens; invalid/inactive accounts cannot sign in.

<details><summary>Code trace</summary>

config/urls.py; accounts/forms.py; templates/registration/login.html

</details>

<a id="02-dashboard"></a>

## 2. Navigate the dashboard

**Before you begin** — Signed-in users see navigation according to their access. Dashboard status text is not a live health check.

### Do this

1. Use Create Request / New Request to begin and My Requests for your submissions.

2. Use Approvals for current assigned steps and Approval History for your decisions.

3. Open permitted reports or Invoices. Choose EN/FR with the language selector; use Logout when finished.

> **Important check** — A role name does not grant every menu. Check lists even without email: workflow notifications may fail silently.

> **Expected result** — The right work area opens in the chosen language.

<details><summary>Code trace</summary>

core/views.py; templates/core/dashboard.html; templates/base.html; requests_app/context_processors.py

</details>

<a id="03-administrative"></a>

## 3. Create an administrative request

**Before you begin** — Your account needs a department and a configured workflow. Request-type flags control required fields.

### Do this

1. Choose Request Type and Request For Department: the owning team, not a billing succursale.

2. Enter description, Date Needed and Amount when required; attach supporting files.

3. For Leave Permission enter By Foot/By Car, destination and reason; travel times/driver are optional. Site Authorization requires site, validity dates, Microcom agents and reason; TT/external persons are optional.

4. Submit Request, or Save as Draft. Reopen My Requests → Edit Draft, finish and submit.

> **Important check** — A draft starts no approvals or stock reservation. Recheck saved rows if incomplete. Amount is not an invoice/payment execution. Check chronological consistency yourself.

> **Expected result** — Submission starts routing; a draft remains editable and unsubmitted. Note the reference.

<details><summary>Code trace</summary>

requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/create_request.html

</details>

<a id="04-material"></a>

## 4. Create a technician material request

**Before you begin** — Choose a material request type, owning department and active catalog materials. All materials come from central stock.

### Do this

1. Enter purpose/destination and Date Needed.

2. Search by name, code or category, or Filter By Category; select the actual item and enter a positive quantity in its unit.

3. Use + Add Material / Remove, one row per item; review then Submit Request or Save as Draft.

> **Important check** — At least one item, no duplicates, and valid positive quantities are required. Stock is checked at entry and final approval; nothing is reserved. No editable item-note box is rendered: use the description.

> **Expected result** — The request enters approval. Technicians do not perform stock classification or select the billing branch.

<details><summary>Code trace</summary>

requests_app/forms.py; requests_app/views.py:create_request; templates/requests_app/includes/material_formset.html

</details>

<a id="05-classification"></a>

## 5. Classify at the designated stock-review step

**Before you begin** — Only the assigned active primary or alternate can classify when this step is current; preceding steps must finish first.

### Do this

1. Open the current assigned approval and review the materials and purpose.

2. Choose Approve and CLIENT or MICROCOM. CLIENT does not require a succursale.

3. For MICROCOM select the appropriate active succursale, add the required comment and submit.

4. Later approvers wait for their configured turn. A workflow may place stock review second or last without reordering other steps.

> **Important check** — Only one designated review is allowed. Designation is optional in configuration: administrators must ensure material workflows include it. Returning or rejecting does not require classification.

> **Expected result** — Valid classification is required before this step can approve. CLIENT requests do not require an internal invoice.

<details><summary>Code trace</summary>

requests_app/approval_forms.py; requests_app/classification.py; requests_app/services.py:approve_step; workflows/models.py

</details>

<a id="06-succursale"></a>

## 6. Select the succursale

**Before you begin** — A succursale is an administrative/billing entity, never a warehouse. You must be the designated stock reviewer approving Microcom.

### Do this

1. Confirm the intended destination with the requesting team and select its code/name in Succursale.

2. If missing/inactive, ask an authorized administrator to review Inventory → Succursales; do not substitute another branch or department.

3. Submit and check classification/branch in request details.

> **Important check** — Microcom requires a branch; Client must not select one. New branches require physical address; final invoicing requires it for older branches too. Selection never transfers stock.

> **Expected result** — The billing entity is linked; stock remains central.

<details><summary>Code trace</summary>

requests_app/approval_forms.py; requests_app/classification.py; inventory/models.py:Succursale; inventory/admin.py

</details>

<a id="07-decisions"></a>

## 7. Approve, reject or return

**Before you begin** — Only your current pending primary/alternate step of an open request is actionable.

### Do this

1. Filter Approvals by type, owning department, search or Date Needed range.

2. Inspect details, amount, materials and attachments before Review / Approve Request.

3. Choose Approve, Reject or Return for changes, explain in Comment and Submit; refresh to check result.

> **Important check** — Comment is optional in code but should explain rejection/correction. Once one assigned actor acts, the other cannot repeat. Later steps wait; superuser alone cannot bypass assignment. Required does not skip steps.

> **Expected result** — Approve advances/finalizes; Return sets Returned; Reject closes as Rejected, without ordinary resubmission.

<details><summary>Code trace</summary>

requests_app/views.py:pending_approvals,approval_detail; requests_app/services.py; requests_app/approval_forms.py

</details>

<a id="08-correction"></a>

## 8. Correct, resubmit or cancel

**Before you begin** — The active owner edits their own Draft or Returned request. Read the return comment first.

### Do this

1. Open My Requests, the request, then Edit and Resubmit or Edit Draft.

2. Correct the information and material rows; add attachments when necessary. Save Changes keeps a returned request returned.

3. Choose Resubmit Request when complete. Material requests restart the applicable approval workflow.

4. General Permission requests can resume at the returning step only if approval-relevant information, workflow and reliable evidence are unchanged; otherwise they restart.

5. Read the resubmission result and previous attempts. If no longer needed, use Cancel Request only for an eligible open request and confirm.

> **Important check** — Earlier approval rows are archived before active routing is rebuilt. Existing history predating this archive feature is not reconstructed. Rejected requests have no ordinary resubmission action.

> **Expected result** — The original request reference remains stable; earlier decisions remain visible as archived evidence.

<details><summary>Code trace</summary>

requests_app/views.py:edit_request,cancel_request; requests_app/services.py:resubmit_request; templates/requests_app/edit_request.html

</details>

<a id="09-stock"></a>

## 9. View availability and stock reports

**Before you begin** — Employees see availability in picker/permitted details. Material Reports requires can_manage_stock or superuser.

### Do this

1. Read material units and current central availability; no stock is reserved by browsing.

2. Open Material Reports and apply the offered request, department and date filters.

3. Review current inventory, entries, issuance/returns and warehouse activity in the available report sections. Keep units and currencies separate.

4. Export the filtered Excel report. Financial sheets and values remain permission-scoped; exports never post stock or issue documents.

> **Important check** — Requested quantities, current balances and net returns describe different measures. Current Stock Inventory is a live snapshot including inactive materials; request/activity filters do not apply to that sheet. Narrow large exports and investigate inconsistent evidence before further stock actions.

> **Expected result** — Find approved material requests and download the filtered report without moving stock.

<details><summary>Code trace</summary>

inventory/models.py; requests_app/views.py:material_reports; templates/requests_app/material_reports.html

</details>

<a id="10-catalog"></a>

## 10. Maintain materials, prices and currencies

**Before you begin** — Django Admin requires staff access and material permissions. Catalogue price editing also supports active stock personnel through Material Entries.

### Do this

1. In Inventory → Materials maintain category, unique code, name, description, unit, active status and minimum stock level.

2. On an unbound Add Material form, currency uses company document currency or USD. An existing USD, CDF or EUR remains selected; an unassigned currency displays the default.

3. Enter a known unit price and select USD, CDF or EUR. Blank price means unknown; zero is an explicit price. There is no currency conversion.

4. For an existing price/currency change, enter Price change reason and Save. Stock, price and catalogue revisions must still match; reload and review conflicts.

5. Alternatively, on Receive Stock select the material and Modify Price. Enter price, currency and a meaningful reason, then save the price in the dialog. This is separate from receipt confirmation.

6. Use View price history in Admin to inspect actor, reason, old/new values and source. Use Material Entries for traceable deliveries rather than direct stock edits.

> **Important check** — A blank currency submitted with a price resolves to company currency or USD, even if the old currency differed. Opening a form writes nothing. Saving a displayed default is an audited currency change. Direct Admin stock edits do not create receipt movements.

> **Expected result** — Price history is append-only. Catalogue changes do not rewrite finalized invoices, stock quantities or old financial records.

<details><summary>Code trace</summary>

inventory/models.py; inventory/admin.py; core/document_config.py

</details>

<a id="11-deduction"></a>

## 11. Understand automatic deduction

**Before you begin** — There is no Deduct Stock button. The final assigned approver completes the material workflow.

### Do this

1. Review and submit the final Approve action.

2. If insufficient stock is reported, ask stock staff to review; do not force Approved manually.

3. On success check Approved and the timeline; authorized administrators can inspect related OUT movements.

> **Important check** — The service locks request/material balances and uses stock_deducted against repeated deduction. Failure rolls back final approval. Safeguards were inspected, not runtime-tested for these guides.

> **Expected result** — Stock deducts once and OUT movements record the actor. Documents/invoices/reconciliation never deduct again.

<details><summary>Code trace</summary>

requests_app/services.py:approve_step; requests_app/stock_services.py:deduct_material_stock

</details>

<a id="12-bcbs"></a>

## 12. Issue BC and BS

**Before you begin** — BC is an internal material order; BS is the authorized issue document. Requires Approved, stock_deducted, material rows and permitted request/document access.

### Do this

1. In detail or Material Reports open the required BC or BS action.

2. At first issuance check kind/reference, then Confirm & Print. Cancel allocates nothing.

3. Check the official reference, choose Print 1 copy / Print 2 copies; over six items forces one. Print / Save as PDF, review A4, sign/archive.

> **Important check** — Confirmation allocates once; reprints reuse it. Format examples: BC/0001/2026 and BS/0001/2026, not actual records. Issuance never moves stock. Legacy bulk printing does not allocate official BC/BS.

> **Expected result** — The numbered document opens. Reference is frozen; live names, available stock and editable issue remarks may change on reprint.

<details><summary>Code trace</summary>

requests_app/material_documents.py; requests_app/views.py:material_document; templates/requests_app/material_document_confirm.html

</details>

<a id="13-invoice-draft"></a>

## 13. Create and prepare an invoice draft

**Before you begin** — One invoice per individual eligible MICROCOM request, on demand. Requires view_invoice + add_invoice and scope, Approved/deducted stock evidence, designated-review confirmation/branch and valid company configuration.

### Do this

1. Open Invoices. Requests available for invoice review appears first, above invoice history. Search by request reference with its Search button and open the eligible request link.

2. On the creation screen review the MICROCOM request and succursale, select invoice currency and confirm draft creation. Eligibility is checked before saving.

3. Below the available requests, existing invoices have their own search, issue-date and status filters, Print Filtered Invoices, history table and pagination. Request search does not filter invoices or printing.

4. Open Edit invoice draft: check Net billable quantity, enter authorized Unit price and optional Invoice note; Save draft prices.

5. After new physical returns use Refresh issued quantities, then review/save again before finalization.

> **Important check** — CLIENT excluded. Draft has no official number. Net quantities = issued less returns. Other-currency catalog prices remain unknown; no conversion. Zero is explicit, blank unknown. Duplicate/ambiguous stock evidence blocks invoicing.

> **Expected result** — An editable unnumbered draft is ready for review; no stock/payment operation occurs.

<details><summary>Code trace</summary>

invoicing/permissions.py; invoicing/views.py:invoice_list,invoice_create,invoice_edit; invoicing/services.py

</details>

<a id="14-invoice-issue"></a>

## 14. Verify and finalize the invoice

**Before you begin** — Requires view_invoice + finalize_invoice and scope; prices/net quantities reviewed; current company attestation, verified annual series and branch physical address.

### Do this

1. Open Finalize invoice and compare materials, net quantities, prices and totals to evidence.

2. Choose Invoice series. If absent, ask the authorized administrator to verify numbering; do not invent a number.

3. Tick permanent confirmation and Finalize invoice. Check Finalized, number, issue date, branch, total and Invoice history.

> **Important check** — User review and administrator attestations are prerequisites, not an extra invoice approval status. Financial/party snapshots and number become immutable. Currency consistent; date/year Africa/Kinshasa. New returns/stale revision require refresh/review.

> **Expected result** — Permanent bookkeeping invoice issued without a second stock deduction. Later returns do not silently rewrite it; ordinary edit/delete is unavailable.

<details><summary>Code trace</summary>

invoicing/forms.py; invoicing/services.py:finalize_invoice; invoicing/views.py:invoice_finalize

</details>

<a id="15-credit-boundary"></a>

## 15. Credit notes: availability boundary

**Before you begin** — Credit models/database safeguards exist, but no employee credit-note creation/issue route or registered credit admin lifecycle was found.

### Do this

1. Record original invoice reference and actual physical return evidence.

2. Ask Finance/IT to assess the accounting action; do not invent a Create credit note button.

3. Keep physical RCP receipt, invoice-linked return valuation and accounting credit separate.

> **Important check** — Schema safeguards include finalized original invoice/currency, attributable returns, reservation caps, explicit review, verified numbering and immutable final evidence. This does not prove deployed guards or expose a user workflow. Active credit allocations can block valued return notes.

> **Expected result** — The accounting need is escalated without fabricating a credit. This is a boundary notice, not an issue procedure.

<details><summary>Code trace</summary>

invoicing/models.py:CreditNote,CreditAllocation,CreditOperation; invoicing/migrations/0004_credit_reservation_schema.py; invoicing/migrations/0005_credit_financial_guards.py; invoicing/urls.py; invoicing/admin.py

</details>

<a id="16-physical-return"></a>

## 16. Record a physical stock return

**Before you begin** — Stock access, Approved/deducted material request and consistent OUT/RETURN evidence are required. Receive the goods before recording.

### Do this

1. Material Management → Returns & Receipts: expand the correct material. The standalone Return to Stock page remains available.

2. Check Available to return; enter positive Returned Quantity (two decimals) and required Return Reason.

3. Confirm return to stock, review the dialog then Confirm; Back cancels. Check success/new remainder. Fully returned items have no active form.

> **Important check** — Cumulative cap enforced. Locks and one transaction protect stock/movement/audit. Exact committed-token replay does not restore twice. If uncertain retry the same form or inspect history, not a new operation. Ambiguous old evidence is blocked. Server checks apply without JavaScript.

> **Expected result** — Stock restored once with RETURN/audit reason. Ten issued minus four returned leaves six eligible. No invoice, credit or receipt is automatically issued.

<details><summary>Code trace</summary>

requests_app/stock_services.py:return_material_stock,material_return_totals; requests_app/material_outcome_views.py; requests_app/stock_forms.py

</details>

<a id="17-reconciliation"></a>

## 17. Reconcile material usage

**Before you begin** — Stock personnel record outcomes for the original technician on an Approved/deducted request. Original classification is unchanged.

### Do this

1. Use Material Management → Overview, then Reconcile and expand each material.

2. Use quick destination for all remaining units or Split quantities / multiple outcomes: CLIENT-installed, MICROCOM-used, Retained / testing.

3. Physically returned is read-only from movements. All four outcomes must total issued quantity. Enter Short explanation, Review and save, review then Confirm; inspect Reconciliation history.

> **Important check** — Before a revision, usage is unknown. New physical returns can mark the old revision Review required. Reload stale data and append a new revision; old revisions remain. No stock/invoice changes.

> **Expected result** — Versioned outcomes account for every unit: e.g. ten issued = four CLIENT + two MICROCOM + one retained + three physically returned.

<details><summary>Code trace</summary>

requests_app/material_outcomes.py:reconcile; requests_app/material_outcome_views.py; templates/requests_app/material_outcomes.html

</details>

<a id="18-receipt"></a>

## 18. Issue a nonfinancial RCP return receipt

**Before you begin** — The stock button Generate Bon de retour creates an RCP physical-return receipt, not a financial credit or invoice-linked valuation.

### Do this

1. With stock access, select recorded physical RETURN movements under Material Return Receipt.

2. Generate Bon de retour, review selections and Confirm; Back issues nothing.

3. Check the RCP reference/history. Set application language, then View PDF / Print; use the PDF viewer to save/print.

> **Important check** — Only actual distinct returns not already in an RCP. Exact token replay reuses the receipt. No stock change, credit, refund or invoice adjustment. On PDF failure use retry on this receipt; do not issue another.

> **Expected result** — A permanent RCP/year reference and frozen return snapshot are available through protected PDF access.

<details><summary>Code trace</summary>

requests_app/material_outcomes.py:issue_receipt; requests_app/material_outcome_views.py:receipt_pdf; requests_app/return_receipt_documents.py

</details>

<a id="19-return-note"></a>

## 19. Issue an invoice-linked valued return note

**Before you begin** — Requires enabled UI, finalized internal invoice, eligible complete returns, verified RETURN_NOTE year/series, invoice scope and dedicated permissions.

### Do this

1. From finalized invoice open Issue material return note or Material return note history.

2. Select eligible complete movements, Operation reason and Return note series; Preview material return note.

3. Check original invoice, frozen prices, quantities, returned value, cumulative value and adjusted net value. Change selection if needed; preview allocates no number.

4. Tick permanent confirmation and Issue material return note; check its number/history, then Print if permitted.

> **Important check** — Current settings enable UI; fallback/older notes say disabled: verify deployment, do not change flags. Pre-invoice excluded returns, duplicates, ambiguous provenance or active credit allocations can block. Confirmation max two hours; session may expire earlier. Lost response: check history first.

> **Expected result** — Permanent valuation issued at original invoice prices, without stock change, credit/payment adjustment or rewriting the original invoice. Distinct from RCP.

<details><summary>Code trace</summary>

invoicing/return_note_access.py; invoicing/return_note_views.py; invoicing/return_note_services.py; invoicing/return_note_forms.py; config/settings.py

</details>

<a id="20-audit"></a>

## 20. Follow approvals and audit records

**Before you begin** — Use ownership/assignment or appropriate report/invoice access; report-only rights do not unlock ordinary request detail.

### Do this

1. Open My Requests → detail: reference/status, origin/owning departments, attachments, Approval Timeline and Audit Log.

2. Approval History shows your latest qualifying non-pending action per request, not all assignments; filter owning department.

3. Invoice history → Audit details explains financial events. Material Management shows reconciliation revisions and RCP history.

4. Administration Report readers filter approved configured-type requests by search, origin/owner/requester and submission dates, then View Document / Print (25 per page).

5. For an approved Administration permission request, View Document / Print opens the dedicated Bon d’accès. Report access does not grant ordinary request editing or approval rights.

> **Important check** — Earlier approvals are archived on resubmission and can be consulted in previous attempts. Pre-feature missing history is not reconstructed. Audit evidence is not a complete snapshot of every field.

> **Expected result** — Support can trace a reference/action/time and distinguish decisions, stock and document evidence.

<details><summary>Code trace</summary>

requests_app/views.py:request_detail,approval_history,administration_reports; invoicing/views.py:invoice_detail; templates/requests_app/request_detail.html

</details>

<a id="21-users"></a>

## 21. Manage users and permissions

**Before you begin** — Authorized staff/model access and an approved account process are required. No accounts are created during guide preparation.

### Do this

1. Accounts → Users: maintain identity, required email, department, role, Active; maintain Departments/Roles separately.

2. Grant Can Manage Stock Reports / Can view administration reports only as needed; staff/model access is separate.

3. Invoices require view_invoice plus add/change/finalize as needed and stock-review assignment scope. Broad scope: superuser or staff + manage_all_invoices.

4. Valued notes: view_invoice + view_materialreturnnote; preview also issue_materialreturnnote; issue also add_materialreturnnote; documents also view_materialreturnnote_document. Save and arrange access verification.

> **Important check** — Custom ModelAdmin is not the standard password wizard: never type plaintext in its raw password field; use approved provisioning/reset. Deactivate leavers, preserve actors. Stock flag or staff alone grants no invoice actions/scope.

> **Expected result** — Existing accounts have the approved permissions; assigned current steps still control approvals.

<details><summary>Code trace</summary>

accounts/admin.py; accounts/models.py; invoicing/permissions.py; requests_app/material_outcomes.py:authorize

</details>

<a id="22-workflows"></a>

## 22. Configure approval workflows

**Before you begin** — Authorized administrator and agreed policy. Routing uses type/amount and owning department, then department-free global fallback.

### Do this

1. Maintain Request types and Requires materials / Requires amount / Is permission request flags; keep assigned reference namespaces unchanged.

2. Workflows → Approval workflows: type, optional owning department, amount bounds, Active.

3. Add unique ordered steps: specific user or active owning-department role user, with alternate where appropriate.

4. For material workflows designate at most one Stock classification review at any valid position, with an active named primary and optional active alternate. Save without reordering existing steps.

> **Important check** — The stock review is actionable only after preceding approvals. Test the configured sequence using approved rehearsal data.

> **Expected result** — Future submissions use configured steps; saving configuration is not proof of runtime acceptance.

<details><summary>Code trace</summary>

workflows/models.py; workflows/admin.py; requests_app/services.py:get_applicable_workflow,create_approval_steps

</details>

<a id="23-company"></a>

## 23. Configure verified company/document information

**Before you begin** — Authorized staff/model rights including invoicing.add_companyverification for company attestation and invoicing.change_documentsequence for sequence attestation; checked external numbering history.

### Do this

1. Core → Company and document settings: name, verified address, contacts, existing static logo reference, default USD/CDF/EUR and Africa/Kinshasa timezone; Save.

2. In the list select settings and Attest current company information after checking; re-attest relevant changes.

3. Invoicing → Document sequences: correct INVOICE or RETURN_NOTE type/year/series/format/safe starting value and external-history evidence. Save, select and Attest checked external numbering history.

4. Inventory → Succursales: maintain code/name/active/physical address; new branches require address and invoicing requires it.

> **Important check** — Never guess counters, lower used counters or rewrite issued references. Format preferences alone allocate nothing; BC/BS and RCP have separate automatic counters. No authorization here to run year-preparation commands or change flags.

> **Expected result** — Current company and annual numbering have recorded attestations, enabling issuance if other checks pass; frozen existing documents remain unchanged.

<details><summary>Code trace</summary>

core/models.py; core/admin.py; invoicing/admin.py; invoicing/models.py:CompanyVerification,DocumentSequence; inventory/admin.py

</details>

<a id="24-print"></a>

## 24. Print and download documents

**Before you begin** — Authorized document access and issued/finalized documents; browser PDF capability. Check type, reference and language.

### Do this

1. Set application language; finalized invoice → Print Invoice. The server prepares its protected PDF; use viewer print/save.

2. For filtered invoices, supply both issue dates in Invoices, narrow search/status then Print Invoices. Server selects finalized matches across pages; maximum 20.

3. BC/BS use Print / Save as PDF and copy controls. RCP uses View PDF / Print; valued return note uses Print.

4. Approved permissions use Permission Document → Print / Save PDF. Authorized Administration Report readers use View Document / Print.

> **Important check** — Invoice printing uses protected PDF artifacts, not page-body printing. Filtered print has 20-document, size and page limits. PDF failure does not undo issuance: retry existing document, not a new invoice/receipt. Legacy material bulk print allocates no official BC/BS.

> **Expected result** — Reviewed PDF/print uses the existing official reference. Layout, printer behaviour and download protection still require rehearsal verification.

<details><summary>Code trace</summary>

invoicing/views.py:invoice_print,invoice_bulk_print; invoicing/printing.py; invoicing/print_delivery.py; requests_app/material_outcome_views.py; templates/invoicing/list.html

</details>

<a id="25-errors"></a>

## 25. Troubleshoot without duplicate operations

**Before you begin** — Read exact error and preserve request/document reference. IT handles configuration/inconsistent evidence.

### Do this

1. Missing workflow/department/approver: report type, owning department and amount; check My Requests before recreating.

2. Classification: Client without branch; Microcom with active branch. Stock/excess return/stale revision: refresh evidence, correct quantity; never force status/movements.

3. Invoice missing price/address/attestation/series: resolve with Finance/IT. PDF failure: retry existing document.

4. Expired confirmation: reopen/preview as directed. Uncertain issuance: history first. Forbidden: check action permission and request scope.

> **Important check** — Never create a new return/receipt/invoice just to check the first. No passwords or confidential attachments in support messages. A missing credit-note screen is a product boundary.

> **Expected result** — Resolve/escalate with reference, time and exact message, avoiding duplicate stock/documents.

<details><summary>Code trace</summary>

requests_app/approval_forms.py; requests_app/stock_services.py; invoicing/services.py; invoicing/return_note_services.py; PDF error templates

</details>

<a id="26-entry-new"></a>

## 26. Register a new material and initial stock

**Before you begin** — Active stock personnel or superuser. One central stock; no warehouse selection.

### Do this

1. Open Material Entries and Register New Material.

2. Enter name, unique code, category, unit, description, active status, minimum stock level and optional catalogue price. This form initially selects USD; choose CDF or EUR explicitly when needed.

3. Enter initial quantity (at least 0.01), receipt date, and optional supplier, delivery reference and notes.

4. Choose Verify details. Nothing is received yet. Check material identity, unit, price, quantity and delivery details; use Modify to correct.

5. Choose Confirm and Save once. Read Receipt completed and retain the IN reference. Open View receipt details or Receipt History.

> **Important check** — A new material with zero opening stock cannot use this receipt form; authorized Admin catalogue creation is separate. Draft saving and verification do not create stock. Retry the same operation after a lost response; do not start a duplicate delivery.

> **Expected result** — Confirmation atomically creates the material, receipt and IN movement. Initial stock is recorded once.

<details><summary>Code trace</summary>

inventory/entry_forms.py; inventory/entry_services.py; inventory/entry_views.py; templates/inventory/entry_review.html

</details>

<a id="27-entry-existing"></a>

## 27. Receive an existing material

**Before you begin** — Active stock personnel or superuser. Price-edit permission alone does not allow receipts or receipt history.

### Do this

1. Open Material Entries → Receive Stock and search/select the existing material.

2. Check code and unit, current stock and catalogue price. Enter quantity received, receipt date, supplier/reference and notes as applicable.

3. Read Estimated stock after receipt as an estimate. Choose Verify details and check the summary.

4. Choose Confirm and Save. Read the IN reference, quantity received and stock after receipt.

5. Open receipt details/history to consult the saved record. New Entry starts a separate delivery.

> **Important check** — Receipt confirmation shows recorded historical balances, not live stock. Older records without an identity snapshot label catalogue fields as current information. A receipt is not linked to a technician request, invoice or credit note.

> **Expected result** — The confirmed receipt increases central stock once and creates an incoming movement.

<details><summary>Code trace</summary>

inventory/entry_forms.py; inventory/entry_views.py; inventory/entry_services.py; templates/inventory/receipt_confirmation.html

</details>

<a id="28-entry-drafts"></a>

## 28. Save, resume and cancel an entry draft

**Before you begin** — Stock access; drafts belong to their creator and are separate from request drafts.

### Do this

1. On either entry form choose Save Draft to retain unfinished information without receiving stock.

2. After Draft saved successfully choose Continue Editing or New Entry. Saved Drafts lists your own open drafts with Resume Draft and Cancel Draft.

3. Resume the draft, finish its fields, then Verify details and Confirm and Save.

4. To abandon an open draft, choose Cancel Draft, review the confirmation and confirm cancellation.

5. If another tab changed the draft, reload and review the latest information. Completed drafts cannot be cancelled; find their receipt instead.

> **Important check** — A draft is not a reservation, material registration or IN movement. Cancelling it does not reverse an already completed receipt. Do not reuse stale tabs to overwrite newer work.

> **Expected result** — Only confirmation posts the stock receipt; saving or cancelling unfinished work leaves inventory unchanged.

<details><summary>Code trace</summary>

inventory/entry_drafts.py; inventory/entry_views.py; templates/inventory/draft_saved_notice.html; templates/inventory/cancel_entry_draft.html

</details>

<a id="29-notifications"></a>

## 29. Use workflow notifications and email preferences

**Before you begin** — Active individual account. Notifications do not replace approval authorization.

### Do this

1. Open Notifications in the navigation. Choose All or Unread; use View All Notifications for the paginated history.

2. Check reference and current state. View Request marks the notification read and opens the request only when your access still permits it.

3. Use Mark as Read to acknowledge a notice without approving, rejecting or returning the request.

4. Use Pending Approvals for work that is currently actionable. Historical notifications do not reactivate completed or superseded assignments.

5. Ask an authorized administrator to adjust Receive email notifications in Accounts → Users. This preference controls optional workflow email, not security/account messages or in-app notifications.

> **Important check** — The unread badge counts active unread approval notices, not every unread historical event. Earlier events are not backfilled. Email failure does not cancel the request; check the application queues.

> **Expected result** — Read state is personal. Marking read changes neither the request decision nor stock.

<details><summary>Code trace</summary>

requests_app/notifications.py; requests_app/notification_views.py; templates/includes/workflow_notifications.html; accounts/admin.py

</details>

<a id="glossary"></a>

## A. Glossary and references

New ordinary references follow REQ-{namespace}-{counter}/{year}, e.g. REQ-MAT-0001/2026 or REQ-ADM-0001/2026: examples only, not real records. They are durable at creation, including drafts; older references remain unchanged. BC/BS/RCP allocate independently at issuance in the Africa/Kinshasa business year. Never manually reuse/rewrite references.

| Term / Terme | Meaning / Sens |
|---|---|
| Draft / Returned / Rejected | Unsubmitted / needs correction / closed by rejection: distinct states. |
| Pending / In Review / Approved / Cancelled | Open approval / under review / final success / stopped before completion. |
| Origin / owning department | Submitter department / Request For Department for routing and most filters. |
| CLIENT / MICROCOM | Original classification confirmed by designated stock reviewer. |
| BC / BS | Internal material order / authorized material issue, each with an official reference. |
| Invoice | Bookkeeping snapshot for one eligible MICROCOM request; not a payment operation. |
| RCP receipt | Nonfinancial evidence of physical returns, not credit/refund/invoice adjustment. |
| Valued return note | Invoice-linked valuation of already-returned materials, not physical stock restoration or credit. |
| Reconciliation | Versioned CLIENT-installed, MICROCOM-used, retained and physically returned outcomes. |
| OUT / RETURN | Actual stock deduction / actual stock restoration movement. |
| Material Issue Note | Free-text issue remarks: stock users open approved material detail, edit the note and Save Note. It appears in documents/reports; not a separately numbered document. Old full note text is not preserved in the update event. |
| Audit / snapshot | Action evidence / frozen document data; not every request field has historical snapshots. |

Final text edition. Follow the numbered procedures for your authorized role. Application screenshots are a separate future improvement.
