"""Grouped reporting evidence on disposable local PostgreSQL only."""
from datetime import date, datetime, timezone
from decimal import Decimal

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from inventory.entry_services import new_token, receive_stock
from inventory.models import MaterialReceipt, MaterialReceiptLine
from . import test_stock_report_analytics as analytics
from .models import Request, RequestMaterialItem, StockMovement
from .stock_report_foundations import (
    WarehouseActivityFilterForm, aggregate_quantities, reporting_scopes,
    plan_export_budget, request_material_reconciliation,
)


class FoundationsPostgreSQLTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']

    def test_receipt_date_and_movement_time_are_independent_of_request_filters(self):
        receipt, _ = receive_stock(user=self.user, mode='existing', token=new_token(self.user, 'existing'),
            material_id=self.cable.pk,
            receipt_data={'quantity': '2', 'received_on': '2026-02-01', 'supplier': 'Synthetic'})
        movement = receipt.lines.get().movement
        StockMovement.objects.filter(pk=movement.pk).update(created_at=datetime(2026, 1, 31, 23, 0, tzinfo=timezone.utc))
        form = WarehouseActivityFilterForm({'warehouse_receipt_from': '2026-02-01', 'warehouse_receipt_to': '2026-02-01',
                                          'warehouse_movement_from': '2026-02-01', 'warehouse_movement_to': '2026-02-01'})
        self.assertTrue(form.is_valid())
        selected = Request.objects.filter(request_number='SEP-1', date_needed__gte=date(2026, 9, 1))
        with CaptureQueriesContext(connection) as queries:
            scopes = reporting_scopes(self.user, selected, form.cleaned_data)
            self.assertEqual(list(scopes.receipts.values_list('receipt_id', flat=True)), [receipt.pk])
            self.assertEqual(list(scopes.movements.values_list('pk', flat=True)), [movement.pk])
            inventory = list(scopes.inventory)
        self.assertEqual(len(inventory), 2)
        self.assertFalse(any('unit_price' in row or 'currency' in row for row in inventory))
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        for instant, expected in [(datetime(2026, 1, 31, 22, 59, 59, tzinfo=timezone.utc), []),
                                  (datetime(2026, 2, 1, 22, 59, 59, tzinfo=timezone.utc), [movement.pk]),
                                  (datetime(2026, 2, 1, 23, 0, tzinfo=timezone.utc), [])]:
            StockMovement.objects.filter(pk=movement.pk).update(created_at=instant)
            self.assertEqual(list(reporting_scopes(self.user, selected, form.cleaned_data).movements.values_list('pk', flat=True)), expected)
        other = reporting_scopes(self.user, selected, {'warehouse_receipt_from': date(2026, 2, 2)})
        self.assertFalse(other.receipts.exists())
        self.assertEqual(other.inventory.count(), 2)

    def test_grouped_decimal_reconciliation_uses_two_reads_and_only_physical_evidence(self):
        selected = Request.objects.filter(request_number='SEP-1')
        req = selected.get()
        for kind, quantity in [('OUT', '4.25'), ('RETURN', '1.10'), ('RETURN', '0.15')]:
            StockMovement.objects.create(request=req, material=self.cable, movement_type=kind, quantity=Decimal(quantity))
        StockMovement.objects.create(material=self.cable, movement_type='IN', quantity=2)
        with CaptureQueriesContext(connection) as queries:
            evidence = request_material_reconciliation(self.user, selected, StockMovement.objects.all())
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        meters = evidence[(req.pk, self.cable.pk, 'm')]
        self.assertEqual((meters.approved, meters.issued, meters.returned, meters.net_issued),
                         tuple(map(Decimal, ['5', '4.25', '1.25', '3.00'])))
        self.assertEqual(evidence[(req.pk, self.bolt.pk, 'pcs')].out_records, 0)
        self.assertEqual(evidence[(req.pk, self.bolt.pk, 'pcs')].issued, 0)
        all_evidence = aggregate_quantities(self.user, RequestMaterialItem.objects.filter(request_id__in=selected), StockMovement.objects.all())
        self.assertEqual(all_evidence[(None, self.cable.pk, 'm')].received, 2)
        # No movement balance is invented from 100 units of catalogue stock.
        self.assertEqual(len(all_evidence), 3)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=3)
    def test_future_detail_budget_unions_shared_movement_ids_without_double_counting(self):
        req = Request.objects.get(request_number='SEP-1')
        movement = StockMovement.objects.create(request=req, material=self.cable, movement_type='OUT', quantity=1)
        items = RequestMaterialItem.objects.filter(request=req)
        scopes = [StockMovement.objects.filter(pk=movement.pk), StockMovement.objects.all()]
        with CaptureQueriesContext(connection) as queries:
            budget = plan_export_budget(request_items=items, movement_scopes=scopes)
        self.assertEqual(budget.counts['movements'], 1)
        self.assertEqual(budget.remaining, 0)
        self.assertEqual(len(queries), 2)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            plan_export_budget(request_items=items, movement_scopes=scopes, reconciliation_rows=1)
        with self.assertRaises(ValidationError):
            plan_export_budget(request_items=items, inventory=self.cable.__class__.objects.all())

    def test_legacy_movement_needs_no_receipt_or_current_stock_reconstruction(self):
        movement = StockMovement.objects.create(material=self.cable, movement_type='IN', quantity=Decimal('0.25'))
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertFalse(MaterialReceiptLine.objects.exists())
        scopes = reporting_scopes(self.user, Request.objects.none(), {})
        self.assertEqual(list(scopes.movements.values_list('pk', flat=True)), [movement.pk])
        self.assertFalse(scopes.receipts.exists())
