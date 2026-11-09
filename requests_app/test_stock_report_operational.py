"""Stage 3D operational scope, chart and confidentiality regressions."""
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from unittest import TestCase as OfflineTestCase

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils.translation import override
from openpyxl import Workbook, load_workbook

from inventory.entry_services import receive_stock, new_token
from inventory.models import Material, MaterialReceiptLine
from . import test_stock_report_analytics as analytics
from .models import Request, StockMovement
from .stock_report_operational import operational_data, load_warehouse_movements
from .stock_report_entries import receipt_material
from . import test_stock_bookkeeping_offline as financial_tests


def metrics(workbook, title='Dashboard'):
    return {row[0]: row[8] for row in workbook[title].iter_rows(min_col=1, max_col=9, values_only=True)
            if isinstance(row[0], str) and isinstance(row[8], int)}


class OperationalOfflineTests(OfflineTestCase):
    def test_receipt_details_and_analytics_share_legacy_fallback(self):
        row = dict(snapshot_version=1, snapshot_code='OLD', snapshot_name='Recorded',
            snapshot_category_name='Recorded group', snapshot_unit='m',
            material__code='NOW', material__name='Current', material__category__name='Current group', material__unit='pcs')
        self.assertEqual(receipt_material(row), (['OLD', 'Recorded', 'Recorded group', 'm'], True))
        row['snapshot_name'] = None
        self.assertEqual(receipt_material(row), (['NOW', 'Current', 'Current group', 'pcs'], False))

    def test_duplicate_movement_and_receipt_ids_are_not_counted_twice(self):
        move = dict(pk=1, movement_type='OUT', created_at=datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc))
        line = dict(pk=1, receipt_id=1, receipt__received_on=datetime(2026, 12, 31))
        data = operational_data([], [], [line, line], [], [move, move])
        self.assertEqual(data['movements']['2027-01']['OUT'], 1)
        self.assertEqual(data['receipts']['2026-12']['lines'], 1)
        self.assertEqual(len(data['receipts']['2026-12']['receipts']), 1)

    def test_frozen_financial_totals_only_in_bookkeeping(self):
        helper = financial_tests.BookkeepingOfflineTests()
        req, financial = helper.data(amount=Decimal('876543.21'))
        workbook = helper.workbook(req, financial)
        self.assertIn(('2027-01', 'Known Authorized Invoice Totals', 'USD', 876543.21),
                      financial_tests.financial_rows(workbook, 'Monthly Statistics'))
        for sheet in workbook:
            if sheet.title != 'Bookkeeping':
                for row in sheet:
                    for cell in row:
                        self.assertNotEqual(cell.value, 876543.21)
                        self.assertNotEqual(cell.value, 'USD')


class OperationalExportTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']
    export = analytics.StockReportAnalyticsTests.__dict__['export']

    def evidence(self):
        req = Request.objects.get(request_number='SEP-1')
        Material.objects.filter(pk=self.cable.pk).update(minimum_stock_level=100)
        Material.objects.filter(pk=self.bolt.pk).update(stock_quantity=0, minimum_stock_level=1, is_active=False)
        Material.objects.create(category=self.cable.category, code='OPS-NEG', name='Legacy negative', unit='pcs', stock_quantity=-1)
        receipt = receive_stock(user=self.user, mode='existing', token=new_token(self.user, 'existing'),
            material_id=self.cable.pk, receipt_data={'quantity': '2.50', 'received_on': '2026-12-31'})[0]
        movements = []
        for request, kind, quantity in [(req, 'OUT', '3'), (req, 'OUT', '2'), (req, 'RETURN', '1'), (None, 'OUT', '7')]:
            movement = StockMovement.objects.create(request=request, material=self.cable, movement_type=kind, quantity=Decimal(quantity))
            StockMovement.objects.filter(pk=movement.pk).update(created_at=datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc))
            movements.append(movement)
        params = dict(q='SEP-1', warehouse_receipt_from='2026-12-31', warehouse_receipt_to='2026-12-31',
                      warehouse_movement_from='2027-01-01', warehouse_movement_to='2027-01-01')
        return receipt, movements, params

    def test_dashboard_scope_counts_match_detail_evidence(self):
        receipt, movements, params = self.evidence()
        _, workbook = self.export(params)
        values = metrics(workbook)
        expected = {'Approved Material Requests': 1, 'Approved Material Lines': 2,
            'Total catalogue materials': 3, 'Active materials': 2, 'Inactive materials': 1,
            'Materials strictly below minimum stock': 2, 'Materials with zero stock': 1,
            'Receipt transactions': 1, 'Received material lines': 1,
            'Physical OUT movement count': 3, 'Physical RETURN movement count': 1,
            'Requests with recorded issuance': 1,
            'Requests missing OUT evidence on at least one approved material': 1,
            'Requests with recorded returns': 1, 'Reconciliation exception rows': 1}
        for label, value in expected.items():
            self.assertEqual(values[label], value, label)
        self.assertEqual(workbook['Material Entries'].max_row - 4, values['Received material lines'])
        self.assertEqual(workbook['Current Stock Inventory'].max_row - 4, values['Total catalogue materials'])
        self.assertEqual(workbook['Material Report'].max_row - 4, values['Approved Material Lines'])

    def test_monthly_quantities_and_charts_use_correct_dates_and_units(self):
        _, _, params = self.evidence()
        _, workbook = self.export(params)
        monthly = list(workbook['Monthly Statistics'].values)
        self.assertIn(('2026-12', 'Receipt transactions — receipt dates', None, 1), monthly)
        self.assertIn(('2026-12', 'Received quantity — receipt dates', 'm', 2.5), monthly)
        self.assertIn(('2027-01', 'Issued quantity — warehouse movement dates', 'm', 12), monthly)
        self.assertIn(('2027-01', 'Returned quantity — warehouse movement dates', 'm', 1), monthly)
        self.assertIn(('2027-01', 'Net issued — warehouse movement dates', 'm', 11), monthly)
        graphs = workbook['Graphs']
        self.assertEqual(graphs.cell(2, 48).value, '2027-01')
        self.assertEqual([graphs.cell(2, col).value for col in (49, 50)], [3, 1])
        self.assertEqual([graphs.cell(2, col).value for col in (44, 45, 46)], ['2026-12', 1, 1])
        self.assertEqual(graphs.cell(2, 36).value, 1)  # Mixed-unit demand: request count, not 5 meters.
        self.assertEqual(len(graphs._charts), 8)
        for chart in graphs._charts[4:]:
            self.assertEqual(chart.y_axis.numFmt.formatCode, '0')
            self.assertFalse(chart.visible_cells_only)
            self.assertIsNotNone(chart.series[0].cat.strRef)

    def test_warehouse_dates_do_not_truncate_request_reconciliation(self):
        _, _, params = self.evidence()
        params['warehouse_movement_from'] = '2000-01-01'; params['warehouse_movement_to'] = '2000-01-01'
        params['warehouse_receipt_from'] = '2000-01-01'; params['warehouse_receipt_to'] = '2000-01-01'
        _, workbook = self.export(params)
        values = metrics(workbook)
        self.assertEqual(values['Physical OUT movement count'], 0)
        self.assertEqual(values['Receipt transactions'], 0)
        self.assertEqual(values['Requests with recorded issuance'], 1)
        self.assertEqual(values['Requests with recorded returns'], 1)
        self.assertEqual(workbook['Issuance and Returns']['O5'].value, 4)
        self.assertEqual(values['Total catalogue materials'], 3)

    def test_shared_budget_charges_only_new_warehouse_ids(self):
        req = Request.objects.get(request_number='SEP-1')
        existing = StockMovement.objects.create(request=req, material=self.cable, movement_type='OUT', quantity=1)
        outside = StockMovement.objects.create(material=self.cable, movement_type='RETURN', quantity=1)
        with CaptureQueriesContext(connection) as queries:
            rows, additional = load_warehouse_movements(self.user, Request.objects.filter(pk=req.pk), {}, [existing], 2, 1)
        self.assertEqual(len(queries), 2)
        self.assertEqual(additional, 1)
        self.assertEqual({row['pk'] for row in rows}, {existing.pk, outside.pk})
        with self.assertRaises(ValidationError):
            load_warehouse_movements(self.user, Request.objects.all(), {}, [existing], 1, 1)

    def test_stock_boundaries_and_multiple_receipt_lines(self):
        Material.objects.filter(pk=self.cable.pk).update(stock_quantity=100, minimum_stock_level=100)
        _, workbook = self.export({'q': 'no-request'})
        self.assertEqual(metrics(workbook)['Materials strictly below minimum stock'], 0)
        receipt = receive_stock(user=self.user, mode='existing', token=new_token(self.user, 'existing'),
            material_id=self.cable.pk, receipt_data={'quantity': '1', 'received_on': '2026-01-01'})[0]
        move = StockMovement.objects.create(material=self.bolt, movement_type='IN', quantity=1)
        MaterialReceiptLine.objects.create(receipt=receipt, material=self.bolt, quantity=1, stock_after=101, movement=move)
        Material.objects.filter(pk=self.bolt.pk).update(stock_quantity=101)
        _, workbook = self.export({'q': 'no-request'})
        self.assertEqual(metrics(workbook)['Receipt transactions'], 1)
        self.assertEqual(metrics(workbook)['Received material lines'], 2)

    def test_summary_and_chart_limits_http_413(self):
        from django.urls import reverse
        _, _, params = self.evidence()
        self.client.force_login(self.user)
        for options in [dict(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=1), dict(STOCK_REPORT_EXPORT_MAX_CHART_ROWS=1),
                        dict(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=30), dict(STOCK_REPORT_EXPORT_MAX_CHART_ROWS=6)]:
            with self.subTest(options=options), override_settings(**options):
                response = self.client.get(reverse('export_material_report_excel'), params, HTTP_HOST='127.0.0.1')
                self.assertEqual(response.status_code, 413)

    def test_french_read_only_and_financial_confidentiality(self):
        _, _, params = self.evidence()
        Material.objects.create(category=self.cable.category, code='OPS-PRICE', name='=PRIVATE-PRICE',
            unit_price=Decimal('765432.10'), currency='EUR')
        _, workbook = self.export(params, language='fr')
        self.assertEqual(metrics(workbook, 'Tableau de bord')['Transactions de réception'], 1)
        self.assertIn('Périmètres indépendants', workbook['Graphiques']['A45'].value)
        self.assertNotIn('Comptabilité interne', workbook.sheetnames)
        for sheet in workbook:
            for row in sheet:
                for cell in row:
                    self.assertNotEqual(cell.value, 765432.1)
                    self.assertNotEqual(cell.value, 'EUR')
                    self.assertNotEqual(cell.data_type, 'f')
        from .views import export_material_report_excel
        request = RequestFactory().get('/', params); request.user = self.user
        before = list(Material.objects.order_by('pk').values())
        with override('en'), CaptureQueriesContext(connection) as queries:
            response = export_material_report_excel(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertEqual(before, list(Material.objects.order_by('pk').values()))
