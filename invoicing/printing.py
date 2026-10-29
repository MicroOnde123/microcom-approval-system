"""Bounded print batches of authorized, checksum-verified existing invoice PDFs."""
import io

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.utils.translation import gettext as _

from .documents import generate_pdf, download_pdf
from .models import Invoice
from .permissions import authorize, require_permission, request_scope
from .filters import InvoiceFilterForm, apply_invoice_filters

MAX_PRINT_INVOICES = 20
MAX_PRINT_BYTES = 50 * 1024 * 1024
MAX_PRINT_PAGES = 200


def prepare_filtered_print(data, user, *, language):
    """Rebuild selection on the server across all pages; never accept client IDs."""
    require_permission(user, "view_invoice")
    form = InvoiceFilterForm(data, require_dates=True)
    if not form.is_valid():
        raise ValidationError([message for errors in form.errors.values() for message in errors])
    scope = request_scope(user)
    queryset = Invoice.objects.filter(request_id__in=scope.values("pk"))
    queryset = apply_invoice_filters(queryset, form.cleaned_data).filter(status="FINALIZED")
    ids = list(queryset.order_by("issue_date", "number", "pk").values_list("pk", flat=True)[:MAX_PRINT_INVOICES + 1])
    if not ids:
        raise ValidationError(_("No finalized invoices match these filters."))
    if len(ids) > MAX_PRINT_INVOICES:
        raise ValidationError(_("More than %(limit)s finalized invoices match these filters. Narrow the date range or search before printing.") % {"limit": MAX_PRINT_INVOICES})
    return prepare_bulk_print(ids, user, language=language)


def selected_invoice_ids(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValidationError(_("Select at least one finalized invoice to print."))
    if len(values) > MAX_PRINT_INVOICES:
        raise ValidationError(_("Select no more than %(limit)s invoices to print.") % {"limit": MAX_PRINT_INVOICES})
    result = []
    for value in values:
        if type(value) is int:
            number = value
        elif type(value) is str and value.isascii() and value.isdigit() and len(value) <= 19:
            number = int(value)
        else:
            raise ValidationError(_("The invoice selection is invalid. Return to the invoice list and select again."))
        if not 0 < number <= 9223372036854775807 or number in result:
            raise ValidationError(_("The invoice selection is invalid. Return to the invoice list and select again."))
        result.append(number)
    return result


def merge_invoice_pdfs(contents):
    """Only server-generated PDFs, verified by download_pdf; no uploaded PDFs."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        raise ImproperlyConfigured("Install the configured invoice PDF merging dependency.") from None

    class BoundedOutput(io.BytesIO):
        def write(self, data):
            if self.tell() + len(data) > MAX_PRINT_BYTES:
                raise ValidationError(_("The selected invoices exceed the printing size limit. Print a smaller selection."))
            return super().write(data)

    if not contents or len(contents) > MAX_PRINT_INVOICES or sum(len(data) for data in contents) > MAX_PRINT_BYTES:
        raise ValidationError(_("The selected invoices exceed the printing size limit. Print a smaller selection."))
    writer = PdfWriter()
    try:
        for content in contents:
            reader = PdfReader(io.BytesIO(content), strict=True)
            if reader.is_encrypted or not reader.pages:
                raise ValueError
            if len(writer.pages) + len(reader.pages) > MAX_PRINT_PAGES:
                raise ValidationError(_("The selected invoices exceed the printing page limit. Print a smaller selection."))
            # Each source starts on a fresh page; retain all its pages. Do not
            # copy document-level actions, attachments, outlines or annotations.
            for page in reader.pages:
                writer.add_page(page, excluded_keys=["/Annots", "/AA"])
        with BoundedOutput() as output:
            writer.write(output)
            return output.getvalue()
    except ValidationError:
        raise
    except Exception:
        raise ValidationError(_("The combined invoice PDF could not be prepared. Try a smaller selection or ask an administrator for help.")) from None
    finally:
        writer.close()


def prepare_bulk_print(values, user, *, language):
    ids = selected_invoice_ids(values)
    if language not in {"en", "fr"}:
        raise ValidationError(_("Choose English or French for the PDF."))
    invoices = {invoice.pk: invoice for invoice in Invoice.objects.filter(pk__in=ids).only("pk", "request_id", "status")}
    # Check the whole selection before any PDF attempt is created. Each source
    # service independently rechecks authorization and verifies its checksum.
    for invoice_id in ids:
        invoice = invoices.get(invoice_id)
        if invoice is None:
            raise ValidationError(_("The invoice selection is invalid. Return to the invoice list and select again."))
        authorize(user, "view_invoice", invoice.request_id)
        if invoice.status != "FINALIZED":
            raise ValidationError(_("Only finalized invoices can be printed."))
    contents = []
    total_bytes = 0
    for invoice_id in ids:
        artifact = generate_pdf(invoice_id, user, language=language)
        _downloaded_artifact, stream = download_pdf(artifact.pk, user)
        with stream:
            content = stream.read(MAX_PRINT_BYTES + 1)
        total_bytes += len(content)
        if total_bytes > MAX_PRINT_BYTES:
            raise ValidationError(_("The selected invoices exceed the printing size limit. Print a smaller selection."))
        contents.append(content)
    # The combined file is transient; original artifacts remain append-only.
    return merge_invoice_pdfs(contents)
