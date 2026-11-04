"""Read-only incoming receipt browsing. Legacy metadata is never inferred or backfilled."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .entry_services import authorize
from .models import MaterialReceipt, MaterialReceiptLine
from .entry_dates import EntryDateField, canonical_date

PAGE_SIZE = 25
FILTER_KEYS = ("q", "date_from", "date_to", "transaction_type")


class ReceiptHistoryFilter(forms.Form):
    q = forms.CharField(label=gettext_lazy("Search receipts"), required=False, max_length=200,
        widget=forms.TextInput(attrs={"type": "search"}))
    date_from = EntryDateField(label=gettext_lazy("Receipt date from"), required=False)
    date_to = EntryDateField(label=gettext_lazy("Receipt date to"), required=False)
    transaction_type = forms.ChoiceField(label=gettext_lazy("Transaction type"), required=False,
        choices=[("", gettext_lazy("All transaction types")), ("new", gettext_lazy("New material")),
                 ("existing", gettext_lazy("Existing material")), ("unknown", gettext_lazy("Not recorded"))])

    def clean(self):
        values = super().clean()
        if values.get("date_from") and values.get("date_to") and values["date_from"] > values["date_to"]:
            self.add_error("date_to", gettext_lazy("The end date must be on or after the start date."))
        return values


def receipt_queryset():
    return MaterialReceipt.objects.select_related("created_by").prefetch_related(Prefetch(
        "lines", queryset=MaterialReceiptLine.objects.select_related("material__category", "movement").order_by("pk")))


def display_receipt(receipt):
    rows = []
    for line in receipt.lines.all():
        snapshot = line.material_snapshot
        recorded = isinstance(snapshot, dict) and snapshot.get("version") == 1 and all(
            isinstance(snapshot.get(key), str) for key in ("name", "code", "unit", "category_name", "category_code"))
        material = snapshot if recorded else {
            "name": line.material.name, "code": line.material.code, "unit": line.material.unit,
            "category_name": line.material.category.name, "category_code": line.material.category.code,
            "description": line.material.description,
        }
        rows.append({"line": line, "material": material, "snapshot_recorded": recorded,
                     "stock_before": line.stock_after - line.quantity})
    return {"receipt": receipt, "line_rows": rows,
            "transaction_label": receipt.get_transaction_type_display() if receipt.transaction_type else _("Not recorded")}


def history_query(request, *, page=None):
    query = QueryDict(mutable=True)
    for key in FILTER_KEYS:
        if key in request.GET:
            query[key] = canonical_date(request.GET[key]) if key in ("date_from", "date_to") else request.GET[key]
    if page is not None:
        query["page"] = str(page)
    elif "page" in request.GET:
        query["page"] = request.GET["page"]
    return query


@login_required
@require_GET
@never_cache
def receipt_history(request):
    authorize(request.user)
    form = ReceiptHistoryFilter(request.GET)
    receipts = receipt_queryset()
    if form.is_valid():
        values = form.cleaned_data
        if values["q"]:
            term = values["q"]
            receipts = receipts.filter(
                Q(reference__icontains=term) | Q(supplier__icontains=term) | Q(delivery_reference__icontains=term)
                | Q(lines__material_snapshot__name__icontains=term) | Q(lines__material_snapshot__code__icontains=term)
                | Q(lines__material_snapshot__isnull=True, lines__material__name__icontains=term)
                | Q(lines__material_snapshot__isnull=True, lines__material__code__icontains=term)).distinct()
        if values["date_from"]:
            receipts = receipts.filter(received_on__gte=values["date_from"])
        if values["date_to"]:
            receipts = receipts.filter(received_on__lte=values["date_to"])
        if values["transaction_type"] == "unknown":
            receipts = receipts.filter(transaction_type__isnull=True)
        elif values["transaction_type"]:
            receipts = receipts.filter(transaction_type=values["transaction_type"])
    else:
        receipts = receipts.none()
    page = Paginator(receipts.order_by("-received_on", "-pk"), PAGE_SIZE).get_page(request.GET.get("page"))
    query = history_query(request, page=page.number)
    filters = query.copy()
    filters.pop("page", None)
    return render(request, "inventory/receipt_history.html", {
        "mode": "history", "filter_form": form, "page_obj": page,
        "receipt_rows": [display_receipt(receipt) for receipt in page.object_list],
        "history_query": query.urlencode(), "filter_query": filters.urlencode(),
    })


@login_required
@require_GET
@never_cache
def receipt_detail(request, receipt_id):
    authorize(request.user)
    receipt = get_object_or_404(receipt_queryset(), pk=receipt_id)
    query = history_query(request).urlencode()
    return render(request, "inventory/receipt_detail.html", {
        "mode": "history", **display_receipt(receipt),
        "history_url": reverse("material_receipt_history") + ("?" + query if query else ""),
    })
