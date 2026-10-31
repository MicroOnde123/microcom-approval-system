from invoicing.print_delivery import print_response, active_language
"""Existing stock staff interface; all mutations require CSRF-protected POST."""
from uuid import uuid4
from zoneinfo import ZoneInfo
from django import forms
from django.core import signing
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, ImproperlyConfigured
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.contrib import messages
from django.utils.translation import gettext as _, get_language
from django.utils.timezone import localtime
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import Request, ReturnReceipt, ReturnReceiptArtifact, StockMovement
from .material_outcomes import authorize, reconcile, issue_receipt, OUTCOMES
from .return_receipt_documents import generate_receipt_pdf, read_artifact
from .stock_forms import ReturnToStockForm
from .stock_services import RETURN_TOKEN_SALT, return_material_stock


class ReceiptForm(forms.Form):
    token = forms.UUIDField(widget=forms.HiddenInput)
    movements = forms.MultipleChoiceField(label=_("Recorded physical returns"), widget=forms.CheckboxSelectMultiple)


def outcome_form(req, data=None, *, items=None, totals=None, latest=None):
    class OutcomeForm(forms.Form):
        token = forms.UUIDField(widget=forms.HiddenInput)
        revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
        reason = forms.CharField(label=_("Reconciliation reason"), max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))
    latest = latest if latest is not None else req.reconciliations.order_by("-revision").first()
    initial = {"token": uuid4(), "revision": latest.revision if latest else 0}
    recorded = {(line.item_id, line.outcome): line.quantity for line in latest.lines.all()} if latest else {}
    form = OutcomeForm(data, initial=initial)
    labels = {"CLIENT": _("CLIENT-installed"), "MICROCOM": _("MICROCOM-used"),
              "RETAINED": _("Retained / testing"), "RETURNED": _("Physically returned")}
    from .stock_services import material_return_totals
    for item in items if items is not None else req.material_items.select_related("material").order_by("pk"):
        item_totals = totals[item.pk] if totals is not None else material_return_totals(item)
        for key in OUTCOMES:
            default = recorded.get((item.pk, key), 0) if latest else (item_totals["remaining_quantity"] if key == "RETAINED" else item_totals["returned_quantity"] if key == "RETURNED" else 0)
            if item_totals["remaining_quantity"] == 0 and key != "RETURNED":
                default = 0
            if key == "RETURNED":
                default = item_totals["returned_quantity"]
            form.fields[f"item_{item.pk}_{key}"] = forms.DecimalField(
                label=f"{item.material.name} ({item.material.unit or ''}) — {labels[key]}",
                min_value=0, max_digits=10, decimal_places=2, initial=default)
            form.fields[f"item_{item.pk}_{key}"].widget.attrs.update({"step": "0.01", "inputmode": "decimal", "data-outcome": key})
            if key == "RETURNED":
                form.fields[f"item_{item.pk}_{key}"].widget.attrs["readonly"] = True
    return form


@login_required
@require_http_methods(["GET", "POST"])
def workspace(request, request_id):
    authorize(request.user)
    req = get_object_or_404(Request.objects.select_related("submitted_by"), pk=request_id, status="APPROVED", stock_deducted=True, request_type__requires_materials=True)
    error = ""
    items = list(req.material_items.select_related("material").order_by("pk"))
    latest = req.reconciliations.prefetch_related("lines").order_by("-revision").first()
    totals = {}
    try:
        from .stock_services import material_return_totals
        totals = {item.pk: material_return_totals(item) for item in items}
        form = outcome_form(req, request.POST if request.method == "POST" and request.POST.get("action") == "reconcile" else None,
                            items=items, totals=totals, latest=latest)
    except ValidationError as exc:
        form = None
        error = " ".join(exc.messages)
    movements = StockMovement.objects.filter(request=req, movement_type="RETURN").select_related("material", "performed_by").order_by("pk")
    receipt_form = ReceiptForm(request.POST if request.method == "POST" and request.POST.get("action") == "receipt" else None, initial={"token": uuid4()})
    def movement_choices(queryset):
        return [(str(m.pk), f"{m.material.name} — {m.quantity} {m.material.unit or ''} — {localtime(m.created_at, ZoneInfo('Africa/Kinshasa')):%Y-%m-%d %H:%M} (Africa/Kinshasa)") for m in queryset]
    receipt_form.fields["movements"].choices = movement_choices(movements.filter(returnreceiptline__isnull=True))
    operation = request.POST.get("action") if request.method == "POST" else ""
    active_tab = {"reconcile": "reconcile", "receipt": "returns", "return": "returns"}.get(operation, request.GET.get("tab", "overview"))
    if active_tab not in {"overview", "reconcile", "returns"}:
        active_tab = "overview"
    return_forms = {}
    for item in items:
        bound = operation == "return" and request.POST.get("item") == str(item.pk)
        return_forms[item.pk] = ReturnToStockForm(request.POST if bound else None, initial={
            "operation_token": signing.dumps({"item": item.pk, "user": request.user.pk, "operation": str(uuid4())}, salt=RETURN_TOKEN_SALT)})
        return_forms[item.pk].fields["quantity"].widget.attrs.update({"step": "0.01", "inputmode": "decimal"})
    if request.method == "POST":
        selected_return = next((return_forms[item.pk] for item in items if operation == "return" and request.POST.get("item") == str(item.pk)), None)
        if operation == "return" and selected_return is None:
            error = _("Select a material from this request.")
        selected = form if operation == "reconcile" else receipt_form if operation == "receipt" else selected_return
        # Retained selections remain valid for an exact committed replay after a lost response.
        if selected is receipt_form:
            receipt_form.fields["movements"].choices = movement_choices(movements)
        if selected is not None and selected.is_valid():
            try:
                if selected is form:
                    allocations = {item.pk: {key: form.cleaned_data[f"item_{item.pk}_{key}"] for key in OUTCOMES} for item in req.material_items.all()}
                    reconcile(req.pk, request.user, allocations=allocations, expected_revision=form.cleaned_data["revision"],
                        reported_by_id=req.submitted_by_id, reason=form.cleaned_data["reason"], token=form.cleaned_data["token"])
                elif selected is receipt_form:
                    issue_receipt(req.pk, request.user, [int(x) for x in selected.cleaned_data["movements"]], selected.cleaned_data["token"])
                else:
                    selected_item = next(item for item in items if return_forms[item.pk] is selected)
                    movement, created = return_material_stock(selected_item.pk, request.user, selected.cleaned_data["quantity"],
                        selected.cleaned_data["reason"], selected.cleaned_data["operation_token"])
            except ValidationError as exc:
                selected.add_error(None, exc)
            except DatabaseError:
                selected.add_error(None, _("The operation could not be confirmed. Retry the same form or review history; do not create a new operation."))
            else:
                message = (_("Material reconciliation saved.") if selected is form else
                    _("Return receipt issued. You can now view or print the PDF.") if selected is receipt_form else
                    _("Material returned to stock successfully.") if created else _("This return has already been recorded."))
                messages.success(request, message)
                return redirect(reverse("material_outcomes", args=[req.pk]) + "?tab=" + active_tab)
        if operation == "return":
            # A concurrent return may have changed the maximum during validation.
            try:
                totals = {item.pk: material_return_totals(item) for item in items}
            except ValidationError as exc:
                totals = {}
                error = " ".join(exc.messages)
    recorded = {(line.item_id, line.outcome): line.quantity for line in latest.lines.all()} if latest else {}
    rows = []
    for item in items:
        item_totals = totals.get(item.pk)
        return_form = return_forms[item.pk]
        if item_totals:
            return_form.fields["quantity"].widget.attrs["max"] = str(item_totals["remaining_quantity"])
        # Repeated controls have distinct accessible IDs while retaining the existing POST names.
        return_form.auto_id = f"return_{item.pk}_%s"
        row = {"item": item, "totals": item_totals, "return_form": return_form}
        if item_totals:
            row.update(client=recorded.get((item.pk, "CLIENT"), 0), microcom=recorded.get((item.pk, "MICROCOM"), 0),
                       outstanding=max(0, item_totals["remaining_quantity"] - recorded.get((item.pk, "CLIENT"), 0) - recorded.get((item.pk, "MICROCOM"), 0)), used=recorded.get((item.pk, "CLIENT"), 0) + recorded.get((item.pk, "MICROCOM"), 0),
                       retained=recorded.get((item.pk, "RETAINED"), 0) if latest else None,
                       status=_("Review required") if latest and recorded.get((item.pk, "RETURNED"), 0) != item_totals["returned_quantity"] else _("Reconciled") if latest else _("Not yet reconciled"))
        if form:
            row["fields"] = [(key, form[f"item_{item.pk}_{key}"]) for key in OUTCOMES]
        rows.append(row)
    return render(request, "requests_app/material_outcomes.html", {"request_obj": req, "form": form,
        "receipt_form": receipt_form, "return_error": error,
        "items": items, "material_rows": rows, "latest": latest,
        "active_operation": operation, "active_tab": active_tab,
        "history": req.reconciliations.select_related("recorded_by", "reported_by").prefetch_related("lines__item__material").order_by("-revision"),
        "receipts": req.return_receipts.prefetch_related("artifacts").order_by("-issued_at")})


@login_required
@require_POST
def receipt_pdf(request, receipt_id):
    authorize(request.user)
    receipt = get_object_or_404(ReturnReceipt, pk=receipt_id)
    language = active_language()
    if language not in {"en", "fr"}:
        return HttpResponse(_("Choose English or French for the PDF."), status=400)
    try:
        artifact = generate_receipt_pdf(receipt.pk, request.user, language)
        content = read_artifact(artifact, request.user)
    except (OSError, ValidationError, DatabaseError, ImproperlyConfigured):
        return render(request, "requests_app/receipt_pdf_error.html", {"receipt": receipt, "pdf_language": language}, status=503)
    if request.POST.get("intent") == "view":
        return _pdf_response(content, receipt.reference, language)
    return print_response(request, content, f"receipt-{receipt.pk}-{language}.pdf")


def _pdf_response(content, reference, language):
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{reference.replace("/", "-")}-{language}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def receipt_artifact(request, artifact_id):
    authorize(request.user)
    artifact = get_object_or_404(ReturnReceiptArtifact.objects.select_related("receipt"), pk=artifact_id)
    try:
        content = read_artifact(artifact, request.user)
    except (OSError, ValidationError, ImproperlyConfigured, DatabaseError):
        return render(request, "requests_app/receipt_pdf_error.html", {"receipt": artifact.receipt, "pdf_language": artifact.language}, status=503)
    return _pdf_response(content, artifact.receipt.reference, artifact.language)
