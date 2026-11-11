from .adjusted_access import navigation as adjusted_navigation
from .document_presentation import amount_words
from .print_delivery import active_language
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _, get_language
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django.views.decorators.cache import never_cache
from django.db import DatabaseError, transaction
from django.db.models import Count, DecimalField, Q, Sum
from django.http import FileResponse, Http404
import io
from decimal import Decimal

from core.models import CompanyDocumentSettings
from requests_app.models import Request
from .configuration import business_date
from .forms import CreateInvoiceForm, DraftInformationForm, Prices, FinalizeInvoiceForm
from .models import DocumentSequence, Invoice, DocumentArtifact
from .documents import generate_pdf, download_pdf
from .permissions import authorize, require_permission, request_scope
from .services import create_draft, edit_draft, refresh_draft, finalize_invoice, draft_revision, database_now
from .return_note_access import navigation as return_note_navigation
from .audit_presentation import format_event
from .printing import MAX_PRINT_INVOICES, prepare_filtered_print
from .filters import InvoiceFilterForm, InvoiceCandidateFilterForm, apply_invoice_filters


def _invoice(user,pk,action="view_invoice"):
    require_permission(user,action)
    invoice = get_object_or_404(Invoice,pk=pk)
    authorize(user,action,invoice.request_id)
    return invoice


def _errors(form,error):
    for message in error.messages:
        form.add_error(None,message)


@login_required
def invoice_list(request):
    require_permission(request.user,"view_invoice")
    scope = request_scope(request.user)
    filters = InvoiceFilterForm(request.GET)
    invoices = Invoice.objects.filter(request_id__in=scope.values("pk"))
    invoices = apply_invoice_filters(invoices, filters.cleaned_data) if filters.is_valid() else invoices.none()
    invoices = invoices.select_related("request", "succursale", "company_verification").annotate(
        list_line_count=Count("lines", filter=Q(status="DRAFT")),
        list_priced_line_count=Count("lines", filter=Q(status="DRAFT",
            lines__unit_price__isnull=False, lines__line_total__isnull=False)),
        list_provisional_total=Sum("lines__line_total", filter=Q(status="DRAFT"),
            output_field=DecimalField(max_digits=20, decimal_places=2)),
    ).order_by("-created_at","-pk")
    candidates = scope.filter(status="APPROVED",classification="MICROCOM",stock_deducted=True,invoice__isnull=True).order_by("-pk")
    if not request.user.has_perm("invoicing.add_invoice"):
        candidates = Request.objects.none()
    candidate_form = InvoiceCandidateFilterForm(request.GET)
    if candidate_form.is_valid():
        if candidate_form.cleaned_data["candidate_q"]:
            candidates = candidates.filter(request_number__icontains=candidate_form.cleaned_data["candidate_q"])
    else:
        candidates = Request.objects.none()
    candidate_rows = list(candidates[:51])
    params = request.GET.copy()
    # Only supported filters survive pagination and the print form.
    active = {name: request.GET.get(name, "") for name in filters.fields}
    for name in list(params):
        if name not in {*filters.fields, "candidate_q"}:
            params.pop(name)
    return render(request,"invoicing/list.html",{"page_obj":Paginator(invoices,25).get_page(request.GET.get("page")),
        "candidate_requests":candidate_rows[:50], "candidate_has_more":len(candidate_rows) > 50,
        "candidate_form":candidate_form, "can_create_invoice":request.user.has_perm("invoicing.add_invoice"),
        "invoice_print_limit": MAX_PRINT_INVOICES,
        "filter_form": filters, "active_querystring": params.urlencode(), "active_filters": active})


@login_required
@require_http_methods(["GET","POST"])
def invoice_create(request,request_id):
    require_permission(request.user,"add_invoice")
    source = get_object_or_404(Request,pk=request_id)
    authorize(request.user,"add_invoice",source.pk)
    form = CreateInvoiceForm(request.POST if request.method=="POST" else None,initial={"currency":CompanyDocumentSettings.objects.values_list("default_currency",flat=True).first() or "USD"})
    if request.method=="POST" and form.is_valid():
        try:
            invoice = create_draft(source.pk,request.user,currency=form.cleaned_data["currency"])
        except ValidationError as error:
            _errors(form,error)
        else:
            messages.success(request,_("Invoice draft created. No document number has been allocated."))
            return redirect("invoicing:detail",pk=invoice.pk)
    return render(request,"invoicing/create.html",{"form":form,"source_request":source,
        "company": CompanyDocumentSettings.objects.filter(pk=1).first(),
        "source_lines": source.material_items.select_related("material").order_by("pk")})


@login_required
def invoice_detail(request,pk):
    invoice = _invoice(request.user,pk)
    lines = list(invoice.lines.order_by("position","pk"))
    line_labels = {line.pk: line.material_code_snapshot + " — " + line.description_snapshot for line in lines}
    history = [{"event": event, "presentation": format_event(event.event_type, event.details, line_labels)}
        for event in invoice.invoiceauditevent_set.select_related("actor").order_by("occurred_at","pk")]
    # Presentation only: sum already-recorded draft line totals, never reprice lines.
    draft_total = sum((line.line_total for line in lines), Decimal("0")) if (
        lines and all(line.unit_price is not None and line.line_total is not None for line in lines)) else None
    finalization_success = invoice.status == "FINALIZED" and any(
        message.extra_tags == f"invoice-finalized-{invoice.pk}"
        for message in messages.get_messages(request))
    return render(request,"invoicing/detail.html",{"invoice":invoice,"lines":lines,
        "draft_total": draft_total, "finalization_success": finalization_success,
        "audit_history":history,
        "display_amount_words": amount_words(invoice.total, invoice.currency, active_language(), invoice.amount_words_fr) if invoice.status == "FINALIZED" else "",
        "return_note_nav":return_note_navigation(request.user, invoice=invoice),
        "adjusted_nav":adjusted_navigation(request.user,invoice),
        "can_edit":invoice.status=="DRAFT" and request.user.has_perm("invoicing.change_invoice"),
        "can_finalize":invoice.status=="DRAFT" and request.user.has_perm("invoicing.finalize_invoice")})


@login_required
@require_http_methods(["GET","POST"])
def invoice_edit(request,pk):
    invoice = _invoice(request.user,pk,"change_invoice")
    if invoice.status!="DRAFT":
        messages.error(request,_("Finalized invoices are read-only."))
        return redirect("invoicing:detail",pk=pk)
    lines = list(invoice.lines.order_by("position","pk"))
    form = DraftInformationForm(request.POST if request.method=="POST" else None,initial={"note":invoice.audit_metadata.get("note",""),"revision":draft_revision(invoice,request.user,lines=lines)})
    prices = Prices(request.POST if request.method=="POST" else None,lines=lines,prefix="prices")
    if request.method=="POST" and form.is_valid() and prices.is_valid():
        try:
            edit_draft(pk,request.user,prices={row.cleaned_data["line_id"]:row.cleaned_data["unit_price"] for row in prices},
                note=form.cleaned_data["note"],revision=form.cleaned_data["revision"])
        except ValidationError as error:
            _errors(form,error)
        else:
            messages.success(request,_("Invoice draft saved."))
            return redirect("invoicing:detail",pk=pk)
    return render(request,"invoicing/edit.html",{"invoice":invoice,"form":form,"prices":prices})


@login_required
@require_POST
def invoice_refresh(request,pk):
    _invoice(request.user,pk,"change_invoice")
    try:
        refresh_draft(pk,request.user,revision=request.POST.get("revision",""))
    except ValidationError as error:
        for message in error.messages:
            messages.error(request,message)
    else:
        messages.success(request,_("Draft quantities refreshed from stock evidence. Review them before finalizing."))
    return redirect("invoicing:edit",pk=pk)


@login_required
@require_http_methods(["GET","POST"])
def invoice_finalize(request,pk):
    invoice = _invoice(request.user,pk,"finalize_invoice")
    if invoice.status=="FINALIZED":
        return redirect("invoicing:detail",pk=pk)
    day = business_date(database_now(),"Africa/Kinshasa")
    sequences = list(DocumentSequence.objects.filter(document_type="INVOICE",year=day.year).order_by("series"))
    sequences = [sequence for sequence in sequences if sequence.is_verified]
    lines = list(invoice.lines.order_by("position","pk"))
    form = FinalizeInvoiceForm(request.POST if request.method=="POST" else None,sequences=sequences,initial={"revision":draft_revision(invoice,request.user,lines=lines)})
    if request.method=="POST" and form.is_valid():
        try:
            invoice = finalize_invoice(pk,request.user,series=form.cleaned_data["series"],revision=form.cleaned_data["revision"])
        except ValidationError as error:
            _errors(form,error)
        else:
            messages.success(request,_("Invoice finalized. Its number and financial snapshots are now permanent."),
                             extra_tags=f"invoice-finalized-{invoice.pk}")
            return redirect("invoicing:detail",pk=pk)
    # Review sums recorded line totals only. Finalization still revalidates in its service.
    review_total = sum((line.line_total for line in lines), Decimal("0")) if (
        lines and all(line.unit_price is not None and line.line_total is not None for line in lines)) else None
    return render(request,"invoicing/finalize.html",{"invoice":invoice,"form":form,"lines":lines,
        "company": CompanyDocumentSettings.objects.filter(pk=1).first(),
        "review_total": review_total, "sequences_available":bool(sequences)})


@transaction.non_atomic_requests
@login_required
@require_POST
def invoice_pdf(request, pk, language):
    try:
        _invoice(request.user, pk)
        artifact = generate_pdf(pk, request.user, language=active_language())
    except (ValidationError, ImproperlyConfigured, DatabaseError, OSError) as error:
        return _print_error(request, error)
    return redirect("invoicing:download", artifact_id=artifact.pk)


@login_required
@never_cache
@require_GET
def invoice_download(request, artifact_id, *, attachment=False):
    try:
        require_permission(request.user, "view_invoice")
        artifact, stream = download_pdf(artifact_id, request.user)
    except DocumentArtifact.DoesNotExist:
        raise Http404 from None
    except (ValidationError, ImproperlyConfigured, DatabaseError, OSError) as error:
        return _print_error(request, error)
    return _inline_pdf(stream, f"invoice-{artifact.invoice_id}-{artifact.language}.pdf", attachment=attachment)


def _inline_pdf(stream, filename, *, attachment=False):
    response = FileResponse(stream, as_attachment=attachment, filename=filename, content_type="application/pdf")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _print_language():
    return "fr" if (get_language() or "en").split("-", 1)[0].lower() == "fr" else "en"


def _print_error(request, error):
    # Configuration and database errors may contain paths/connection information.
    errors = error.messages if isinstance(error, ValidationError) else [_(
        "Invoice printing is unavailable. Ask an administrator to review private document storage and printing configuration.")]
    return render(request, "invoicing/pdf_error.html", {"errors": errors}, status=409)


@transaction.non_atomic_requests
@login_required
@never_cache
@require_POST
def invoice_print(request, pk, *, attachment=False):
    try:
        invoice = _invoice(request.user, pk)
        if invoice.status != "FINALIZED":
            raise ValidationError(_("Only finalized invoices can be printed."))
        artifact = generate_pdf(pk, request.user, language=_print_language())
    except (ValidationError, ImproperlyConfigured, DatabaseError, OSError) as error:
        return _print_error(request, error)
    # Top-level authenticated GET works without Blob URLs, embedded viewers,
    # static JavaScript or a cross-frame print() call. The delivery endpoint
    # rechecks current permissions and checksum on every open/download.
    return redirect("invoicing:download_file" if attachment else "invoicing:download",
                    artifact_id=artifact.pk)


@transaction.non_atomic_requests
@login_required
@never_cache
@require_POST
def invoice_bulk_print(request):
    try:
        require_permission(request.user, "view_invoice")
        content = prepare_filtered_print(request.POST, request.user, language=_print_language())
    except (ValidationError, ImproperlyConfigured, DatabaseError, OSError) as error:
        return _print_error(request, error)
    return _inline_pdf(io.BytesIO(content), "invoices-" + _print_language() + ".pdf")
