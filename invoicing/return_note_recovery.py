"""Sanitized recovery categories; no financial decisions or database access."""
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


def category(error):
    allowed = {"preview_invalid", "outcome_uncertain", "session_unavailable", "pdf_transient", "pdf_review_required"}
    codes = {getattr(item, "code", None) for item in getattr(error, "error_list", [])}
    if "outcome_uncertain" in codes:
        return "outcome_uncertain"
    return next((code for code in sorted(allowed) if code in codes), "review_required")


def session_error():
    return ValidationError(_("This confirmation is missing, malformed, expired or overwritten. Check issued-note history. A new preview is a different operation, not a retry of the previous one."), code="session_unavailable")


def pdf_error(*, transient=False):
    if transient:
        return ValidationError(_("The PDF could not be prepared because storage or the document service is temporarily unavailable. Retry PDF only; the issued note is unchanged."), code="pdf_transient")
    return ValidationError(_("The PDF cannot be rendered safely. Ask an administrator to review the frozen snapshot, font or private storage configuration. The issued note is unchanged."), code="pdf_review_required")
