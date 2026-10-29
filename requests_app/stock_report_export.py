"""Read-only Excel support. No stock, financial or document issuance services."""
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from openpyxl.styles import Alignment, Font, PatternFill

from accounts.models import Department
from .models import RequestMaterialItem, StockMovement

BUSINESS_ZONE = ZoneInfo("Africa/Kinshasa")


class ExportFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=200)
    date_from = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    date_to = forms.DateField(required=False, input_formats=["%Y-%m-%d"])
    department = forms.ModelChoiceField(required=False, queryset=Department.objects.all())

    def clean(self):
        data = super().clean()
        if data.get("date_from") and data.get("date_to") and data["date_from"] > data["date_to"]:
            raise ValidationError(_("The start date must not be after the end date."))
        return data


def reporting_time(value):
    if value is None:
        return ""
    if timezone.is_naive(value):
        value = timezone.make_aware(value, ZoneInfo("UTC"))
    return timezone.localtime(value, BUSINESS_ZONE).strftime("%Y-%m-%d %H:%M")


def references(request):
    return {document.kind: document.reference for document in request.material_documents.all()}


def request_extras(request):
    refs = references(request)
    issues = []
    if request.classification == "CLIENT":
        classification, branch = _("Client"), _("Not applicable")
    elif request.classification == "MICROCOM":
        classification = _("Microcom")
        if request.succursale_id:
            branch = str(request.succursale)
        else:
            branch = _("Missing succursale")
            issues.append(branch)
    else:
        classification, branch = _("Classification unavailable"), _("Classification unavailable")
        issues.append(classification)
    for kind in ("BC", "BS"):
        if kind not in refs:
            issues.append(_("%(kind)s not issued") % {"kind": kind})
    return [classification, branch, refs.get("BC", _("Not issued")), refs.get("BS", _("Not issued")), "; ".join(issues) or _("Complete")]


def movement_scope(requests, filters):
    scope = Q(request_id__in=requests.values("pk"))
    # Date Needed and department/search filters belong to requests. Unlinked
    # movements cannot satisfy them: include these only in an unfiltered export.
    if not any(filters.get(key) for key in ("q", "date_from", "date_to", "department")):
        scope |= Q(request__isnull=True)
    return StockMovement.objects.filter(scope).select_related(
        "material__category", "performed_by", "request"
    ).order_by("created_at", "pk")


def enforce_size(requests, movements):
    limit = getattr(settings, "STOCK_REPORT_EXPORT_MAX_ROWS", 10000)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000_000:
        raise ValidationError(_("The Excel export limit is invalid. Ask an administrator."))
    lines = RequestMaterialItem.objects.filter(request_id__in=requests.values("pk")).count()
    if lines > limit or movements.count() > limit - lines:
        raise ValidationError(_("The Excel export exceeds %(limit)s rows. Narrow the filters and try again.") % {"limit": limit})
    return limit


def enforce_loaded_size(requests, movements, limit):
    if sum(len(request.material_items.all()) for request in requests) + len(movements) > limit:
        raise ValidationError(_("The Excel export exceeds %(limit)s rows. Narrow the filters and try again.") % {"limit": limit})


def add_movements(workbook, movements, requests):
    sheet = workbook.create_sheet(_("Stock Movements"))
    sheet.append([_("Stock movement scope")])
    sheet.append([_("Movements linked to the filtered approved requests. Unlinked movements appear only without request filters. Times: Africa/Kinshasa.")])
    headers = [_("Movement Date (Africa/Kinshasa)"), _("Material"), _("Material Code"), _("Category"),
               _("Movement Type"), _("Quantity"), _("Unit"), _("Request Number"), _("Actor"),
               _("BC Reference"), _("BS Reference")]
    sheet.append(headers)
    refmap = {request.pk: references(request) for request in requests}
    for movement in movements:
        material = movement.material
        refs = refmap.get(movement.request_id, {})
        actor = movement.performed_by
        sheet.append([reporting_time(movement.created_at), material.name, material.code, material.category.name,
            _(movement.get_movement_type_display()), movement.quantity, material.unit,
            movement.request.request_number if movement.request_id else _("No linked request"),
            (actor.full_name or actor.username) if actor else _("Actor unavailable"),
            refs.get("BC", _("Not issued")), refs.get("BS", _("Not issued"))])
    sheet.freeze_panes = "A4"
    sheet.auto_filter.ref = f"A3:K{sheet.max_row}"
    sheet.sheet_view.showGridLines = False
    for cell in sheet[3]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
    for column in "ABCDEFGHIJK":
        sheet.column_dimensions[column].width = 24
    for row in sheet:
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def protect_text_cells(workbook):
    """All text is literal, including strings openpyxl initially typed as formulas.

    No reporting sheet uses calculated cell formulas; charts refer to data ranges.
    Prefixes are preserved, not stripped or prepended with visible apostrophes.
    """
    for sheet in workbook:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
