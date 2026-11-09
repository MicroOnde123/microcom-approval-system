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
            "can_view_administration_reports": False,
        }

    from .notifications import counts
    current = counts(request.user)
    pending_count = current["pending"]
    returned_count = current["returned"]

    return {
        "pending_approval_count": pending_count,
        "notification_unread_count": current["unread"],
        "returned_requests_count": returned_count,
        "can_manage_stock": is_stock_manager(request.user),
        "can_view_administration_reports": request.user.is_superuser or request.user.can_view_administration_reports,
    }
