"""HTTP orchestration only. E-R2 owns all financial decisions and issuance."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from requests_app.models import StockMovement
from . import return_note_services as issuance
from .models import DocumentSequence, Invoice, MaterialReturnNoteArtifact
from .permissions import authorize_return_note
from .return_note_access import gated, navigation
from .return_note_forms import ReturnNoteSelectionForm, ReturnNoteConfirmationForm
from .return_note_documents import generate_pdf, download_pdf
from . import return_note_sessions as confirmations
from .return_note_recovery import category

SESSION_KEY = confirmations.SESSION_KEY


def _invoice(user, pk, *, issue=False, preview=False):
    invoice = get_object_or_404(Invoice, pk=pk, status="FINALIZED")
    authorize_return_note(user, invoice.request_id, issue=issue, preview=preview)
    return invoice


def _session(request):
    return confirmations.entries(request)


def _store(request, invoice_id, preview, arguments):
    return confirmations.store(request, invoice_id, preview, arguments)


def _selection(invoice, user, data=None):
    rows = issuance.eligible_return_movements(invoice.pk, user)
    # Only attach authorized display data. Eligibility/values come from E-R2.
    movements = {m.pk: m for m in StockMovement.objects.filter(request_id=invoice.request_id,
        pk__in=[row["return_movement_id"] for row in rows]).order_by("pk")}
    lines = {line.material_id: line for line in invoice.lines.all()}
    selected = set(data.getlist("movements")) if data is not None else set()
    for row in rows:
        movement = movements.get(row["return_movement_id"])
        line = lines.get(movement.material_id) if movement else None
        row.update({"movement": movement, "line": line,
                    "selected": row["eligible"] and str(row["return_movement_id"]) in selected})
        if not row["eligible"] and movement and movement.created_at <= invoice.finalized_at:
            # Explanation only: never override E-R2 eligibility or valuations.
            row["reason"] = _("This physical return predates or coincides with facture finalization. It cannot be valued again by a material return note.")
    day = issuance.business_date(issuance.database_now(), invoice.business_timezone)
    sequences = [s for s in DocumentSequence.objects.filter(document_type="RETURN_NOTE", year=day.year).order_by("series")
                 if s.is_verified]
    form = ReturnNoteSelectionForm(data, rows=rows, sequences=sequences)
    return {"invoice": invoice, "rows": rows, "form": form, "has_eligible": any(row["eligible"] for row in rows),
            "has_sequences": bool(sequences)}


def _error(request, error, *, invoice=None, status=409, retry_handle=None, note=None, language=None):
    # No exception repr, traceback, paths, tokens or operation payload in output.
    errors = error.messages if isinstance(error, ValidationError) else [_("The return note document is unavailable. Ask an administrator to review private storage.")]
    recovery = category(error)
    if retry_handle and recovery == "outcome_uncertain":
        errors = [_("The previous issuance may have completed. Check history or retry the same confirmation. Do not start a new operation to recover this response.")]
    return render(request, "invoicing/return_notes/pdf_error.html", {"errors": errors, "invoice": invoice,
        "recovery": recovery, "note": note, "language": language,
        "retry_form": ReturnNoteConfirmationForm(initial={"handle": retry_handle})
            if retry_handle and recovery == "outcome_uncertain" else None,
        "can_retry_pdf": note is not None and language in {"en", "fr"} and recovery == "pdf_transient",
        "can_preview_again": invoice is not None and retry_handle is None and recovery != "outcome_uncertain"}, status=status)


@transaction.non_atomic_requests
@gated
@login_required
@never_cache
@require_GET
def select(request, invoice_id):
    invoice = _invoice(request.user, invoice_id, issue=True)
    try:
        context = _selection(invoice, request.user)
    except ValidationError as error:
        return _error(request, error, invoice=invoice)
    return render(request, "invoicing/return_notes/select.html", context)


@transaction.non_atomic_requests
@gated
@login_required
@never_cache
@require_POST
def preview(request, invoice_id):
    invoice = _invoice(request.user, invoice_id, issue=True)
    try:
        context = _selection(invoice, request.user, request.POST)
        form = context["form"]
        if form.is_valid():
            arguments = {"return_movement_ids": form.cleaned_data["movements"],
                         "reason": form.cleaned_data["reason"], "series": form.cleaned_data["series"]}
            result = issuance.preview_material_return_note(invoice.pk, request.user, **arguments)
            handle = _store(request, invoice.pk, result, arguments)
            # Explicit allowlist: signatures, UUID and ledger digests never reach
            # template context or HTML, even via debug/default rendering.
            display = {key: result[key] for key in ("lines", "total", "currency", "cumulative_returned_value",
                "adjusted_net_value", "original_invoice_snapshot", "business_date")}
            return render(request, "invoicing/return_notes/preview.html", {"invoice": invoice, "preview": display,
                "reason": arguments["reason"], "series": arguments["series"],
                "form": ReturnNoteConfirmationForm(initial={"handle": handle})})
    except ValidationError as error:
        return _error(request, error, invoice=invoice)
    return render(request, "invoicing/return_notes/select.html", context, status=400)


@transaction.non_atomic_requests
@gated
@login_required
@never_cache
@require_POST
def issue(request, invoice_id):
    invoice = _invoice(request.user, invoice_id, issue=True)
    form = ReturnNoteConfirmationForm(request.POST)
    if not form.is_valid():
        return _error(request, ValidationError(_("Confirm the preview before issuing the material return note.")), invoice=invoice, status=400)
    retained = None
    try:
        entry, _preview_expired = confirmations.load(request, invoice.pk, form.cleaned_data["handle"])
        retained = form.cleaned_data["handle"]
        # Do not pre-check age/current eligibility: E-R2 must be able to recover
        # a committed response using the original token, even after expiry.
        note = issuance.issue_material_return_note(invoice.pk, request.user, **entry["arguments"],
            issuance_token=entry["issuance_token"], confirmation=entry["confirmation"])
    except ValidationError as error:
        return _error(request, error, invoice=invoice,
                      retry_handle=retained if category(error) == "outcome_uncertain" else None)
    messages.success(request, _("Material return note issued. The original invoice and stock records are unchanged."))
    return redirect("invoicing:return_note_detail", note_id=note.pk)


@gated
@login_required
@never_cache
@require_GET
def history(request, invoice_id):
    invoice = _invoice(request.user, invoice_id)
    # Query only IDs for pagination; financial document retrieval stays in E-R2.
    notes = invoice.material_return_notes.filter(status="FINALIZED").order_by("-finalized_at", "-pk").values_list("pk", flat=True)
    page = Paginator(notes, 25).get_page(request.GET.get("page"))
    page.object_list = [issuance.get_material_return_note(pk, request.user) for pk in page.object_list]
    for note in page.object_list:
        # Immutable note lines only; never infer history from mutable stock data.
        lines = list(note.lines.order_by("pk").values("return_movement_id", "quantity", "unit_snapshot"))
        note.return_movement_summary = lines[:5]
        note.additional_movement_count = max(0, len(lines) - 5)
    return render(request, "invoicing/return_notes/history.html", {"invoice": invoice,
        "page_obj": page, "return_note_nav": navigation(request.user, invoice=invoice)})


@gated
@login_required
@never_cache
@require_GET
def detail(request, note_id):
    try:
        note = issuance.get_material_return_note(note_id, request.user)
    except issuance.MaterialReturnNote.DoesNotExist:
        raise Http404 from None
    try:
        authorize_return_note(request.user, note.invoice.request_id, document=True)
        can_document = True
    except PermissionDenied:
        can_document = False
    return render(request, "invoicing/return_notes/detail.html", {"note": note, "lines": note.lines.order_by("pk"),
        "reason": note.operation.reason, "can_document": can_document})


@transaction.non_atomic_requests
@gated
@login_required
@never_cache
@require_POST
def pdf(request, note_id, language):
    try:
        note = issuance.get_material_return_note(note_id, request.user)
    except issuance.MaterialReturnNote.DoesNotExist:
        raise Http404 from None
    authorize_return_note(request.user, note.invoice.request_id, document=True)
    try:
        artifact = generate_pdf(note_id, request.user, language=language)
    except issuance.MaterialReturnNote.DoesNotExist:
        raise Http404 from None
    except (ValidationError, ImproperlyConfigured) as error:
        return _error(request, error, note=note, language=language)
    return redirect("invoicing:return_note_download", artifact_id=artifact.pk)


@gated
@login_required
@never_cache
@require_GET
def download(request, artifact_id):
    try:
        owner = MaterialReturnNoteArtifact.objects.get(pk=artifact_id)
        note = issuance.get_material_return_note(owner.note_id, request.user)
    except (MaterialReturnNoteArtifact.DoesNotExist, issuance.MaterialReturnNote.DoesNotExist):
        raise Http404 from None
    authorize_return_note(request.user, note.invoice.request_id, document=True)
    try:
        artifact, stream = download_pdf(artifact_id, request.user)
    except (MaterialReturnNoteArtifact.DoesNotExist, issuance.MaterialReturnNote.DoesNotExist):
        raise Http404 from None
    except (ValidationError, ImproperlyConfigured) as error:
        return _error(request, error, note=note, language=owner.language)
    response = FileResponse(stream, as_attachment=True,
        filename=f"return-note-{artifact.note_id}-{artifact.language}.pdf", content_type="application/pdf")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
