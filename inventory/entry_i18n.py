"""Localized presentation of Material Entries denials; authorization is unchanged."""
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext as _
from django.views.defaults import permission_denied as default_permission_denied
from django.views.csrf import csrf_failure as default_csrf_failure


def is_material_entries(request):
    return request.path.startswith("/materials/entries/") or request.path == "/materials/categories/create/"


def denied_response(request, message):
    if request.path == "/materials/categories/create/":
        return JsonResponse({"errors": {"__all__": [message]}}, status=403)
    return render(request, "inventory/entry_denied.html", {"denial_message": message}, status=403)


def permission_denied(request, exception):
    if not is_material_entries(request):
        return default_permission_denied(request, exception)
    return denied_response(request, _("You do not have permission to manage material entries."))


def csrf_failure(request, reason=""):
    if not is_material_entries(request):
        return default_csrf_failure(request, reason=reason)
    # Never expose raw technical failure reasons or tokens to the user.
    return denied_response(request, _("Your form could not be verified. Reload the page and try again."))
