"""Explicit action permissions plus request-level stock-review assignment scope."""
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import gettext as _

from requests_app.models import Request


def require_permission(user, action):
    if not (user.is_authenticated and user.is_active and user.has_perm("invoicing.view_invoice")
            and user.has_perm("invoicing." + action)):
        raise PermissionDenied(_("You do not have permission to perform this invoice action."))


def request_scope(user):
    if not user.is_authenticated or not user.is_active:
        return Request.objects.none()
    if user.is_authenticated and user.is_active and (
            user.is_superuser or (user.is_staff and user.has_perm("invoicing.manage_all_invoices"))):
        return Request.objects.all()
    return Request.objects.filter(Q(approvals__requires_stock_classification=True) & (
        Q(approvals__approver_user_id=user.pk) | Q(approvals__alternate_approver_user_id=user.pk) |
        Q(approvals__acted_by_id=user.pk))).distinct()


def authorize(user, action, request_id):
    require_permission(user, action)
    if not request_scope(user).filter(pk=request_id).exists():
        raise PermissionDenied(_("This invoice is outside your stock-review assignments."))


def authorize_return_note(user, request_id, *, issue=False, preview=False, document=False):
    """Fresh permissions, dedicated actions, existing stock-review object scope."""
    from django.contrib.auth import get_user_model

    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied(_("You do not have permission to perform this material return note action."))
    actor = get_user_model().objects.filter(pk=user.pk).first()
    permissions = ["view_invoice", "view_materialreturnnote"]
    if issue or preview:
        permissions.append("issue_materialreturnnote")
    if issue:
        permissions.append("add_materialreturnnote")
    if document:
        permissions.append("view_materialreturnnote_document")
    if not (
        actor
        and actor.is_active
        and all(
            actor.has_perm("invoicing." + action)
            for action in permissions
        )
    ):
        raise PermissionDenied(_("You do not have permission to perform this material return note action."))
    if not request_scope(actor).filter(pk=request_id).exists():
        raise PermissionDenied(_("This material return note is outside your stock-review assignments."))
    return actor
