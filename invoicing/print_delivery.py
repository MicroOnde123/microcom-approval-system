"""Authenticated callers supply already-authorized, checksum-verified PDFs."""
import base64
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.translation import get_language


def active_language():
    return "fr" if (get_language() or "en").split("-", 1)[0].lower() == "fr" else "en"


def print_response(request, content, filename):
    # Standalone viewer: no navigation context processors or extra ORM queries.
    response = HttpResponse(render_to_string("invoicing/print_document.html", {
        "pdf_base64": base64.b64encode(content).decode("ascii"), "filename": filename,
        "LANGUAGE_CODE": active_language()}))
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
