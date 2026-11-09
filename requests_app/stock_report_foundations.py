"""Read-only reporting scopes, quantity evidence and bounded export planning.

Request dates mean Date Needed. Warehouse receipt dates mean received_on;
movement dates mean created_at in Africa/Kinshasa. Inventory is current, never
an inferred historical balance. These scopes must not be intersected implicitly.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django import forms
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.db.models.fields.json import KeyTransform
from django.utils.translation import gettext as _, gettext_lazy

ZONE = ZoneInfo('Africa/Kinshasa')


class WarehouseActivityFilterForm(forms.Form):
    warehouse_receipt_from = forms.DateField(required=False, input_formats=['%Y-%m-%d'])
    warehouse_receipt_to = forms.DateField(required=False, input_formats=['%Y-%m-%d'])
    warehouse_movement_from = forms.DateField(required=False, input_formats=['%Y-%m-%d'])
    warehouse_movement_to = forms.DateField(required=False, input_formats=['%Y-%m-%d'])

    def clean(self):
        data = super().clean()
        for kind in ('receipt', 'movement'):
            start, end = (data.get(f'warehouse_{kind}_{part}') for part in ('from', 'to'))
            if start and end and start > end:
                self.add_error(f'warehouse_{kind}_to', gettext_lazy('The start date must not be after the end date.'))
        return data


def authorize_stock_reporting(user):
    if not (user.is_authenticated and user.is_active and
            (user.is_superuser or getattr(user, 'can_manage_stock', False))):
        raise PermissionDenied(_('You are not allowed to export material reports.'))


@dataclass(frozen=True)
class ReportingScopes:
    """Querysets expose operational evidence only; no prices or invoice joins.

    approved_requests must already carry the caller's existing request filters.
    Warehouse scopes intentionally do not use those filters. Consumers must use
    these projected fields rather than fetching unrestricted catalogue objects.
    """
    approved_requests: object
    receipts: object
    movements: object
    inventory: object


def reporting_scopes(user, approved_requests, warehouse_filters):
    authorize_stock_reporting(user)
    from inventory.models import Material, MaterialReceiptLine
    from .models import StockMovement
    receipts = MaterialReceiptLine.objects.all()
    movements = StockMovement.objects.all()
    for part, lookup in (('from', 'gte'), ('to', 'lte')):
        value = warehouse_filters.get(f'warehouse_receipt_{part}')
        if value:
            receipts = receipts.filter(**{f'receipt__received_on__{lookup}': value})
    start = warehouse_filters.get('warehouse_movement_from')
    end = warehouse_filters.get('warehouse_movement_to')
    if start:
        movements = movements.filter(created_at__gte=datetime.combine(start, time.min, ZONE))
    if end:
        # Half-open next-day boundary, except the maximum representable date.
        if end.year == 9999 and end.month == 12 and end.day == 31:
            movements = movements.filter(created_at__lte=datetime.combine(end, time.max, ZONE))
        else:
            movements = movements.filter(created_at__lt=datetime.combine(end + timedelta(days=1), time.min, ZONE))
    return ReportingScopes(
        approved_requests=approved_requests.filter(status='APPROVED'),
        receipts=receipts.annotate(**{
            'snapshot_' + name: KeyTransform(name, 'material_snapshot')
            for name in ('version', 'code', 'name', 'category_name', 'category_code', 'unit')
        }).order_by('receipt__received_on', 'pk').values(
            'pk', 'receipt_id', 'material_id', 'quantity', 'stock_after', 'movement_id',
            'receipt__received_on', 'receipt__created_at', 'receipt__reference',
            'receipt__transaction_type', 'receipt__supplier', 'receipt__delivery_reference', 'receipt__notes',
            'receipt__created_by__full_name', 'receipt__created_by__username',
            'material__code', 'material__name', 'material__category__name', 'material__category__code', 'material__unit',
            'movement__movement_type', 'movement__quantity', 'movement__material_id',
            'snapshot_version', 'snapshot_code', 'snapshot_name', 'snapshot_category_name', 'snapshot_category_code', 'snapshot_unit'),
        movements=movements.order_by('created_at', 'pk').values(
            'pk', 'request_id', 'material_id', 'material__unit', 'material__code', 'material__name',
            'material__category__name', 'material__category__code', 'movement_type', 'quantity', 'created_at'),
        inventory=Material.objects.order_by('pk').values(
            'pk', 'name', 'code', 'category_id', 'category__name', 'category__code', 'unit', 'is_active', 'stock_quantity', 'minimum_stock_level'),
    )


@dataclass
class QuantityEvidence:
    approved: Decimal = Decimal('0')
    received: Decimal = Decimal('0')
    issued: Decimal = Decimal('0')
    returned: Decimal = Decimal('0')
    out_records: int = 0

    @property
    def net_issued(self):
        return self.issued - self.returned


def quantity_evidence(approved_rows, movement_rows):
    """Combine grouped primitive rows by (request_id, material_id, current unit).

    No unit conversion, prices, inferred movements or reconciliation-row inputs.
    An approved-only line has out_records=0, not proof of a zero-quantity issue.
    Null request IDs remain distinct warehouse evidence.
    """
    result = {}
    for row in approved_rows:
        key = (row['request_id'], row['material_id'], row['material__unit'])
        evidence = result.setdefault(key, QuantityEvidence())
        evidence.approved += row['quantity']
    fields = {'IN': 'received', 'OUT': 'issued', 'RETURN': 'returned'}
    for row in movement_rows:
        key = (row['request_id'], row['material_id'], row['material__unit'])
        evidence = result.setdefault(key, QuantityEvidence())
        name = fields[row['movement_type']]
        setattr(evidence, name, getattr(evidence, name) + row['quantity'])
        if name == 'issued':
            evidence.out_records += row['records']
    return result


def aggregate_quantities(user, approved_items, movements):
    """Two grouped SELECTs over explicitly scoped querysets; no related loads."""
    authorize_stock_reporting(user)
    approved = approved_items.filter(request__status='APPROVED').order_by().values('request_id', 'material_id', 'material__unit').annotate(quantity_total=Sum('quantity'))
    recorded = movements.order_by().values('request_id', 'material_id', 'material__unit', 'movement_type').annotate(
        quantity_total=Sum('quantity'), records=Count('pk'))
    return quantity_evidence(
        ({**row, 'quantity': row['quantity_total']} for row in approved),
        ({**row, 'quantity': row['quantity_total']} for row in recorded),
    )


def request_material_reconciliation(user, approved_requests, movements):
    from .models import RequestMaterialItem
    approved = approved_requests.filter(status='APPROVED').values('pk')
    return aggregate_quantities(user,
        RequestMaterialItem.objects.filter(request_id__in=approved),
        movements.filter(request_id__in=approved))


def configured_limit(name='STOCK_REPORT_EXPORT_MAX_ROWS'):
    limit = getattr(settings, name, 10000)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1_000_000:
        raise ValidationError(_('The Excel export limit is invalid. Ask an administrator.'))
    return limit


@dataclass
class ExportBudget:
    limit: int
    counts: dict = field(default_factory=dict)

    def reserve(self, source, count):
        """Reserve each named source once; repeat reservations replace, not add."""
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError('Source row counts must be nonnegative integers.')
        proposed = {**self.counts, source: count}
        if sum(proposed.values()) > self.limit:
            raise ValidationError(_('The Excel export exceeds %(limit)s rows. Narrow the filters and try again.') % {'limit': self.limit})
        self.counts = proposed

    @property
    def remaining(self):
        return self.limit - sum(self.counts.values())


def plan_export_budget(*, request_items, movement_scopes=(), inventory=None,
                       receipt_lines=None, reconciliation_rows=0, financial_rows=0):
    """Count selected sources before loading; shared movement IDs count once.

    Receipt-line metadata is its own detail source, not a second movement.
    Stage 2 does not reserve unused future sheets in the existing export.
    """
    budget = ExportBudget(configured_limit())
    budget.reserve('request_items', request_items.count())
    scopes = list(movement_scopes)
    if scopes:
        ids = scopes[0].order_by().values_list('pk', flat=True).distinct()
        if len(scopes) > 1:
            ids = ids.union(*(scope.order_by().values_list('pk', flat=True) for scope in scopes[1:]))
        budget.reserve('movements', ids.count())
    for source, queryset in (('inventory', inventory), ('receipt_lines', receipt_lines)):
        if queryset is not None:
            budget.reserve(source, queryset.count())
    budget.reserve('reconciliation', reconciliation_rows)
    budget.reserve('financial', financial_rows)
    return budget


def reserve_generated(workbook, *, summary_rows=0, chart_rows=0):
    """Independent cumulative budgets for derived output, before writing it."""
    for kind, count in (('summary', summary_rows), ('chart', chart_rows)):
        attr = f'_stock_report_{kind}_budget'
        budget = getattr(workbook, attr, None)
        if budget is None:
            budget = ExportBudget(configured_limit(f'STOCK_REPORT_EXPORT_MAX_{kind.upper()}_ROWS'))
            setattr(workbook, attr, budget)
        budget.reserve('generated', budget.counts.get('generated', 0) + count)
