"""Current inventory worksheet regressions; disposable PostgreSQL only."""
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase as OfflineTestCase
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils.translation import override
from openpyxl import Workbook, load_workbook

from inventory.models import Material
from . import test_stock_report_analytics as analytics
from .models import StockMovement
from .stock_report_export import protect_text_cells
from .stock_report_inventory import add_current_inventory


class InventoryWorkbookOfflineTests(OfflineTestCase):
    def test_empty_inventory_translations_and_no_summary_budget(self):
        user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        for language, title, empty in [('en', 'Current Stock Inventory', 'No materials in the current inventory.'),
                                       ('fr', 'Stock actuel', 'Aucun matériel dans le stock actuel.')]:
            with self.subTest(language=language), override(language), override_settings(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=0):
                workbook = Workbook()
                sheet = add_current_inventory(workbook, user, [])
                self.assertEqual(sheet.title, title)
                self.assertEqual(sheet['A5'].value, empty)
                self.assertFalse(hasattr(workbook, '_stock_report_summary_budget'))

    def test_builder_authorization(self):
        for active, stock in [(False, True), (True, False)]:
            user = SimpleNamespace(is_authenticated=True, is_active=active, is_superuser=False, can_manage_stock=stock)
            with self.assertRaises(PermissionDenied):
                add_current_inventory(Workbook(), user, [])


class InventoryExportTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']
    export = analytics.StockReportAnalyticsTests.__dict__['export']

    def test_current_quantities_inactive_materials_and_status_boundaries(self):
        Material.objects.filter(pk=self.cable.pk).update(stock_quantity=100, minimum_stock_level=100)
        Material.objects.filter(pk=self.bolt.pk).update(stock_quantity=0, minimum_stock_level=0)
        inactive = Material.objects.create(category=self.cable.category, code='INV-INACTIVE', name='Inactive material',
            unit='m', is_active=False, stock_quantity=Decimal('1.25'), minimum_stock_level=2)
        Material.objects.create(category=self.cable.category, code='INV-NEGATIVE', name='Legacy negative stock',
            stock_quantity=-1)
        Material.objects.create(category=self.cable.category, code='INV-OK', name='Available material',
            stock_quantity=10, minimum_stock_level=3)
        # Even an empty request/date cohort cannot hide current warehouse stock.
        _, workbook = self.export({'q': 'no-matching-request', 'date_from': '2030-01-01',
                                  'warehouse_movement_to': '2000-01-01', 'warehouse_receipt_to': '2000-01-01'})
        sheet = workbook['Current Stock Inventory']
        rows = {row[0]: row for row in list(sheet.values)[4:]}
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[self.cable.code][5:], (100, 100, 'Low stock'))
        self.assertEqual(rows[self.bolt.code][5:], (0, 0, 'Out of stock'))
        self.assertEqual(rows[inactive.code][4:], ('Inactive', 1.25, 2, 'Low stock'))
        self.assertEqual(rows['INV-NEGATIVE'][7], 'Negative stock')
        self.assertEqual(rows['INV-OK'][7], 'In stock')
        self.assertEqual(sheet['C5'].value, self.cable.category.name)
        self.assertEqual(sheet.freeze_panes, 'A5')
        self.assertEqual(sheet.auto_filter.ref, 'A4:H9')
        self.assertEqual(sheet['F5'].number_format, '#,##0.00')

    def test_prices_are_neither_selected_by_inventory_nor_exported(self):
        Material.objects.create(category=self.cable.category, code='INV-PRICED', name='Price confidentiality fixture',
            unit_price=Decimal('98765.43'), currency='EUR', stock_quantity=3)
        with CaptureQueriesContext(connection) as queries:
            _, workbook = self.export()
        sheet = workbook['Current Stock Inventory']
        self.assertEqual(sheet.max_column, 8)
        for row in sheet:
            for cell in row:
                self.assertNotEqual(cell.value, 98765.43)
                self.assertNotEqual(cell.value, 'EUR')
        inventory_queries = [q['sql'] for q in queries if 'minimum_stock_level' in q['sql'] and 'SELECT' in q['sql']
                             and 'inventory_material"."description' not in q['sql']]
        self.assertTrue(inventory_queries)
        self.assertTrue(any('unit_price' not in query and 'currency' not in query for query in inventory_queries))
        self.assertNotIn('Bookkeeping', workbook.sheetnames)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=6)
    def test_inventory_uses_shared_detail_budget_at_boundary(self):
        # Two request lines + two inventory rows + two reconciliation rows.
        self.export({'q': 'SEP-1'})
        Material.objects.create(category=self.cable.category, code='INV-OVER', name='One over limit')
        self.client.force_login(self.user)
        from django.urls import reverse
        response = self.client.get(reverse('export_material_report_excel'), {'q': 'SEP-1'}, HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code, 413)
        self.assertIn('Narrow the filters', response.content.decode())

    def test_read_only_bounded_queries_and_no_stock_reconstruction(self):
        self.client.force_login(self.user)
        self.user.has_perm('invoicing.view_invoice')
        from django.test import RequestFactory
        from .views import export_material_report_excel
        request = RequestFactory().get('/materials/reports/export-excel/')
        request.user = self.user
        before = list(Material.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as small:
            response = export_material_report_excel(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(before, list(Material.objects.order_by('pk').values()))
        self.assertEqual(StockMovement.objects.count(), 0)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in small))
        for index in range(15):
            Material.objects.create(category=self.cable.category, code=f'INV-SCALE-{index}', name='Scale fixture', stock_quantity=3)
        with CaptureQueriesContext(connection) as large:
            response = export_material_report_excel(request)
        self.assertEqual(len(small), len(large))
        self.assertEqual(load_workbook(BytesIO(response.content))['Current Stock Inventory'].max_row, 21)

    def test_french_and_formula_injection_protection(self):
        Material.objects.filter(pk=self.cable.pk).update(name='=HYPERLINK("https://invalid","x")', minimum_stock_level=100)
        _, workbook = self.export(language='fr')
        sheet = workbook['Stock actuel']
        self.assertEqual(sheet['F4'].value, 'Quantité actuelle')
        self.assertEqual(sheet['E5'].value, 'Actif')
        self.assertEqual(sheet['H5'].value, 'Stock faible')
        self.assertEqual(sheet['B5'].data_type, 's')
        for tab in workbook:
            for row in tab:
                for cell in row:
                    self.assertNotEqual(cell.data_type, 'f')
