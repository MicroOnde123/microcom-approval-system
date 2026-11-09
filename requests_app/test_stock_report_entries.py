"""Receipt worksheet evidence on disposable local PostgreSQL only."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase as OfflineTestCase

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.test import TestCase, override_settings, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils.translation import override
from openpyxl import Workbook, load_workbook

from inventory.entry_services import new_token, receive_stock
from inventory.models import Material, MaterialReceipt, MaterialReceiptLine
from . import test_stock_report_analytics as analytics
from .models import Request, StockMovement
from .stock_report_entries import add_material_entries, load_material_entries


class EntriesOfflineTests(OfflineTestCase):
    def test_empty_sheet_and_builder_permissions(self):
        user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        with override('fr'):
            sheet = add_material_entries(Workbook(), user, [], {})
            self.assertEqual(sheet.title, 'Entrées de matériel')
            self.assertEqual(sheet['A5'].value, 'Aucune réception de matériel pour les dates sélectionnées.')
        user.is_active = False
        with self.assertRaises(PermissionDenied):
            add_material_entries(Workbook(), user, [], {})


class EntriesExportTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']
    export = analytics.StockReportAnalyticsTests.__dict__['export']

    def receipt(self, quantity='1.25', received_on='2026-02-01', material=None):
        return receive_stock(user=self.user, mode='existing', token=new_token(self.user, 'existing'),
            material_id=(material or self.cable).pk, receipt_data={
                'quantity': quantity, 'received_on': received_on, 'supplier': '=SUPPLIER',
                'delivery_reference': '+DELIVERY', 'notes': '=NOTE'})[0]

    def test_multiple_receipts_business_dates_and_request_filter_independence(self):
        first = self.receipt()
        self.receipt('2.50', '2026-02-02')
        self.receipt('3', '2026-01-31')
        Material.objects.filter(pk=self.cable.pk).update(is_active=False, name='Current renamed material', stock_quantity=999)
        _, workbook = self.export({'q': 'no-request-matches', 'department': self.destination.pk,
            'date_from': '2030-01-01', 'warehouse_receipt_from': '2026-02-01',
            'warehouse_receipt_to': '2026-02-02', 'warehouse_movement_to': '2000-01-01'})
        sheet = workbook['Material Entries']
        rows = list(sheet.values)[4:]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], first.reference)
        self.assertEqual(rows[0][1].date(), date(2026, 2, 1))
        self.assertEqual(rows[0][4], 'Cable')
        self.assertEqual(rows[0][7:9], (1.25, 101.25))
        self.assertEqual(rows[1][7], 2.5)
        self.assertEqual(rows[0][9], 'Existing material')
        self.assertEqual(rows[0][10], first.lines.get().movement_id)
        self.assertEqual(rows[0][12], 1.25)
        self.assertEqual(rows[0][13], self.user.username)
        self.assertEqual(rows[0][17:], ('Recorded material snapshot', 'Linked IN movement'))
        self.assertEqual(sheet.freeze_panes, 'A5')
        self.assertEqual(sheet.auto_filter.ref, 'A4:S6')
        from .stock_report_export import reporting_time
        self.assertEqual(rows[0][2], reporting_time(first.created_at))

    def test_multiple_lines_on_one_receipt_preserve_each_movement(self):
        receipt = self.receipt()
        movement = StockMovement.objects.create(material=self.bolt, movement_type='IN', quantity=Decimal('0.25'))
        MaterialReceiptLine.objects.create(receipt=receipt, material=self.bolt, quantity=Decimal('0.25'),
            stock_after=Decimal('100.25'), movement=movement)
        Material.objects.filter(pk=self.bolt.pk).update(stock_quantity=Decimal('100.25'))
        _, workbook = self.export()
        rows = list(workbook['Material Entries'].values)[4:]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row[0] for row in rows}, {receipt.reference})
        self.assertEqual({row[10] for row in rows}, {movement.pk, receipt.lines.first().movement_id})
        self.assertEqual(rows[1][3:8], (self.bolt.code, self.bolt.name, self.bolt.category.name, 'pcs', 0.25))

    def test_legacy_missing_snapshots_and_transaction_type_are_explicit(self):
        receipt = self.receipt()
        MaterialReceipt.objects.filter(pk=receipt.pk).update(transaction_type=None)
        MaterialReceiptLine.objects.filter(receipt=receipt).update(material_snapshot=None)
        _, workbook = self.export()
        row = list(workbook['Material Entries'].values)[4]
        self.assertEqual(row[9], 'Not recorded')
        self.assertEqual(row[17], 'Current catalogue fallback; historical material details not recorded')
        # Legacy IN with no receipt is not invented into a receipt row.
        StockMovement.objects.create(material=self.bolt, movement_type='IN', quantity=7)
        _, workbook = self.export()
        self.assertEqual(workbook['Material Entries'].max_row, 5)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=4)
    def test_shared_budget_counts_receipt_line_but_not_linked_movement_twice(self):
        self.receipt()
        # Empty request cohort: 2 inventory rows + 1 receipt line; unlinked IN
        # is excluded from the existing request-filtered movement sheet.
        self.export({'q': 'no-match'})
        # Unfiltered: 6 approved lines + movement + inventory + receipt exceed 4.
        from django.urls import reverse
        self.client.force_login(self.user)
        response = self.client.get(reverse('export_material_report_excel'), HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code, 413)
        with override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=16):
            # 6 request lines + 1 movement + 2 inventory + 1 receipt + 6 reconciliation.
            self.export()
        with override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=15):
            self.assertEqual(self.client.get(reverse('export_material_report_excel'), HTTP_HOST='127.0.0.1').status_code, 413)

    def test_read_only_price_confidentiality_and_query_count(self):
        self.receipt()
        with CaptureQueriesContext(connection) as small:
            rows = load_material_entries(self.user, Request.objects.all(), {}, 100, 0)
        self.assertEqual(len(small), 2)
        self.assertFalse(any('unit_price' in query['sql'] or 'currency' in query['sql'] for query in small))
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in small))
        self.assertFalse(any('material_snapshot' == key for key in rows[0]))
        for _ in range(4):
            self.receipt()
        with CaptureQueriesContext(connection) as large:
            load_material_entries(self.user, Request.objects.all(), {}, 100, 0)
        self.assertEqual(len(large), len(small))
        # Capture after synthetic setup: exports must change none of this evidence.
        stock = list(Material.objects.order_by('pk').values())
        receipts = list(MaterialReceipt.objects.values())
        from .views import export_material_report_excel
        request = RequestFactory().get('/materials/reports/export-excel/')
        request.user = self.user
        with CaptureQueriesContext(connection) as queries:
            response = export_material_report_excel(request)
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        self.assertEqual(stock, list(Material.objects.order_by('pk').values()))
        self.assertEqual(receipts, list(MaterialReceipt.objects.values()))
        self.assertEqual(workbook['Material Entries'].max_column, 19)
        self.assertNotIn('Bookkeeping', workbook.sheetnames)

    def test_french_formula_protection_and_missing_metadata(self):
        receipt = self.receipt()
        MaterialReceipt.objects.filter(pk=receipt.pk).update(transaction_type=None)
        _, workbook = self.export(language='fr')
        sheet = workbook['Entrées de matériel']
        self.assertEqual(sheet['A4'].value, 'Référence de réception')
        self.assertEqual(sheet['B5'].number_format, 'dd/mm/yyyy')
        self.assertEqual(sheet['H5'].number_format, '#,##0.00')
        self.assertEqual(sheet['J5'].value, 'Non enregistré')
        for column in ('O', 'P', 'Q'):
            self.assertEqual(sheet[f'{column}5'].data_type, 's')
        self.assertEqual(sheet['O5'].value, '=SUPPLIER')

    def test_inconsistent_linked_movement_is_flagged_without_repair(self):
        receipt = self.receipt()
        movement = receipt.lines.get().movement
        StockMovement.objects.filter(pk=movement.pk).update(quantity=9)
        _, workbook = self.export()
        self.assertEqual(workbook['Material Entries']['S5'].value, 'Inconsistent linked movement evidence')
        movement.refresh_from_db()
        self.assertEqual(movement.quantity, 9)
