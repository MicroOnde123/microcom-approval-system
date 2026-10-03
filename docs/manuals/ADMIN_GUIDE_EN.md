# Microcom Approval & Workflow System

## Administrator Manual

**Document version:** 1.0  
**Audience:** System administrators, department administrators, platform managers  
**Language:** English

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Login](#2-login)
3. [User Management](#3-user-management)
4. [Workflow Management](#4-workflow-management)
5. [Request Types](#5-request-types)
6. [Inventory & Materials](#6-inventory--materials)
7. [Department Ownership](#7-department-ownership)
8. [Draft Requests](#8-draft-requests)
9. [Returned Requests](#9-returned-requests)
10. [Request Cancellation](#10-request-cancellation)
11. [Reporting](#11-reporting)
12. [System Administration](#12-system-administration)
13. [Troubleshooting](#13-troubleshooting)
14. [Best Practices](#14-best-practices)

---

## 1. Introduction

The Microcom Approval & Workflow System is a web-based platform for creating, approving, tracking, printing, and reporting operational requests. It supports department ownership, configurable approval workflows, material inventory control, English and French usage, and auditable request history.

### 1.1 Purpose of the Platform

The system centralizes request handling so that requests are submitted through a standard process, routed to the correct department approvers, reviewed step by step, and retained with an audit trail.

Administrators use the platform to maintain:

- Departments and roles.
- Users and stock-management access.
- Request types and their behavior.
- Approval workflows and approval steps.
- Material catalog, stock levels, and reporting controls.

### 1.2 Key Features

- Custom departments and roles.
- Custom user profiles with employee ID, department, role, and stock-report permission.
- Configurable request types for material, payment, general, and permission/leave workflows.
- Department-specific workflows and global fallback workflows.
- Amount-based workflow ranges.
- Sequential approval steps with primary and alternate approvers.
- Draft requests that are not submitted for approval until the user submits them.
- Returned-request correction and resubmission.
- Request cancellation for open requests.
- Material stock deduction after final approval.
- Material return-to-stock records.
- CSV and Excel material report exports.
- Printable material exit slips and permission documents.
- English and French language support.

### 1.3 Approval Workflow Overview

When a user submits a request, the system selects an active workflow for the request type. If the request has an amount, the workflow must also match the configured minimum and maximum amount rules.

Workflow selection follows this order:

1. Active workflow matching the request type and the selected **Request For Department**.
2. Active workflow matching the request type with no department assigned. This is the global fallback.
3. If no workflow matches, submission is blocked and the administrator must configure an applicable workflow.

After a workflow is selected, the system creates approval records for each workflow step. The current step is routed to the configured approver user or to an active user in the owning department with the configured role.

> **Note:** The owning department for routing is **Request For Department**, not the submitter's department.

**Screenshot placeholder:** Administrator dashboard and navigation menu.

---

## 2. Login

### 2.1 Administrator Login

Administrators sign in at `/login/` using their assigned username and password. After login, users are redirected to the dashboard.

Administrators with staff access can open Django administration at `/admin/`.

**Screenshot placeholder:** Login screen.

### 2.2 Password Reset

Users can request a password reset from the login page. The system uses the configured email backend to send reset instructions. The password reset pages are available under `/password-reset/`.

### 2.3 Security Recommendations

- Assign administrator access only to users who require it.
- Keep user email addresses valid because password reset depends on email.
- Deactivate user accounts instead of deleting them when the user leaves or changes responsibilities.
- Review users with stock-management rights regularly.
- Use strong passwords and avoid shared administrator accounts.
- Keep environment secrets out of source control.

> **Warning:** Never reuse a personal user account as a shared administrative account. Audit history is tied to the user who performed each action.

---

## 3. User Management

User management is performed in the administration area.

### 3.1 Departments

Departments represent organizational units such as Administration, Fiber, IT, Finance, or Logistics.

Each department has:

- **Name:** Human-readable department name.
- **Code:** Unique short code.

Departments are used for user assignment, request ownership, filtering, reporting, and approval routing.

### 3.2 Roles

Roles represent approval responsibilities. Examples include Department Manager, Finance Manager, Stock Manager, or Director.

Each role has:

- **Name:** Human-readable role name.
- **Code:** Unique short code.

Workflow steps can route approvals to a specific user or to the first active user in the request-owning department with the configured role.

### 3.3 Users

Users have the standard login fields plus Microcom-specific fields:

- **Full name**
- **Employee ID**
- **Department**
- **Role**
- **Can Manage Stock Reports**
- **Active status**
- **Staff status** for administrative access

The system requires a valid email address in the admin user form.

### 3.4 Create a Department

1. Open `/admin/`.
2. Go to **Accounts > Departments**.
3. Select **Add Department**.
4. Enter the department name and unique code.
5. Save.

**Screenshot placeholder:** Department creation form.

### 3.5 Edit a Department

1. Open **Accounts > Departments**.
2. Select the department.
3. Update the name or code.
4. Save.

> **Tip:** Avoid changing department codes after workflows and reports are in production unless the change has been approved internally.

### 3.6 Disable a Department

The current department model does not include an active/inactive flag. To stop using a department:

1. Remove it from new workflow configuration.
2. Move active users to another department or deactivate them.
3. Keep the department record for historical request and audit integrity.

> **Warning:** Do not delete departments that are already referenced by users, workflows, or requests.

### 3.7 Create a User

1. Open **Accounts > Users**.
2. Select **Add User**.
3. Enter username, full name, employee ID, email, department, and role.
4. Set staff/superuser permissions only when required.
5. Set **Can Manage Stock Reports** only for users who should manage material reports and stock return actions.
6. Save.

### 3.8 Edit a User

1. Open **Accounts > Users**.
2. Search by username, full name, or email.
3. Update department, role, email, active status, or stock-report permission.
4. Save.

### 3.9 Reset a User Password

Use one of the following methods:

- Ask the user to use the password reset page.
- Use Django administration password tools if available for the account.
- If using a console email backend in a development environment, retrieve the reset link from server output.

### 3.10 Activate or Deactivate a User

1. Open the user in **Accounts > Users**.
2. Check or uncheck **Active**.
3. Save.

Inactive users cannot be selected by role-based approval resolution because the system looks for active users in the owning department.

---

## 4. Workflow Management

Workflow management is performed through **Workflows > Approval workflows** and **Workflows > Approval workflow steps** in `/admin/`.

### 4.1 Approval Workflows

An approval workflow defines which process applies to a request.

Workflow fields:

- **Name**
- **Request type**
- **Department**: optional. If blank, the workflow is a global fallback.
- **Minimum amount**
- **Maximum amount**
- **Active**

### 4.2 Approval Steps

Approval steps define who must act and in what order.

Step fields:

- **Workflow**
- **Step order**
- **Approver role**
- **Approver user**
- **Alternate approver user**
- **Required**

The system processes approval steps in ascending step order. Each workflow can have only one step for a given step order.

### 4.3 Assign Approvers

There are two approver assignment methods:

- **Specific approver user:** The step always goes to that user.
- **Approver role:** The system finds an active user in the request-owning department with that role.

An alternate approver can also be configured. The alternate can approve, reject, or return the same pending step.

> **Tip:** Use role-based assignment for department-specific workflows. Use specific users for exceptional global approvals.

### 4.4 Create a Workflow

1. Open `/admin/`.
2. Go to **Workflows > Approval workflows**.
3. Select **Add Approval workflow**.
4. Enter the workflow name.
5. Select the request type.
6. Select a department for a department-specific workflow, or leave department blank for a global fallback.
7. Configure minimum and maximum amount if needed.
8. Keep **Active** checked.
9. Add steps inline or save and add steps separately.

**Screenshot placeholder:** Approval workflow with inline steps.

### 4.5 Create Approval Steps

1. Open the workflow.
2. Add step order `1` for the first approver.
3. Select an approver role or specific approver user.
4. Add an alternate approver if required.
5. Add additional steps using step order `2`, `3`, and so on.
6. Save.

### 4.6 Configure Department Workflows

Department workflows apply when **Request For Department** matches the workflow department.

Example:

- Request type: Material Request
- Department: Fiber
- Step 1: Fiber Manager
- Step 2: Stock Manager

If Administration submits a Material Request for Fiber, this workflow is selected because the request is owned by Fiber.

### 4.7 Configure Amount-Based Workflows

Use minimum and maximum amount fields to define financial approval ranges.

Example:

- Payment Request, Finance, min blank, max `999.99`: Finance Manager.
- Payment Request, Finance, min `1000.00`, max blank: Finance Manager then Director.

For a request with an amount, the selected workflow must match the amount range.

### 4.8 Configure Fallback or Global Workflows

A global workflow has no department selected. It applies only when no department-specific workflow matches the request type, amount, and owning department.

Example:

- Request type: General Request
- Department: blank
- Step 1: Operations Manager

> **Warning:** A global fallback should not replace department-specific workflows where department ownership matters.

### 4.9 Example Workflows

**Example 1: Administration submits for Fiber**

1. Submitter department: Administration.
2. Request For Department: Fiber.
3. Request type: Material Request.
4. The system looks for an active Material Request workflow for Fiber.
5. Approver roles are resolved among active Fiber users.

**Example 2: Administration submits for IT**

1. Submitter department: Administration.
2. Request For Department: IT.
3. Request type: General Request.
4. The system looks for an active General Request workflow for IT.
5. If none exists, it looks for a global General Request workflow.

---

## 5. Request Types

Request types are managed in **Requests app > Request types**.

### 5.1 Request Type Fields

- **Name**
- **Code**
- **Description**
- **Active**
- **Is permission request**
- **Requires materials**
- **Requires amount**

### 5.2 Material Requests

Material request types should have **Requires materials** enabled. Users must select material items and quantities. After final approval, stock is deducted and stock movement records are created.

### 5.3 General Requests

General requests normally require a description. They do not require material items unless the request type is configured to require materials.

### 5.4 Payment Requests

Payment request types should usually enable **Requires amount** so the amount field becomes mandatory and amount-based workflows can route the request.

### 5.5 Leave and Permission Requests

Permission request types should enable **Is permission request**. This activates additional fields for leave permission and site authorization.

Permission groups include:

- Leave Permission
- Site Authorization

Leave permission can include permission type, destination, reason, departure time, return time, arrival time, and driver name. Site authorization can include site, validity dates, Microcom agents, TT, external persons, and reason.

> **Note:** Request type behavior is controlled by explicit flags, not by the display name.

---

## 6. Inventory & Materials

Inventory is managed through **Inventory > Material categories**, **Inventory > Materials**, and request material reports.

### 6.1 Material Catalog

Material categories organize materials. A material record includes:

- Category
- Name
- Code
- Description
- Unit
- Active status
- Stock quantity
- Minimum stock level

### 6.2 Material Stock

Stock quantity is stored on each material. The system validates request quantities against available stock during request entry.

When a material request is finally approved, the system deducts stock and records a stock movement of type **Stock Out**.

### 6.3 Add a Material

1. Open `/admin/`.
2. Go to **Inventory > Materials**.
3. Select **Add Material**.
4. Choose a category.
5. Enter name, code, unit, stock quantity, and minimum stock level.
6. Keep **Active** checked if the material should be available in requests.
7. Save.

### 6.4 Edit a Material

1. Open **Inventory > Materials**.
2. Search by material name or code.
3. Update the required fields.
4. Save.

### 6.5 Update Stock

Administrators can adjust stock quantity on the material record. For stock issued by an approved request, the application automatically creates stock movement records.

> **Tip:** For operational accuracy, document manual stock changes outside the request flow according to internal inventory procedures.

### 6.6 View Stock History

Stock movement records are available under **Requests app > Stock movements**. They show:

- Material
- Movement type
- Quantity
- Related request
- User who performed the action
- Date and time
- Notes

### 6.7 Material Reports

The material report screen is available at `/materials/reports/`. Users with stock-management access can filter, export, print material documents, update material issue notes, and return materials to stock when applicable.

**Screenshot placeholder:** Material report screen with filters and export buttons.

---

## 7. Department Ownership

Department ownership is central to Microcom workflow routing.

### 7.1 Submitted From Department

**Submitted From Department** is the submitter's own department. It identifies where the request originated.

### 7.2 Request For Department

**Request For Department** is the department that owns the request. It controls:

- Workflow selection.
- Role-based approver lookup.
- Department filtering in lists and reports.
- Printed and exported department ownership information.

By default, the request is assigned to the submitter's department. If a user submits on behalf of another department, the user must select the correct department.

### 7.3 Example: Administration Submits for Fiber

Administration creates a request and selects Fiber as **Request For Department**.

The system:

1. Stores Administration as the submitted-from department.
2. Stores Fiber as the request-owning department.
3. Looks for a matching Fiber workflow.
4. Resolves role-based approvers from active Fiber users.

### 7.4 Example: Administration Submits for IT

Administration creates a request and selects IT as **Request For Department**.

The system:

1. Records Administration as the submitting department.
2. Routes the request through the IT-specific workflow if one exists.
3. Uses the global fallback only if no matching IT workflow exists.

> **Warning:** Do not configure workflows based on the submitter department when the process depends on request ownership. Use **Request For Department**.

---

## 8. Draft Requests

### 8.1 What Drafts Are

A draft is a request saved by a user before submission. Drafts are useful when information is incomplete.

### 8.2 Draft Lifecycle

1. User creates a request.
2. User selects **Save as Draft**.
3. The request is stored with status **Draft**.
4. No approval steps are created.
5. The user edits the draft later.
6. The user submits the draft for approval.

### 8.3 Draft Visibility

Drafts appear in the submitter's request list. They are not part of pending approvals.

### 8.4 Draft Limitations

- Drafts are not sent to approvers.
- Drafts do not reserve material stock.
- Drafts do not deduct stock.
- Drafts can be cancelled by the submitter.

> **Warning:** A draft is not an active approval request.

---

## 9. Returned Requests

### 9.1 Returning Requests

An approver can return a pending request for correction. The request status becomes **Returned**, and the current approval path is no longer active.

### 9.2 Correction Process

The submitter can edit returned requests. Corrections may include description changes, amount changes, material item changes, or attachment changes.

### 9.3 Resubmission Process

When the corrected request is submitted again:

1. Existing approval records are cleared.
2. The request status returns to pending workflow processing.
3. The system selects the applicable workflow again.
4. New approval steps are created.

> **Note:** Because workflow selection runs again on resubmission, changes to request type, amount, or Request For Department can affect routing.

---

## 10. Request Cancellation

### 10.1 When Cancellation Is Allowed

The submitter can cancel requests in these statuses:

- Draft
- Returned
- Pending
- In Review

### 10.2 When Cancellation Is Blocked

Cancellation is blocked after final decisions such as:

- Approved
- Rejected
- Already cancelled

### 10.3 Effects on Approvals

When a request is cancelled:

- Request status becomes **Cancelled**.
- Current approval processing stops.
- The action is recorded in the request audit log.
- Approvers cannot complete approval actions on that request.

> **Warning:** Cancellation does not replace the returned-request correction process. Use return when the request should be corrected and resubmitted.

---

## 11. Reporting

### 11.1 Material Reports

Material reports are available at `/materials/reports/`.

They include approved material requests and display:

- Request number.
- Submitted-from department.
- Request For Department.
- Request type.
- Material items.
- Quantities.
- Issue notes.
- Stock status and return information.

### 11.2 Request Reports and Lists

Operational request tracking is available through:

- **My Requests** at `/requests/`.
- **Pending Approvals** at `/approvals/pending/`.
- **Approval History** at `/approvals/history/`.

### 11.3 Department Filtering

Department filters use **Request For Department**. This keeps reports aligned with request ownership rather than submitter origin.

### 11.4 CSV Export

The CSV export is available from the material report screen. Active filters are preserved in the export URL.

### 11.5 Excel Export

The Excel export is available from the material report screen. It includes localized labels and uses the active report filters.

### 11.6 Print Documents

The system supports:

- **Material Exit Slip** for approved material requests.
- **Permission document** for permission/leave requests.
- Bulk print of material documents from the material report screen.

**Screenshot placeholder:** Material Exit Slip print preview.

---

## 12. System Administration

### 12.1 Environment Variables

The application uses environment variables for settings such as:

- `SECRET_KEY`
- `DEBUG`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`
- `SHOW_DRC_MATCH_BANNER`

### 12.2 Banner Flags

`SHOW_DRC_MATCH_BANNER` controls the dashboard match banner. Set it according to operational communication needs.

### 12.3 Language Support

The system supports English and French. The language switcher uses Django internationalization with the `django_language` cookie.

Supported languages:

- English (`en`)
- French (`fr`)

### 12.4 Static Files

Static files are served through Django static configuration and WhiteNoise. Production deployments should collect static files into `STATIC_ROOT`.

### 12.5 Session Security

The system is configured with a session age and browser-close expiration. Review cookie security settings before production deployment over HTTPS.

---

## 13. Troubleshooting

### 13.1 User Cannot Login

Check:

- User is active.
- Username is correct.
- Password is correct.
- User is using the correct login URL.
- Browser session is not expired.

### 13.2 Password Reset Issues

Check:

- User email exists and is correct.
- Email backend settings are configured.
- Reset link domain and protocol are correct for the deployment.
- Mail server accepts the configured sender.

### 13.3 Request Stuck in Approval

Check:

- Request status.
- Current step order.
- Pending approval record.
- Approver user and alternate approver.
- Whether the assigned approver is active.
- Whether a required next step has an approver.

### 13.4 Wrong Approver Assigned

Check:

- Request For Department.
- Workflow selected for the request type and department.
- Amount range on the workflow.
- Step configuration.
- User role in the owning department.
- Whether a specific approver user overrides role-based lookup.

### 13.5 Material Stock Mismatch

Check:

- Material stock quantity.
- Stock movement records.
- Whether the request is approved.
- Whether stock was already deducted.
- Return-to-stock records and return reasons.

### 13.6 Export Not Working

Check:

- User permission to manage stock reports.
- Report filters.
- Browser download restrictions.
- Server logs for export errors.

### 13.7 No Applicable Workflow Found

Check:

- Request type has an active workflow.
- Department-specific workflow exists for Request For Department.
- A global fallback exists if department-specific routing is not configured.
- Amount ranges include the request amount.
- Workflow is active.

---

## 14. Best Practices

- Keep department-specific workflows for department-owned processes.
- Maintain at least one global fallback per common request type where appropriate.
- Use explicit request type flags instead of relying on names.
- Keep one active primary approver per department/role combination used by role-based workflow steps.
- Configure alternate approvers for critical approval steps.
- Review material stock quantities and minimum stock levels regularly.
- Deactivate users instead of deleting historical actors.
- Test workflow routing after changing departments, roles, request types, or amount ranges.
- Use returned requests for corrections and cancellation for requests that should stop.
- Keep screenshot documentation updated after UI changes.


## Administration Report
Selected employees can use **Administration Report** to search, view and print fully approved General Requests addressed to Administration, including requests submitted by other departments. In Django Admin > Accounts > Users, enable **Can view administration reports** (`can_view_administration_reports`) for each authorized employee. This follows Stock Report's user-flag mechanism; group permissions do not grant this flag. Superusers also have access.

Search by request number, requester names/username or description. Filter by submitting department, requester and submission date range; filters survive pagination. The destination remains Administration. Open **View Document** or **Print**, then use the existing document's print/save-as-PDF button and one/two-copy controls.

Access covers only the report and its approved documents. It does not grant request-detail, editing or approval rights. Drafts and all other unapproved statuses, materials, permission requests and other types are excluded. Dates of approval use existing `finalized_at` when available.

Deployment: apply accounts migration `0003_user_can_view_administration_reports`. Confirm the existing department/type codes and set `ADMINISTRATION_REPORT_DEPARTMENT_CODE` (default `ADMIN`) and `ADMINISTRATION_REPORT_REQUEST_TYPE_CODE` (default `AUTORISATION_GENERAL`) in the environment. These exact codes determine report and document scope; missing codes produce an empty report. No department-name guessing or data changes occur.
