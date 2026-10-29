"""Default-off E-R3 boundary and permission-aware optional navigation."""
from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import Http404

from .models import Invoice
from .permissions import authorize_return_note


def ui_enabled():
    return getattr(settings, "MATERIAL_RETURN_NOTE_UI_ENABLED", False) is True


def require_ui():
    if not ui_enabled():
        raise Http404


def gated(view):
    @wraps(view)
    def call(*args, **kwargs):
        require_ui()
        return view(*args, **kwargs)
    return call


def navigation(user, *, invoice=None, request_id=None):
    # Disabled navigation performs no new ORM/permission queries on old pages.
    if not ui_enabled():
        return {}
    if invoice is None:
        try:
            authorize_return_note(user, request_id)
        except PermissionDenied:
            return {}
        invoice = Invoice.objects.filter(request_id=request_id, status="FINALIZED").first()
        if invoice is None:
            return {"unavailable": True}
    if invoice.status != "FINALIZED":
        return {}
    try:
        authorize_return_note(user, invoice.request_id)
    except PermissionDenied:
        return {}
    result = {"invoice_id": invoice.pk, "can_read": True, "can_issue": False}
    try:
        authorize_return_note(user, invoice.request_id, issue=True)
    except PermissionDenied:
        pass
    else:
        result["can_issue"] = True
    return result
