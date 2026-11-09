
"""Workflow notification state, separate from approval decisions and email delivery."""

from django.db.models import Q, F
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Request, RequestApproval, WorkflowNotification


def actionable_approvals(user):
    return RequestApproval.objects.filter(
        Q(approver_user_id=user.pk) | Q(alternate_approver_user_id=user.pk),
        status="PENDING",
        request__current_step_order=F("step_order"),
        request__status__in=["PENDING", "IN_REVIEW"],
    )


def active_notifications(user):
    """Only notifications for approval actions still awaiting this user."""
    if not user.is_authenticated or not user.is_active:
        return WorkflowNotification.objects.none()

    return WorkflowNotification.objects.filter(
        recipient=user,
        actionable=True,
        approval__status="PENDING",
        request__status__in=["PENDING", "IN_REVIEW"],
        request__current_step_order=F("approval__step_order"),
    ).filter(
        Q(approval__approver_user_id=user.pk)
        | Q(approval__alternate_approver_user_id=user.pk)
    )


def counts(user):
    if not user.is_authenticated or not user.is_active:
        return {"pending": 0, "returned": 0, "unread": 0}

    active = active_notifications(user)

    return {
        "pending": actionable_approvals(user).count(),
        "returned": Request.objects.filter(
            submitted_by=user,
            status="RETURNED",
        ).count(),
        "unread": active.filter(read_at__isnull=True).count(),
    }


def record_event(event):
    """Called inside the existing event transaction. No historical backfill."""
    request = event.request

    if event.action in {
        "APPROVED_STEP",
        "FINAL_APPROVED",
        "REJECTED",
        "RETURNED",
        "CANCELLED",
    }:
        WorkflowNotification.objects.filter(
            request=request,
            actionable=True,
        ).update(
            actionable=False,
            resolved_at=timezone.now(),
        )

    if event.action in {"SUBMITTED", "RESUBMITTED"}:
        notify_current(request, event.action)

    elif event.action in {"FINAL_APPROVED", "REJECTED", "RETURNED"}:
        WorkflowNotification.objects.get_or_create(
            event_key=f"audit:{event.pk}:{request.submitted_by_id}",
            defaults={
                "recipient_id": request.submitted_by_id,
                "request": request,
                "event_type": event.action,
                "reference": request.request_number,
            },
        )


def notify_current(request, event_type):
    approval = request.approvals.filter(
        status="PENDING",
        step_order=request.current_step_order,
    ).first()

    if not approval:
        return

    recipients = {
        approval.approver_user_id,
        approval.alternate_approver_user_id,
    } - {None}

    for recipient in recipients:
        WorkflowNotification.objects.get_or_create(
            event_key=f"approval:{approval.pk}:{recipient}",
            defaults={
                "recipient_id": recipient,
                "request": request,
                "approval": approval,
                "event_type": event_type,
                "reference": request.request_number,
                "actionable": True,
            },
        )


def presentation(notice):
    current = bool(
        notice.actionable
        and notice.approval_id
        and notice.approval.status == "PENDING"
        and notice.request.status in {"PENDING", "IN_REVIEW"}
        and notice.request.current_step_order == notice.approval.step_order
        and notice.recipient_id in {
            notice.approval.approver_user_id,
            notice.approval.alternate_approver_user_id,
        }
    )

    title = {
        "SUBMITTED": _("Request awaiting your approval"),
        "RESUBMITTED": _("Request awaiting your approval"),
        "APPROVED_STEP": _("Request awaiting your approval"),
    }.get(notice.event_type, _("Request update"))

    return {
        "notice": notice,
        "title": title,
        "actionable": current,
        "state": _("Awaiting your decision") if current else _("Already handled"),
    }


def inbox_rows(user, *, unread=False):
    """Return only outstanding approval notifications."""
    rows = active_notifications(user).select_related(
        "request",
        "approval",
    )

    return rows.filter(read_at__isnull=True) if unread else rows
