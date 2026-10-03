# Microcom Approval & Workflow System

## End User Manual

**Document version:** 1.0  
**Audience:** Employees and approvers  
**Language:** English

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Login](#2-login)
3. [Dashboard](#3-dashboard)
4. [Creating Requests](#4-creating-requests)
5. [Request For Department](#5-request-for-department)
6. [Draft Requests](#6-draft-requests)
7. [Editing Returned Requests](#7-editing-returned-requests)
8. [Cancelling Requests](#8-cancelling-requests)
9. [Approval Process](#9-approval-process)
10. [Tracking Requests](#10-tracking-requests)
11. [Material Documents](#11-material-documents)
12. [Frequently Asked Questions](#12-frequently-asked-questions)
13. [Best Practices](#13-best-practices)

---

## 1. Introduction

The Microcom Approval & Workflow System is used to submit, approve, track, print, and report company requests. It helps employees send requests to the correct department and helps approvers review them in a controlled workflow.

### 1.1 What the System Does

You can use the system to:

- Create requests.
- Save incomplete requests as drafts.
- Submit requests for approval.
- Track request status.
- Correct and resubmit returned requests.
- Cancel open requests.
- Approve, reject, or return requests if you are an approver.
- Print approved material or permission documents when available.

### 1.2 Types of Requests

The system supports several request types, including:

- Material requests.
- General requests.
- Payment requests.
- Leave and permission requests.

The fields shown on the request form may change depending on the selected request type.

**Screenshot placeholder:** Dashboard after login.

---

## 2. Login

### 2.1 Login

1. Open the Microcom Approval & Workflow System in your browser.
2. Enter your username and password.
3. Select **Login**.

After login, the dashboard opens.

**Screenshot placeholder:** Login page.

### 2.2 Password Reset

If you forget your password:

1. Open the login page.
2. Select the password reset link.
3. Enter the email address registered with your account.
4. Follow the reset instructions sent by email.

> **Note:** If you do not receive a reset email, contact the system administrator to confirm that your account email address is correct.

### 2.3 Language Switching

The system supports English and French. Use the language selector in the navigation area to switch languages.

---

## 3. Dashboard

The dashboard is the first page shown after login.

### 3.1 Dashboard Widgets

Depending on your access, the dashboard can show request and approval information such as pending actions, returned requests, and navigation to common work areas.

### 3.2 Navigation Menu

Common menu items include:

- **Dashboard**
- **Create Request**
- **My Requests**
- **Pending Approvals**
- **Approval History**
- **Material Reports** for authorized stock users

### 3.3 Notifications

The system displays pending approval and returned request indicators where applicable. Approvers should check pending approvals regularly.

**Screenshot placeholder:** Navigation menu and notification indicator.

---

## 4. Creating Requests

Open **Create Request** to start a new request.

### 4.1 Common Fields

Most request forms include:

- **Request Type:** Select the type of request.
- **Request For Department:** Select the department that owns the request.
- **Description:** Explain why the request is needed.
- **Amount:** Required only for request types that need an amount.
- **Date Needed:** The date when the request is needed.
- **Attachments:** Add supporting files when required.

### 4.2 Material Request

For material requests, add each required material item:

- Material.
- Quantity.
- Item note, if needed.

The system checks available stock. You cannot request more than the available quantity shown for the material.

> **Tip:** Use the item note for serial numbers, location, installation details, or other useful information.

### 4.3 General Request

For general requests:

1. Select the general request type.
2. Select the correct Request For Department.
3. Enter a clear description.
4. Add attachments if needed.
5. Submit or save as draft.

### 4.4 Payment Request

For payment requests:

1. Select the payment request type.
2. Enter the amount if required.
3. Describe the reason for the payment.
4. Attach supporting documents if required.
5. Submit for approval.

Amount-based workflows may route higher-value requests to additional approvers.

### 4.5 Leave or Permission Request

For leave or permission requests, the form displays additional fields.

Leave permission may include:

- Permission type.
- Destination.
- Reason.
- Departure time.
- Return time.
- Arrival time.
- Driver name.

Site authorization may include:

- Site.
- Valid from.
- Valid to.
- Microcom agents.
- TT.
- External persons.
- Reason.

> **Note:** Departure and return times may be optional for leave permission, depending on the form rules currently configured.

### 4.6 Submit the Request

When the request is complete:

1. Review the selected request type and Request For Department.
2. Confirm the description, amount, material items, and attachments.
3. Select **Submit Request**.

The request is sent to the first approver in the applicable workflow.

---

## 5. Request For Department

### 5.1 What It Means

By default, the request is assigned to your department. If you are submitting on behalf of another department, select the appropriate department.

This field controls which department owns the request and which workflow is used for approval.

### 5.2 Examples

**Example 1: You submit for your own department**

If you work in Administration and the request is for Administration, leave **Request For Department** as Administration.

**Example 2: You submit for Fiber**

If you work in Administration but are creating a request for Fiber, select Fiber as **Request For Department**.

**Example 3: You submit for IT**

If you work in Administration but are creating a request for IT, select IT as **Request For Department**.

> **Warning:** Choosing the wrong department may send the request to the wrong approval workflow.

**Screenshot placeholder:** Request For Department field on the request form.

---

## 6. Draft Requests

### 6.1 Save as Draft

Use **Save as Draft** when the request is incomplete or you need to finish it later.

### 6.2 Edit Draft

Drafts appear in **My Requests**. Open the draft and select **Edit Draft** to continue working on it.

### 6.3 Submit Draft Later

When the draft is complete, submit it for approval from the edit screen.

> **Warning:** Drafts are NOT sent for approval. Approvers will not see a request until it is submitted.

### 6.4 Draft Limitations

- Drafts do not create approval steps.
- Drafts do not reserve material stock.
- Drafts do not deduct material stock.
- Drafts can be cancelled.

---

## 7. Editing Returned Requests

### 7.1 Returned Request Process

An approver may return a request when information is missing or changes are required. Returned requests appear with status **Returned**.

The approver's comment explains what should be corrected.

### 7.2 Modify Materials

For returned material requests, you can update material rows:

- Change the material.
- Change the quantity.
- Update the item note.

### 7.3 Remove Materials

To remove an item, delete the material row or mark it for removal if the form provides a delete option.

### 7.4 Add Replacement Materials

Add a new material row for the replacement item, enter the quantity, and save or resubmit.

### 7.5 Resubmit

After making corrections:

1. Review all fields.
2. Confirm Request For Department.
3. Submit the request again.

The system creates a new approval path for the corrected request.

> **Tip:** Address the approver's comment directly before resubmitting.

---

## 8. Cancelling Requests

### 8.1 When Cancellation Is Available

You can cancel your own request when it is still open, including:

- Draft.
- Returned.
- Pending.
- In Review.

### 8.2 When Cancellation Is Unavailable

You cannot cancel a request after it has been:

- Approved.
- Rejected.
- Already cancelled.

### 8.3 How to Cancel

1. Open **My Requests**.
2. Open the request details.
3. Select the cancellation action if it is available.
4. Confirm the cancellation.

> **Warning:** Cancel a request only when it should no longer continue. If the request only needs corrections, use the returned-request edit process.

---

## 9. Approval Process

### 9.1 Pending Approval

A request is pending or in review when it is waiting for one or more approvers.

Approvers can open **Pending Approvals** to see requests assigned to them as primary or alternate approver.

### 9.2 Approver Actions

Approvers can:

- **Approve:** Move the request to the next approval step or final approval.
- **Return:** Send the request back to the submitter for correction.
- **Reject:** Close the request as rejected.

### 9.3 Status Meanings

- **Draft:** Saved but not submitted.
- **Pending / In Review:** Submitted and waiting for approval.
- **Returned:** Sent back for correction.
- **Approved:** Fully approved.
- **Rejected:** Rejected by an approver.
- **Cancelled:** Stopped by the submitter before final completion.

### 9.4 Final Approval

When the last approval step is approved, the request becomes **Approved**. For material requests, stock is deducted after final approval.

---

## 10. Tracking Requests

### 10.1 My Requests

Use **My Requests** to view requests you submitted. You can filter by status and Request For Department.

### 10.2 Request Details

The request detail page shows:

- Request number.
- Request type.
- Submitted-from department.
- Request For Department.
- Status.
- Description.
- Amount and date needed.
- Material items.
- Attachments.
- Approval steps.
- Audit history.

### 10.3 Request History

Approvers can use **Approval History** to review requests they acted on or were assigned to. Department filters use Request For Department.

**Screenshot placeholder:** Request detail page with approval history.

---

## 11. Material Documents

### 11.1 Material Exit Slip

Approved material requests can produce a **Material Exit Slip**. This document supports material issue, signature, and record-keeping processes.

### 11.2 Printing

Use the print action on approved material documents or material report bulk print where available.

### 11.3 Signatures

Printed material documents may include signature areas for operational validation. Follow internal procedures for signature collection.

### 11.4 Record Keeping

Keep printed documents according to department procedures. Material issue notes can record serial numbers, delivery remarks, installation notes, or other issue details.

---

## 12. Frequently Asked Questions

### 12.1 Why is my request not approved yet?

It may still be waiting for the current approver. Open the request detail page to review the approval steps and status.

### 12.2 What is a Draft?

A draft is a saved request that has not been submitted for approval.

### 12.3 Why was my request returned?

An approver returned it because corrections or additional information are needed. Read the approver's comment, edit the request, and resubmit.

### 12.4 Can I edit an approved request?

No. Approved requests are final. Contact an administrator if a correction is required for record-keeping.

### 12.5 Can I cancel my request?

You can cancel your own request while it is open. You cannot cancel it after it is approved or rejected.

### 12.6 How do I request for another department?

Select the correct department in **Request For Department** before submitting.

### 12.7 Why can I not see Material Reports?

Material Reports are available only to users with stock-management access.

---

## 13. Best Practices

- Choose the correct request type.
- Confirm Request For Department before submitting.
- Provide a clear description and complete supporting information.
- Add attachments when they help approvers decide.
- Save as draft when information is incomplete.
- Review returned-request comments carefully.
- Do not request more material than required.
- Check **Pending Approvals** regularly if you are an approver.
- Use comments when approving, returning, or rejecting a request.
- Print and file material documents according to internal procedures.

