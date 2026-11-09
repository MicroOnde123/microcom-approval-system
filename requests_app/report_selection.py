"""Signed filter context for explicit cross-page Material Report selections."""
from urllib.parse import urlencode
from django.core import signing
from django.core.exceptions import ValidationError
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext as _

SALT = "requests.material_report_selection.v1"
FILTERS = ("q", "date_from", "date_to", "department", "status")


def context_key(request):
    session = getattr(request, "session", None)
    return salted_hmac(SALT, f"{request.user.pk}:{getattr(session, 'session_key', '') or ''}").hexdigest()


def filter_values(query):
    return {key: query.get(key, "").strip() for key in FILTERS}


def report_selection(request):
    filters = filter_values(request.GET)
    context = context_key(request)
    return {"report_scope": urlencode(filters), "report_selection_context": context,
            "report_filter_token": signing.dumps({"context": context, "filters": filters}, salt=SALT)}


def selected_ids(post):
    values = post.getlist("selected_requests")
    if any(not v.isascii() or not v.isdigit() or len(v) > 19 or not 0 < int(v) <= 9223372036854775807 for v in values):
        raise ValidationError(_("The selection is invalid or has changed. Reload the report and select the requests again."))
    return list(dict.fromkeys(int(v) for v in values))


def selection_filters(request):
    proof = request.POST.get("report_filter_scope")
    if not proof:
        return None  # Preserve explicit-ID submissions from existing callers.
    try:
        data = signing.loads(proof, salt=SALT)
        if data["context"] != context_key(request) or set(data["filters"]) != set(FILTERS):
            raise ValueError
        return data["filters"]
    except (signing.BadSignature, ValueError, TypeError, KeyError):
        raise ValidationError(_("The selection is invalid or has changed. Reload the report and select the requests again."))
