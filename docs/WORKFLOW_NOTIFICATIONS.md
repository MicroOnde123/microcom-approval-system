# Workflow notifications and optional email preferences

## Existing and preserved behavior

Primary and alternate approvers share one approval row. Existing parent-request and
approval row locks serialize actions. A second action fails existing validation;
no workflow routing, stock deduction, invoice or return calculations were changed.
Workflow email uses Django's configured backend synchronously after commit; no queue
or external notification service is introduced. Essential password-reset/account
email paths remain outside the optional workflow delivery helper.

## Persistence and delivery

accounts.0004 adds receive_email_notifications, default True for existing and new
users, including a database default for older clients during schema/code cutover.
The existing User Admin ModelForm exposes the translated checkbox without
additional Admin privileges. requests_app.0021 creates WorkflowNotification.
Unique event keys identify each approval/recipient and terminal audit-event/recipient.
Notifications are recorded in the workflow transaction. Approval rows removed on
resubmission null their notification FK; request reference and event history remain.
No historical events or pending approvals are silently backfilled.

Current recipient email addresses, active status and preference are read at optional
email delivery time using stable user IDs. Bulk recipients are filtered individually.
Suppression is not an error. Shared email addresses are deduplicated; an opted-in
account using the same mailbox can still cause mail to reach that mailbox.
The existing fail-silently backend behavior remains; this is not a durable email
outbox or automatic retry implementation.

## Interface and access

/notifications/ is an authenticated, active-user inbox, paginated by 25.
/notifications/live/ returns counts and at most 10 recent notifications.
/notifications/<id>/read/ accepts CSRF-protected POSTs scoped to the recipient.
View Request checks current request-view permissions before marking that notification
read and redirecting to a fixed internal request-detail route. Other read actions
change only that notice. Opening the dropdown never changes read state.

Unread and actionable counts are separate. Handling a shared step resolves its
notifications inside the existing transaction; read timestamps do not change.
Presentation additionally checks current approval ownership, request status and step,
so cancellation, reassignment or deleted approval rows cannot advertise an action.
Initial badges and the legacy count endpoint share the same open-step predicate.

## Live updates and performance

One nonoverlapping five-second timer runs per visible browser tab. It pauses while
hidden and refreshes on visibility restoration. Polling is authenticated and uncached.
Recent payload and query counts are bounded independently of inbox length. Pending
approval rendering is paginated to 25, selects requester data in one query and retains
existing search/date/type/department filtering. The shared live-filter region updates
without full-page navigation and avoids aborting an in-flight results refresh.
Automatic result replacement waits for typing debounce and in-flight filtering;
filter controls and entered values are not replaced.
A stale open approval form is disabled when the server reports that its action is no
longer available. Existing service checks remain authoritative even if polling fails.
Dropdown controls retain focus; their subtree replacement waits while it is focused,
but shared-step status labels still update in place.
Read actions immediately update their own visual state.

Polling is eventual presentation synchronization, not instantaneous server push.
Deployment sizing should account for multiple visible browser tabs and the existing
approval-filter query cost. Browser/mobile/screen-reader acceptance remains necessary.

## Deployment and recovery

Migrations were tested only in disposable loopback PostgreSQL databases using
config.test_material_entries_settings. Neither Supabase nor production was accessed.
Before any later approved deployment, back up the target database and coordinate
schema migration with new-code activation: code reads the new User column and notice
table. Run normal migration checks and ship compiled French catalogs and static files.
Existing users remain opted in. Existing pending requests retain their actionable
badges but have no inbox event until subsequent workflow activity.

Prefer a forward fix. Reversing requests_app.0021 drops notification history and read
state; reversing accounts.0004 loses preferences. Preserve/export these records before
any explicitly approved reversal. No rollback/deployment commands were executed.
