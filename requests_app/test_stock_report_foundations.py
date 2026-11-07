"""Stage 2 primitives: no database required."""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory, override_settings
from django.utils.translation import override
from openpyxl import Workbook

from .stock_report_foundations import (
    ExportBudget, WarehouseActivityFilterForm, aggregate_quantities,
    quantity_evidence, reserve_generated,
)
from . import test_stock_export_offline as offline
from .views import export_material_report_excel


class FoundationsOfflineTests(TestCase):
    def test_independent_date_ranges_and_impossible_dates(self):
        form = WarehouseActivityFilterForm({
            'date_from': 'not-a-request-date',
            'warehouse_receipt_from': '2026-02-01', 'warehouse_receipt_to': '2026-02-02',
            'warehouse_movement_from': '2026-03-01', 'warehouse_movement_to': '2026-03-02',
        })
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['warehouse_receipt_from'], date(2026, 2, 1))
        for kind in ('receipt', 'movement'):
            for start, end in [('2026-02-30', ''), ('2026-03-02', '2026-03-01')]:
                with self.subTest(kind=kind, start=start):
                    self.assertFalse(WarehouseActivityFilterForm({
                        f'warehouse_{kind}_from': start, f'warehouse_{kind}_to': end,
                    }).is_valid())
        self.assertTrue(WarehouseActivityFilterForm({}).is_valid())

    def test_decimal_units_partial_returns_and_missing_evidence(self):
        approved = [dict(request_id=1, material_id=1, material__unit='m', quantity=Decimal('10.25')),
                    dict(request_id=1, material_id=2, material__unit='pcs', quantity=Decimal('4'))]
        moves = [dict(request_id=1, material_id=1, material__unit='m', movement_type=kind,
                      quantity=Decimal(q), records=1)
                 for kind, q in [('OUT', '8.25'), ('RETURN', '1.10'), ('RETURN', '0.15'), ('IN', '2')]]
        values = quantity_evidence(approved, moves)
        meters = values[(1, 1, 'm')]
        self.assertEqual((meters.approved, meters.received, meters.issued, meters.returned, meters.net_issued),
                         tuple(map(Decimal, ['10.25', '2', '8.25', '1.25', '7.00'])))
        self.assertEqual(meters.out_records, 1)
        self.assertEqual(values[(1, 2, 'pcs')].out_records, 0)
        self.assertEqual(values[(1, 2, 'pcs')].issued, Decimal('0'))
        self.assertEqual(quantity_evidence([], []), {})

    def test_authorization_precedes_query_evaluation(self):
        from unittest.mock import MagicMock
        items, movements = MagicMock(), MagicMock()
        for active, stock in [(False, True), (True, False)]:
            user = SimpleNamespace(is_authenticated=True, is_active=active, is_superuser=False, can_manage_stock=stock)
            with self.assertRaises(PermissionDenied):
                aggregate_quantities(user, items, movements)
        items.order_by.assert_not_called(); movements.order_by.assert_not_called()

    def test_detail_boundary_repeat_reservations_and_rejection_are_atomic(self):
        budget = ExportBudget(3)
        budget.reserve('movements', 2); budget.reserve('movements', 2)
        budget.reserve('inventory', 1)
        self.assertEqual(budget.remaining, 0)
        with self.assertRaises(ValidationError):
            budget.reserve('receipts', 1)
        self.assertEqual(budget.remaining, 0)
        for invalid in (-1, True, 1.5):
            with self.assertRaises(ValueError):
                budget.reserve('invalid', invalid)

    @override_settings(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=2, STOCK_REPORT_EXPORT_MAX_CHART_ROWS=1)
    def test_generated_budgets_are_separate_and_cumulative(self):
        workbook = Workbook()
        reserve_generated(workbook, summary_rows=1, chart_rows=1)
        reserve_generated(workbook, summary_rows=1)
        with self.assertRaises(ValidationError):
            reserve_generated(workbook, summary_rows=1)
        with self.assertRaises(ValidationError):
            reserve_generated(workbook, chart_rows=1)

    def test_export_invalid_warehouse_dates_translated_before_queries(self):
        request = RequestFactory().get('/', {'warehouse_receipt_from': 'impossible'})
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=True)
        for language, message in [('en', 'Invalid warehouse activity dates.'),
                                  ('fr', 'Dates d’activité de l’entrepôt invalides.')]:
            with self.subTest(language=language), override(language), patch('requests_app.views.get_filtered_material_report_requests') as query:
                response = export_material_report_excel(request)
                self.assertEqual(response.status_code, 400)
                self.assertIn(message, response.content.decode())
                query.assert_not_called()

    @override_settings(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=1)
    def test_generated_limit_is_http_413(self):
        request = RequestFactory().get('/')
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=True)
        from . import stock_report_export as export
        from .test_stock_export_offline import fixture
        with patch('requests_app.views.get_filtered_material_report_requests', return_value=[fixture()]), \
             patch.object(export, 'movement_scope', return_value=[]), \
             patch('requests_app.stock_report_inventory.load_current_inventory', return_value=[]), \
             patch('requests_app.stock_report_entries.load_material_entries', return_value=[]), \
             patch('requests_app.stock_report_reconciliation.load_issuance_returns', return_value=[]), \
             patch('requests_app.stock_report_operational.load_warehouse_movements', return_value=([], 0)), \
             patch.object(export, 'enforce_size', return_value=100):
            response = export_material_report_excel(request)
        self.assertEqual(response.status_code, 413)

    def test_warehouse_parameters_do_not_change_existing_workbook_scope(self):
        helper = offline.StockExportOfflineTests()
        before = helper.render_export()
        after = helper.render_export(params={'warehouse_receipt_from': '2026-01-01',
                                             'warehouse_movement_to': '2026-12-31'})
        self.assertEqual(before.sheetnames, after.sheetnames)
        for name in ('Material Report', 'Stock Movements', 'Current Stock Inventory', 'Issuance and Returns'):
            self.assertEqual(list(before[name].values), list(after[name].values))
