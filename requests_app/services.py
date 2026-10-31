import json

from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from workflows.models import ApprovalWorkflow, validate_stock_review_steps
from requests_app.models import Request, RequestApproval, RequestAuditLog
from .stock_services import deduct_material_stock, validate_material_quantities


def send_notification_email(subject, message, recipients):
    if not recipients:
        return

    send_mail(
        subject,
        message,
        None,
        recipients,
        fail_silently=True,
    )


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
        raise ValidationError("No applicable workflow found for this request.")

    return workflow


def create_approval_steps(request, workflow):
    if request.approvals.exists():
        raise ValidationError("Approval steps already exist for this request.")

    steps = list(workflow.steps.all().order_by("step_order"))
    validate_stock_review_steps(steps)
    for step in steps:
        if step.is_stock_review:
            step.clean()
    approvals = []

    for step in steps:
        approver = step.approver_user

        if not approver and step.approver_role:
            if not request.request_for_department:
                raise ValidationError("Request has no owning department assigned.")

            approver = request.request_for_department.user_set.filter(
                role=step.approver_role,
                is_active=True,
            ).first()

        if not approver:
            raise ValidationError(f"No approver found for step {step.step_order}")

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


def submit_request(request, *, notifications_on_commit=False):
    validate_material_quantities(request)
    if request.approvals.exists():
        raise ValidationError("This request has already been submitted into a workflow.")

    workflow = get_applicable_workflow(request)
    approvals = create_approval_steps(request, workflow)

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


@transaction.atomic
def approve_step(approval, user, comment="", *, classification=None, succursale=None):
    approval = RequestApproval.objects.select_for_update().select_related(
        "request",
    ).get(pk=approval.pk)

    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError(_("You are not allowed to approve this step."))

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for approval.")

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
    approval = RequestApproval.objects.select_for_update().select_related(
        "request",
    ).get(pk=approval.pk)

    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError("You are not allowed to reject this step.")

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for rejection.")

    if request.current_step_order != approval.step_order:
        raise ValidationError("This is not the current approval step.")

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
    approval = RequestApproval.objects.select_for_update().select_related(
        "request",
    ).get(pk=approval.pk)

    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if user.id not in [approval.approver_user_id, approval.alternate_approver_user_id]:
        raise ValidationError("You are not allowed to return this step.")

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for return.")

    if request.current_step_order != approval.step_order:
        raise ValidationError("This is not the current approval step.")

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
    if request_obj.status != "RETURNED":
        raise ValidationError("Only returned requests can be resubmitted.")

    # Preserve complete prior approval evidence without changing the active
    # relation used by existing queues, permissions and invoice guards.
    previous_approvals = list(request_obj.approvals.order_by("step_order", "pk").values())
    if previous_approvals:
        log_action(
            request_obj, "APPROVAL_HISTORY_ARCHIVED", user,
            json.dumps({"version": 1, "approvals": previous_approvals},
                       default=str, ensure_ascii=False),
        )
    request_obj.approvals.all().delete()
    request_obj.status = "PENDING"
    request_obj.current_step_order = None
    request_obj.finalized_at = None
    request_obj.save()

    submit_request(request_obj)

    log_action(request_obj, "RESUBMITTED", user, "Request corrected and resubmitted.")
