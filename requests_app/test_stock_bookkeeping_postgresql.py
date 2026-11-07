"""Synthetic fixtures on the explicitly verified disposable database only."""
from decimal import Decimal
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from openpyxl import load_workbook

from invoicing.test_lifecycle import LifecycleFixtures
from invoicing.models import Invoice, InvoiceLine, DocumentSequence, InvoiceAuditEvent
from inventory.pricing import price_state, update_price
from requests_app.services import approve_step
from requests_app.models import MaterialDocument, MaterialDocumentSequence
from .views import export_material_report_excel
from .test_stock_bookkeeping_offline import financial_rows


class BookkeepingExportTests(LifecycleFixtures, TestCase):
    def finalized(self, price='2', currency='USD'):
        invoice=self.create(currency=currency);self.price(invoice,price)
        if not DocumentSequence.objects.exists():self.verified_sequence()
        return self.finalize(invoice)

    def page(self,user=None):
        request=RequestFactory().get('/materials/reports/export-excel/');request.user=user or self.user
        response=export_material_report_excel(request)
        if response.status_code==200:return load_workbook(BytesIO(response.content))
        return response

    def test_authorized_frozen_values_not_live_catalogue(self):
        invoice=self.finalized();line=invoice.lines.get();old_branch=invoice.succursale_snapshot['name']
        self.material = update_price(self.material.pk, self.admin, price=Decimal('999'), currency='EUR',
            reason='Synthetic historical invoice preservation test', expected_state=price_state(self.material))
        self.material.name='Changed current name';self.material.save(update_fields=['name'])
        self.branch.name='Changed current branch';self.branch.save()
        wb=self.page();sheet=wb['Bookkeeping']
        self.assertEqual(sheet['A3'].value,invoice.number)
        self.assertIn(old_branch,sheet['D3'].value);self.assertNotIn('Changed current branch',sheet['D3'].value)
        self.assertEqual(sheet['E3'].value,line.description_snapshot)
        self.assertEqual(sheet['I3'].value,2);self.assertEqual(sheet['J3'].value,'USD');self.assertEqual(sheet['K3'].value,20)
        self.assertEqual(wb.sheetnames[:4],['Material Report','Dashboard','Graphs','Stock Movements'])
        self.assertEqual(len(wb['Graphs']._charts[:4]),4);self.assertEqual(len(wb.sheetnames),11)

    def test_stock_access_without_invoice_permission_has_no_financial_content(self):
        invoice=self.finalized()
        permission=Permission.objects.get(content_type__app_label='invoicing',codename='view_invoice')
        self.user.user_permissions.remove(permission);actor=get_user_model().objects.get(pk=self.user.pk)
        wb=self.page(actor);self.assertNotIn('Bookkeeping',wb.sheetnames)
        for sheet in wb:
            for row in sheet:
                for cell in row:
                    self.assertNotEqual(cell.value,invoice.number)
                    if isinstance(cell.value,str):self.assertNotIn('Known Authorized',cell.value)

    def test_invoice_permission_without_assignment_does_not_leak(self):
        invoice=self.finalized();self.other.can_manage_stock=True;self.other.save()
        self.other.user_permissions.add(Permission.objects.get(content_type__app_label='invoicing',codename='view_invoice'))
        actor=get_user_model().objects.get(pk=self.other.pk);wb=self.page(actor)
        self.assertNotIn('Bookkeeping',wb.sheetnames)
        self.assertFalse(any(cell.value==invoice.number for sheet in wb for row in sheet for cell in row))
        actor.is_staff=True;actor.save()
        actor.user_permissions.add(Permission.objects.get(content_type__app_label='invoicing',codename='manage_all_invoices'))
        actor=get_user_model().objects.get(pk=actor.pk)
        self.assertEqual(self.page(actor)['Bookkeeping']['A3'].value,invoice.number)

    def test_multiple_currencies_are_separate(self):
        self.finalized()
        req,_=self.make_request(2);approve_step(req.approvals.get(),self.user,classification='MICROCOM',succursale=self.branch)
        self.req=req;self.finalized('3',currency='EUR')
        wb=self.page();rows=list(wb['Monthly Statistics'].values) + financial_rows(wb, 'Monthly Statistics')
        totals={(row[2],row[3]) for row in rows[2:] if row[1]=='Known Authorized Invoice Totals'}
        self.assertEqual(totals,{('USD',20),('EUR',6)})

    def test_zero_price_preserved(self):
        self.finalized('0');sheet=self.page()['Bookkeeping']
        self.assertEqual(sheet['I3'].value,0);self.assertEqual(sheet['K3'].value,0)
        self.assertEqual(sheet['L3'].value,'Finalized')

    def test_missing_finalized_valuation_not_current_price(self):
        self.material = update_price(self.material.pk, self.admin, price=Decimal('500'), currency='USD',
            reason='Synthetic missing finalized valuation test', expected_state=price_state(self.material))
        self.create()  # Unpriced/priced editable draft is not financial evidence.
        sheet=self.page()['Bookkeeping']
        self.assertEqual(sheet['I3'].value,'Unknown');self.assertEqual(sheet['L3'].value,'Invoice not issued or not finalized (on demand)')

    def test_client_activity_has_no_internal_invoice_coverage_warning(self):
        req,_=self.make_request(2)
        approve_step(req.approvals.get(),self.user,classification='CLIENT')
        wb=self.page()
        rows=list(wb['Bookkeeping'].values)[2:]
        client=next(row for row in rows if row[2]==req.request_number)
        self.assertEqual(client[11],'Internal invoice not applicable')
        self.assertEqual(client[8],'Not applicable')
        monthly=list(wb['Monthly Statistics'].values)[2:] + financial_rows(wb, 'Monthly Statistics')
        self.assertEqual(sum(row[3] for row in monthly if row[1]=='MICROCOM invoices not issued or not finalized (on demand)'),1)
        self.assertFalse(any(row[1]=='Missing Frozen Values' for row in monthly))
        self.assertEqual(sum(row[3] for row in monthly if row[1]=='Approved Material Requests'),2)

    def test_returns_preserve_frozen_net_values(self):
        self.restore(Decimal('2'))
        invoice=self.finalized();self.assertEqual(invoice.lines.get().quantity,8)
        self.restore(Decimal('1'))
        sheet=self.page()['Bookkeeping']
        self.assertEqual(sheet['G3'].value,8);self.assertEqual(sheet['K3'].value,16)

    def test_reads_only_and_all_evidence_unchanged(self):
        invoice=self.finalized()
        models=[Invoice,InvoiceLine,DocumentSequence,InvoiceAuditEvent,MaterialDocument,MaterialDocumentSequence]
        before=[list(model.objects.order_by('pk').values()) for model in models];stock=self.source_snapshot()
        with CaptureQueriesContext(connection) as queries:self.page()
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertEqual(before,[list(model.objects.order_by('pk').values()) for model in models])
        self.assertEqual(stock,self.source_snapshot())

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=2)
    def test_bookkeeping_rows_share_existing_limit(self):
        self.finalized();response=self.page()
        self.assertEqual(response.status_code,413)
