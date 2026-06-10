from django.db import models
from .models import Request, RequestApproval


def is_stock_manager(user):
    return (
        user.is_superuser
        or getattr(user, "can_manage_stock", False)
    )


def pending_approval_count(request):
    if not request.user.is_authenticated:
        return {
            "pending_approval_count": 0,
            "returned_requests_count": 0,
            "can_manage_stock": False,
        }

    pending_count = RequestApproval.objects.filter(
        models.Q(approver_user=request.user)
        | models.Q(alternate_approver_user=request.user),
        status="PENDING",
        request__current_step_order=models.F("step_order"),
    ).count()

    returned_count = Request.objects.filter(
        submitted_by=request.user,
        status="RETURNED",
    ).count()

    return {
        "pending_approval_count": pending_count,
        "returned_requests_count": returned_count,
        "can_manage_stock": is_stock_manager(request.user),
    }
