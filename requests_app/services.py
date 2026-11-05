import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from workflows.models import ApprovalWorkflow, validate_stock_review_steps
from requests_app.models import Request, RequestApproval, RequestAuditLog
from .stock_services import deduct_material_stock, validate_material_quantities
from .resubmission import BASELINE_ACTION, is_general_permission, record_baseline, resume_decision


def send_notification_email(subject, message, recipients):
    if not recipients:
        return

    recipients = tuple(recipients)
    # Retain recipients/content, but never send mail for a rolled-back decision.
    transaction.on_commit(lambda: send_mail(subject, message, None, list(recipients), fail_silently=True), robust=True)


def log_action(request, action, user=None, comment=""):
    RequestAuditLog.objects.create(
        request=request,
        action=action,
        performed_by=user,
        comment=comment,
    )


def get_applicable_workflow(request):
    workflows = ApprovalWorkflow.objects.filter(
        request_type=request.request_type,
        is_active=True,
    )

    if request.amount is not None:
        workflows = workflows.filter(min_amount__lte=request.amount) | workflows.filter(min_amount__isnull=True)
        workflows = workflows.filter(max_amount__gte=request.amount) | workflows.filter(max_amount__isnull=True)

    workflow = None
    if request.request_for_department:
        workflow = workflows.filter(
            department=request.request_for_department
        ).order_by("min_amount").first()

    if not workflow:
        workflow = workflows.filter(
            department__isnull=True
        ).order_by("min_amount").first()

    if not workflow:
        raise ValidationError(_("No applicable workflow found for this request."))

    return workflow


def configured_approval_steps(request, workflow):
    """Validate the complete replacement before archiving/deleting any rows."""
    steps = list(workflow.steps.all().order_by("step_order"))
    if not steps:
        raise ValidationError(_("No approval steps are configured. Ask an administrator to configure the approval workflow."))
    validate_stock_review_steps(steps)
    for step in steps:
        if step.is_stock_review:
            step.clean()
    configured = []
    permission_request = is_general_permission(request)

    for step in steps:
        approver = step.approver_user

        if not approver and step.approver_role:
            if not request.request_for_department:
                raise ValidationError(_("Request has no owning department assigned."))

            approver = request.request_for_department.user_set.filter(
                role=step.approver_role,
                is_active=True,
            ).first()

        if not approver:
            raise ValidationError(_("No approver found for step %(step)s.") % {"step": step.step_order})
        if permission_request and (not approver.is_active or step.alternate_approver_user and not step.alternate_approver_user.is_active):
            raise ValidationError(_("Approval assignments must use active users."))
        if not approver.is_active:
            raise ValidationError(_("Approval assignments must use active users."))
        configured.append((step, approver))
    return configured


def create_approval_steps(request, workflow):
    if request.approvals.exists():
        raise ValidationError(_("Approval steps already exist for this request."))
    configured = configured_approval_steps(request, workflow)
    approvals = []
    for step, approver in configured:

        approval = RequestApproval.objects.create(
            request=request,
            workflow_step=step,
            step_order=step.step_order,
            approver_user=approver,
            alternate_approver_user=step.alternate_approver_user,
            requires_stock_classification=step.is_stock_review,
        )

        approvals.append(approval)

    request.current_step_order = approvals[0].step_order if approvals else None
    request.status = "IN_REVIEW"
    request.save()

    return approvals


def lock_permission_workflow(request, workflow):
    if is_general_permission(request):
        workflow = ApprovalWorkflow.objects.select_for_update().get(pk=workflow.pk)
        if not workflow.is_active:
            raise ValidationError(_("No applicable workflow found for this request."))
        # Serialize configured step edits with evidence comparison and recreation.
        list(workflow.steps.select_for_update().order_by("step_order"))
    return workflow


@transaction.atomic
def submit_request(request, *, notifications_on_commit=False):
    locked = Request.objects.select_for_update().get(pk=request.pk)
    if locked.status not in ("DRAFT", "PENDING", "RETURNED"):
        raise ValidationError(_("This request is no longer available for submission."))
    validate_material_quantities(request)
    if request.approvals.exists():
        raise ValidationError(_("This request has already been submitted into a workflow."))

    workflow = lock_permission_workflow(request, get_applicable_workflow(request))
    approvals = create_approval_steps(request, workflow)
    record_baseline(request, workflow)

    first_step = approvals[0] if approvals else None
    
    if first_step:
        recipients = []

        if first_step.approver_user and first_step.approver_user.email:
            recipients.append(first_step.approver_user.email)

        if first_step.alternate_approver_user and first_step.alternate_approver_user.email:
            recipients.append(first_step.alternate_approver_user.email)

        def notify():
            send_notification_email(
                subject="New Request Awaiting Your Approval",
                message=f"Request {request.request_number} requires your approval.",
                recipients=recipients,
            )
        if notifications_on_commit:
            transaction.on_commit(notify, robust=True)
        else:
            notify()

    log_action(request, "SUBMITTED", request.submitted_by)

    return approvals


def locked_approval(approval, user):
    if not user.is_authenticated or not user.is_active or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists():
        raise ValidationError(_("An active authenticated user is required."))
    # All lifecycle transitions acquire the parent before its approval rows.
    request = Request.objects.select_for_update().get(pk=approval.request_id)
    try:
        current = RequestApproval.objects.select_for_update().get(pk=approval.pk, request=request)
    except RequestApproval.DoesNotExist:
        raise ValidationError(_("This approval is no longer active. Reload the request."))
    current.request = request
    return current


@transaction.atomic
def approve_step(approval, user, comment="", *, classification=None, succursale=None):
    approval = locked_approval(approval, user)

    if approval.status != "PENDING":
        raise ValidationError(_("This step has already been acted upon."))

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError(_("You are not allowed to approve this step."))

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError(_("This request is no longer open for approval."))

    if request.current_step_order != approval.step_order:
        raise ValidationError(_("This is not the current approval step."))

    if request.approvals.filter(step_order__lt=approval.step_order).exclude(
        status__in=["APPROVED", "SKIPPED"],
    ).exists():
        raise ValidationError(_("All preceding approval steps must be completed first."))

    reviews = list(request.approvals.filter(requires_stock_classification=True))
    if reviews:
        if len(reviews) != 1:
            raise ValidationError(_("Only one stock-review step may be designated per workflow."))
        review = reviews[0]
        if approval.step_order > review.step_order and (
            review.status != "APPROVED"
            or request.classification not in request.Classification.values
        ):
            raise ValidationError(_("The designated stock review must be approved before later approval steps."))

    if approval.requires_stock_classification:
        from .classification import confirm_classification
        confirm_classification(request, user, classification, succursale)
    elif classification is not None or succursale is not None:
        raise ValidationError(_("Only the designated stock reviewer can classify this request."))

    approval.status = "APPROVED"
    approval.comment = comment
    approval.acted_at = timezone.now()
    approval.acted_by = user
    approval.save()

    log_action(request, "APPROVED_STEP", user, comment)

    next_step = request.approvals.filter(
        step_order__gt=approval.step_order,
        status="PENDING",
    ).order_by("step_order").first()

    if next_step:
        request.current_step_order = next_step.step_order
        request.status = "IN_REVIEW"
        request.save()

        recipients = []

        if next_step.approver_user and next_step.approver_user.email:
            recipients.append(next_step.approver_user.email)

        if next_step.alternate_approver_user and next_step.alternate_approver_user.email:
            recipients.append(next_step.alternate_approver_user.email)

        send_notification_email(
            subject="Request Awaiting Your Approval",
            message=f"Request {request.request_number} is now awaiting your approval.",
            recipients=recipients,
        )
        return

    deduct_material_stock(request, user=user)

    request.status = "APPROVED"
    request.finalized_at = timezone.now()
    request.current_step_order = None
    request.save()

    log_action(request, "FINAL_APPROVED", user, comment)

    if request.submitted_by and request.submitted_by.email:
        send_notification_email(
            subject="Request Approved",
            message=f"Your request {request.request_number} has been approved.",
            recipients=[request.submitted_by.email],
        )


@transaction.atomic
def reject_step(approval, user, comment=""):
    approval = locked_approval(approval, user)

    if approval.status != "PENDING":
        raise ValidationError(_("This step has already been acted upon."))

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError(_("You are not allowed to reject this step."))

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError(_("This request is no longer open for rejection."))

    if request.current_step_order != approval.step_order:
        raise ValidationError(_("This is not the current approval step."))

    approval.status = "REJECTED"
    approval.comment = comment
    approval.acted_at = timezone.now()
    approval.acted_by = user
    approval.save()

    request.status = "REJECTED"
    request.current_step_order = None
    request.finalized_at = timezone.now()
    request.save()

    log_action(request, "REJECTED", user, comment)

    if request.submitted_by and request.submitted_by.email:
        send_notification_email(
            subject="Request Rejected",
            message=f"Your request {request.request_number} has been rejected.",
            recipients=[request.submitted_by.email],
        )


@transaction.atomic
def return_step(approval, user, comment=""):
    approval = locked_approval(approval, user)

    if approval.status != "PENDING":
        raise ValidationError(_("This step has already been acted upon."))

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError(_("You are not allowed to return this step."))

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError(_("This request is no longer open for return."))

    if request.current_step_order != approval.step_order:
        raise ValidationError(_("This is not the current approval step."))

    approval.status = "RETURNED"
    approval.comment = comment
    approval.acted_at = timezone.now()
    approval.acted_by = user
    approval.save()

    request.status = "RETURNED"
    request.current_step_order = None
    request.save()

    log_action(request, "RETURNED", user, comment)

    if request.submitted_by and request.submitted_by.email:
        send_notification_email(
            subject="Request Returned for Correction",
            message=f"Your request {request.request_number} was returned for correction.",
            recipients=[request.submitted_by.email],
        )


@transaction.atomic
def resubmit_request(request_obj, user):
    request_obj = Request.objects.select_for_update().get(pk=request_obj.pk)
    if (not user.is_authenticated or not user.is_active or not get_user_model().objects.filter(pk=user.pk, is_active=True).exists()
            or request_obj.submitted_by_id != user.pk):
        raise ValidationError(_("Only the active request owner can resubmit this request."))
    if request_obj.status != "RETURNED":
        raise ValidationError(_("Only returned requests can be resubmitted."))

    permission_attempt = is_general_permission(request_obj) or request_obj.audit_logs.filter(action=BASELINE_ACTION).exists()
    workflow = lock_permission_workflow(request_obj, get_applicable_workflow(request_obj)) if permission_attempt else None
    target, reason = resume_decision(request_obj, workflow) if permission_attempt else (None, None)
    if not target:
        workflow = workflow or get_applicable_workflow(request_obj)
        configured_approval_steps(request_obj, workflow)

    # Preserve complete prior approval evidence without changing the active
    # relation used by existing queues, permissions and invoice guards.
    previous_approvals = list(request_obj.approvals.order_by("step_order", "pk").values())
    if previous_approvals:
        person_ids = {row[key] for row in previous_approvals for key in
                      ("approver_user_id", "alternate_approver_user_id", "acted_by_id") if row[key]}
        people = {str(person.pk): person.full_name or person.username
                  for person in get_user_model().objects.filter(pk__in=person_ids)}
        log_action(
            request_obj, "APPROVAL_HISTORY_ARCHIVED", user,
            json.dumps({"version": 1, "approvals": previous_approvals, "people": people,
                        "routing": {"reason": reason, "resumed_step": target.step_order if target else None}},
                       default=str, ensure_ascii=False),
        )
    if target:
        # Keep prior decisions untouched; new IDs invalidate all old pending URLs.
        pending = list(request_obj.approvals.filter(step_order__gte=target.step_order).order_by("step_order"))
        request_obj.approvals.filter(step_order__gte=target.step_order).delete()
        for previous in pending:
            RequestApproval.objects.create(request=request_obj, workflow_step_id=previous.workflow_step_id,
                step_order=previous.step_order, approver_user_id=previous.approver_user_id,
                alternate_approver_user_id=previous.alternate_approver_user_id,
                requires_stock_classification=previous.requires_stock_classification)
        request_obj.status = "IN_REVIEW"
        request_obj.current_step_order = target.step_order
        request_obj.finalized_at = None
        request_obj.save()
        record_baseline(request_obj, workflow)
        recipients = [actor.email for actor in (target.approver_user, target.alternate_approver_user) if actor and actor.email]
        send_notification_email("New Request Awaiting Your Approval",
                                f"Request {request_obj.request_number} requires your approval.", recipients)
        log_action(request_obj, "RESUBMITTED", user,
                   json.dumps({"version": 1, "reason": reason, "resumed_step": target.step_order}))
        return {"resumed": True, "reason": reason, "step": target.step_order}

    request_obj.approvals.all().delete()
    request_obj.status = "PENDING"
    request_obj.current_step_order = None
    request_obj.finalized_at = None
    request_obj.save()

    submit_request(request_obj, notifications_on_commit=True)

    comment = json.dumps({"version": 1, "reason": reason, "resumed_step": None}) if reason else "Request corrected and resubmitted."
    log_action(request_obj, "RESUBMITTED", user, comment)
    return {"resumed": False, "reason": reason, "step": request_obj.current_step_order}
