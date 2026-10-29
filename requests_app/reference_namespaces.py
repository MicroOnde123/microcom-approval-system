"""Shared ordinary namespace policy; no model imports or database access."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def administration_code():
    code = getattr(settings, "ADMINISTRATION_REPORT_REQUEST_TYPE_CODE", "AUTORISATION_GENERAL")
    if not isinstance(code, str) or not code.strip() or code == "MATERIAL":
        raise ValidationError(_("The administration and material reference types must be distinct."))
    return code


def validate_namespace_owner(code, namespace):
    admin = administration_code()
    expected = "ADM" if code == admin else "MAT" if code == "MATERIAL" else None
    if namespace:
        if (expected and namespace != expected) or (not expected and namespace in {"ADM", "MAT"}):
            raise ValidationError(_("ADM and MAT are reserved for their canonical request types. The configured namespace does not match this type."))
    return expected
