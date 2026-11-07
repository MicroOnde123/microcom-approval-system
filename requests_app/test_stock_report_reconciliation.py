"""Operational reconciliation regressions; database tests use disposable PG."""
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest import TestCase as OfflineTestCase
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils.translation import override
from openpyxl import Workbook, load_workbook

from inventory.models import Material
from . import test_stock_report_analytics as analytics
from .models import Request, RequestMaterialItem, StockMovement, ReturnReceiptLine
from .stock_report_reconciliation import load_issuance_returns, add_issuance_returns, evidence_text


class ReconciliationOfflineTests(OfflineTestCase):
    def test_empty_french_sheet_and_authorization(self):
        user = SimpleNamespace(is_authenticated=True, is_active=True, is_superuser=True)
        with override('fr'):
            sheet = add_issuance_returns(Workbook(), user, [])
            self.assertEqual(sheet.title, 'Sorties et retours')
            self.assertEqual(sheet['A5'].value, 'Aucune donnée de rapprochement pour les demandes sélectionnées.')
        user.is_active = False
        with self.assertRaises(PermissionDenied):
            load_issuance_returns(user, [], [], 100, 0)
        with self.assertRaises(PermissionDenied):
            add_issuance_returns(Workbook(), user, [])

    def test_cell_limit_rejects_without_truncation(self):
        self.assertEqual(len(evidence_text(['x' * 32767])), 32767)
        with self.assertRaises(ValidationError):
            evidence_text(['x' * 32768])


class ReconciliationExportTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']
    export = analytics.StockReportAnalyticsTests.__dict__['export']

    def movement(self, req, kind, quantity, material=None):
        return StockMovement.objects.create(request=req, material=material or self.cable,
            movement_type=kind, quantity=Decimal(quantity), performed_by=self.user)

    def rows(self, **params):
        _, workbook = self.export(params or {'q': 'SEP-1'})
        return list(workbook['Issuance and Returns'].values)[4:]

    def test_missing_out_evidence_is_not_recorded_zero(self):
        rows = self.rows()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][11:16], (5, 0, 0, 0, 'Missing OUT evidence'))
        self.assertEqual(rows[0][19], 'Missing OUT evidence')
        req = Request.objects.get(request_number='SEP-1')
        self.movement(req, 'OUT', '0')
        row = self.rows()[0]
        self.assertEqual(row[15], 'Recorded zero OUT total')
        self.assertIn('Non-positive movement quantity', row[19])

    def test_full_partial_and_multiple_issue_and_return_totals(self):
        req = Request.objects.get(request_number='SEP-1')
        first = self.movement(req, 'OUT', '2.25')
        self.assertEqual(self.rows()[0][19], 'Partial issuance')
        second = self.movement(req, 'OUT', '2.75')
        self.assertEqual(self.rows()[0][19], 'Issued; no returns recorded')
        a = self.movement(req, 'RETURN', '1.10')
        b = self.movement(req, 'RETURN', '0.15')
        row = self.rows()[0]
        self.assertEqual(row[11:15], (5, 5, 1.25, 3.75))
        self.assertEqual(row[16], f'{first.pk}; {second.pk}')
        self.assertEqual(row[17], f'{a.pk}; {b.pk}')
        self.assertEqual(row[19], 'Partially returned')
        self.movement(req, 'RETURN', '3.75')
        row = self.rows()[0]
        self.assertEqual(row[12:15], (5, 5, 0))
        self.assertEqual(row[19], 'Fully returned')

    def test_excess_returns_and_missing_approval_material_are_explicit(self):
        req = Request.objects.get(request_number='SEP-1')
        self.movement(req, 'OUT', '6')
        self.movement(req, 'RETURN', '7')
        extra = Material.objects.create(category=self.cable.category, code='REC-EXTRA', name='Not approved', unit='m')
        self.movement(req, 'OUT', '1', extra)
        rows = self.rows()
        self.assertEqual(rows[0][14], -1)
        self.assertIn('Returns exceed recorded issuance', rows[0][19])
        self.assertIn('Issued quantity exceeds approved quantity', rows[0][19])
        unknown = next(row for row in rows if row[8] == extra.code)
        self.assertEqual(unknown[11], 'Not recorded')
        self.assertIn('No approved material line', unknown[19])

    def test_request_material_and_date_scope_separation(self):
        selected = Request.objects.get(request_number='SEP-1')
        outside = Request.objects.get(request_number='SEP-2')
        self.movement(selected, 'OUT', '5')
        self.movement(selected, 'OUT', '2', self.bolt)
        self.movement(outside, 'OUT', '50')
        self.movement(None, 'RETURN', '99')
        rows = self.rows(q='SEP-1', date_from='2026-09-01', date_to='2026-09-01',
                         warehouse_movement_to='2000-01-01')
        self.assertEqual([row[12] for row in rows], [5, 2])
        self.assertEqual({row[0] for row in rows}, {'SEP-1'})
        self.assertEqual({row[10] for row in rows}, {'m', 'pcs'})

    def test_duplicate_input_movements_and_repeated_request_lines(self):
        req = Request.objects.select_related('department', 'request_for_department', 'succursale').get(request_number='SEP-1')
        movement = self.movement(req, 'OUT', '5')
        RequestMaterialItem.objects.create(request=req, material=self.cable, quantity=1)
        req = Request.objects.prefetch_related('material_items__material').get(pk=req.pk)
        rows = load_issuance_returns(self.user, [req], [movement, movement], 100, 0)
        cable = next(row for row in rows if row['material'].pk == self.cable.pk)
        self.assertEqual(cable['quantity'].approved, 6)
        self.assertEqual(cable['quantity'].issued, 5)
        self.assertEqual(cable['out_ids'], str(movement.pk))
        self.assertIn('Repeated material lines', cable['status'])

    def test_verified_return_receipt_references_and_bad_links(self):
        from .material_outcomes import issue_receipt
        req = Request.objects.get(request_number='SEP-1')
        req.stock_deducted = True; req.save(update_fields=['stock_deducted'])
        self.movement(req, 'OUT', '5')
        self.movement(req, 'OUT', '2', self.bolt)
        returned = self.movement(req, 'RETURN', '1')
        receipt = issue_receipt(req.pk, self.user, [returned.pk], uuid4())
        self.assertEqual(self.rows()[0][18], f'{returned.pk}: {receipt.reference}')
        # Append-only receipt guards stay enabled. Simulate malformed legacy
        # query evidence rather than editing a protected historical record.
        with patch('requests_app.stock_report_reconciliation.ReturnReceiptLine.objects.filter') as lookup:
            lookup.return_value.order_by.return_value.values.return_value = [dict(
                movement_id=returned.pk, quantity=Decimal('2'), receipt__request_id=req.pk,
                receipt__reference=receipt.reference)]
            row = self.rows()[0]
        self.assertEqual(row[18], 'Not recorded')
        self.assertIn('Unverified return document link', row[19])
        self.assertEqual(row[13], 1)
        self.assertEqual(ReturnReceiptLine.objects.get(movement=returned).quantity, 1)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=6)
    def test_reconciliation_detail_budget_exact_boundary(self):
        self.export({'q': 'SEP-1'})  # 2 request + 2 inventory + 2 reconciliation.
        with override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=5):
            from django.urls import reverse
            response = self.client.get(reverse('export_material_report_excel'), {'q': 'SEP-1'}, HTTP_HOST='127.0.0.1')
            self.assertEqual(response.status_code, 413)

    def test_french_literal_text_no_financial_fields_and_read_only(self):
        # Request references are immutable; supply malicious text at creation.
        from datetime import date
        self.make_request('=REC-INJECTION', self.destination, date(2026, 9, 1), [(self.cable, 1)])
        _, workbook = self.export({'q': '=REC-INJECTION'}, language='fr')
        sheet = workbook['Sorties et retours']
        self.assertEqual(sheet['A5'].value, '=REC-INJECTION')
        self.assertEqual(sheet['A5'].data_type, 's')
        self.assertEqual(sheet['P5'].value, 'Preuve OUT manquante')
        self.assertEqual(sheet['C5'].number_format, 'dd/mm/yyyy')
        self.assertEqual(sheet.max_column, 21)
        self.assertNotIn('Comptabilité interne', workbook.sheetnames)
        from .views import export_material_report_excel
        request = RequestFactory().get('/')
        request.user = self.user
        before = list(Material.objects.order_by('pk').values())
        with override('en'), CaptureQueriesContext(connection) as queries:
            response = export_material_report_excel(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertEqual(before, list(Material.objects.order_by('pk').values()))
        self.assertEqual(StockMovement.objects.count(), 0)
