"""Run only on the verified disposable local PostgreSQL database."""
from datetime import datetime, timezone
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from inventory.models import Succursale
from . import test_stock_report_analytics as analytics
from .models import Request, StockMovement, MaterialDocument, MaterialDocumentSequence
from .material_documents import issue_document
from .views import export_material_report_excel


class StockExportIntegrationTests(TestCase):
    setUpTestData = analytics.StockReportAnalyticsTests.__dict__['setUpTestData']
    make_request = analytics.StockReportAnalyticsTests.__dict__['make_request']
    export = analytics.StockReportAnalyticsTests.__dict__['export']

    def test_classification_and_existing_refs_preserved(self):
        req=Request.objects.get(request_number='SEP-1');req.stock_deducted=True;req.save(update_fields=['stock_deducted'])
        bc=issue_document(req.pk,'BC',self.user);bs=issue_document(req.pk,'BS',self.user)
        before=(MaterialDocument.objects.count(),list(MaterialDocumentSequence.objects.values_list('kind','year','last_counter')))
        _,wb=self.export({'q':'SEP-1'})
        self.assertEqual(wb.active['R5'].value,bc.reference);self.assertEqual(wb.active['S5'].value,bs.reference)
        self.assertEqual(before,(MaterialDocument.objects.count(),list(MaterialDocumentSequence.objects.values_list('kind','year','last_counter'))))
        self.assertEqual(wb.active['P5'].value,'Classification unavailable')

    def test_client_and_microcom_missing_history(self):
        req=Request.objects.get(request_number='SEP-1');req.classification='CLIENT';req.save(update_fields=['classification'])
        _,wb=self.export({'q':'SEP-1'});self.assertEqual(wb.active['Q5'].value,'Not applicable')
        # The database correctly rejects MICROCOM without a branch, so the
        # malformed legacy shape is covered by synthetic offline tests instead.
        branch=Succursale.objects.create(code='EXPORT',name='Existing sample branch',physical_address='Synthetic address')
        req.classification='MICROCOM';req.succursale=branch;req.save(update_fields=['classification','succursale'])
        _,wb=self.export({'q':'SEP-1'});self.assertEqual(wb.active['Q5'].value,'EXPORT - Existing sample branch')

    def test_movement_scope_and_unlinked_rows(self):
        selected=Request.objects.get(request_number='SEP-1');outside=Request.objects.get(request_number='OCT')
        for request,kind in [(selected,'OUT'),(outside,'OUT'),(None,'IN')]:
            StockMovement.objects.create(request=request,material=self.cable,quantity=1,movement_type=kind)
        _,wb=self.export();self.assertEqual(wb['Stock Movements'].max_row,6)
        _,wb=self.export({'q':'SEP-1'});sheet=wb['Stock Movements']
        self.assertEqual(sheet.max_row,4);self.assertEqual(sheet['H4'].value,'SEP-1')

    def test_literal_formulas_in_actual_export(self):
        req=Request.objects.get(request_number='SEP-1');req.description='=HYPERLINK("https://invalid","x")';req.save(update_fields=['description'])
        self.cable.name='=FORMULA';self.cable.save(update_fields=['name'])
        _,wb=self.export({'q':'SEP-1'})
        self.assertEqual(wb.active['M5'].data_type,'s')
        self.assertEqual(wb.active['M5'].value,req.description)
        self.assertEqual(wb.active['G5'].data_type,'s')

    def test_invalid_filters_return_400(self):
        self.client.force_login(self.user)
        for params in [{'date_from':'bad'},{'date_from':'2026-10-02','date_to':'2026-10-01'},{'department':'not-an-id'},{'department':'999999999'}]:
            self.assertEqual(self.client.get(reverse('export_material_report_excel'),params,HTTP_HOST='127.0.0.1').status_code,400)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=1)
    def test_size_limit(self):
        self.client.force_login(self.user)
        response=self.client.get(reverse('export_material_report_excel'),{'q':'SEP-1'},HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code,413)
        self.assertContains(response,'Narrow the filters',status_code=413)

    def test_timezone_boundary(self):
        Request.objects.filter(request_number='SEP-1').update(finalized_at=datetime(2026,12,31,23,30,tzinfo=timezone.utc))
        _,wb=self.export({'q':'SEP-1'})
        self.assertEqual(wb.active['F5'].value,'2027-01-01 00:30')
        self.assertEqual(wb['Graphs']['AE2'].value,'Jan 2027')

    def test_export_executes_only_reads(self):
        request=RequestFactory().get('/materials/reports/export-excel/');request.user=self.user
        with CaptureQueriesContext(connection) as queries:
            response=export_material_report_excel(request)
        self.assertEqual(response.status_code,200)
        for query in queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'),query['sql'].split()[0])
        self.assertFalse(MaterialDocument.objects.exists())
        self.assertFalse(MaterialDocumentSequence.objects.exists())
