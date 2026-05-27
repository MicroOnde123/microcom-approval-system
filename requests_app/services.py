from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from workflows.models import ApprovalWorkflow
from requests_app.models import RequestApproval, RequestAuditLog, StockMovement


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

    if request.department:
        workflows = workflows.filter(department=request.department) | workflows.filter(department__isnull=True)

    if request.amount is not None:
        workflows = workflows.filter(min_amount__lte=request.amount) | workflows.filter(min_amount__isnull=True)
        workflows = workflows.filter(max_amount__gte=request.amount) | workflows.filter(max_amount__isnull=True)

    workflow = workflows.order_by("department", "min_amount").first()

    if not workflow:
        raise ValidationError("No applicable workflow found for this request.")

    return workflow


def create_approval_steps(request, workflow):
    if request.approvals.exists():
        raise ValidationError("Approval steps already exist for this request.")

    approvals = []

    for step in workflow.steps.all().order_by("step_order"):
        approver = step.approver_user

        if not approver and step.approver_role:
            if not request.department:
                raise ValidationError("Request has no department assigned.")

            approver = request.department.user_set.filter(
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
        )

        approvals.append(approval)

    request.current_step_order = approvals[0].step_order if approvals else None
    request.status = "IN_REVIEW"
    request.save()

    return approvals


def submit_request(request):
    if request.approvals.exists():
        raise ValidationError("This request has already been submitted into a workflow.")

    workflow = get_applicable_workflow(request)
    approvals = create_approval_steps(request, workflow)

    first_step = approvals[0] if approvals else None
    if first_step and first_step.approver_user and first_step.approver_user.email:
        send_notification_email(
            subject="New Request Awaiting Your Approval",
            message=f"Request {request.request_number} requires your approval.",
            recipients=[first_step.approver_user.email],
        )

    log_action(request, "SUBMITTED", request.submitted_by)

    return approvals


def deduct_material_stock(request, user=None):
    if request.stock_deducted:
        return

    if not request.request_type or not request.request_type.requires_materials:
        return

    material_items = request.material_items.select_related("material").all()

    for item in material_items:
        material = item.material

        if item.quantity > material.stock_quantity:
            raise ValidationError(
                f"Insufficient stock for {material.name}. "
                f"Available: {material.stock_quantity} {material.unit}, "
                f"requested: {item.quantity} {material.unit}."
            )

    for item in material_items:
        material = item.material
        material.stock_quantity -= item.quantity
        material.save(update_fields=["stock_quantity"])

        StockMovement.objects.create(
            material=material,
            request=request,
            quantity=item.quantity,
            movement_type="OUT",
            performed_by=user,
            note=f"Stock deducted after approval of request {request.request_number}.",
        )

    request.stock_deducted = True
    request.save(update_fields=["stock_deducted"])


@transaction.atomic
def approve_step(approval, user, comment=""):
    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if approval.approver_user != user:
        raise ValidationError("You are not allowed to approve this step.")

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for approval.")

    if request.current_step_order != approval.step_order:
        raise ValidationError("This is not the current approval step.")

    approval.status = "APPROVED"
    approval.comment = comment
    approval.acted_at = timezone.now()
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

        if next_step.approver_user and next_step.approver_user.email:
            send_notification_email(
                subject="Request Awaiting Your Approval",
                message=f"Request {request.request_number} is now awaiting your approval.",
                recipients=[next_step.approver_user.email],
            )

        return

    deduct_material_stock(request)

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
    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if approval.approver_user != user:
        raise ValidationError("You are not allowed to reject this step.")

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for rejection.")

    if request.current_step_order != approval.step_order:
        raise ValidationError("This is not the current approval step.")

    approval.status = "REJECTED"
    approval.comment = comment
    approval.acted_at = timezone.now()
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
    if approval.status != "PENDING":
        raise ValidationError("This step has already been acted upon.")

    if approval.approver_user != user:
        raise ValidationError("You are not allowed to return this step.")

    request = approval.request

    if request.status not in ["IN_REVIEW", "PENDING"]:
        raise ValidationError("This request is no longer open for return.")

    if request.current_step_order != approval.step_order:
        raise ValidationError("This is not the current approval step.")

    approval.status = "RETURNED"
    approval.comment = comment
    approval.acted_at = timezone.now()
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
    if request_obj.status != "RETURNED":
        raise ValidationError("Only returned requests can be resubmitted.")

    request_obj.approvals.all().delete()
    request_obj.status = "PENDING"
    request_obj.current_step_order = None
    request_obj.finalized_at = None
    request_obj.save()

    submit_request(request_obj)

    log_action(request_obj, "RESUBMITTED", user, "Request corrected and resubmitted.")