from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as Obj
from unittest import TestCase
from unittest.mock import patch

from django.utils.translation import override
from openpyxl import Workbook, load_workbook

from . import stock_report_bookkeeping as report
from .stock_report_export import protect_text_cells
from .test_stock_export_offline import fixture, related


class BookkeepingOfflineTests(TestCase):
    def data(self,price=Decimal('2.50'),amount=Decimal('5.00'),currency='USD'):
        req=fixture()
        inv=Obj(pk=1,request_id=1,number='FAC/FROZEN',issue_date=date(2027,1,1),finalized_at=req.finalized_at,
            succursale_snapshot={'id':1,'code':'OLD','name':'=FROZEN BRANCH'},request_reference_snapshot='REQ-FROZEN',currency=currency,total=amount)
        line=Obj(invoice_id=1,material=req.material_items.all()[0].material,description_snapshot='=FROZEN MATERIAL',quantity=Decimal('2'),unit_snapshot='m',unit_price=price,line_total=amount,currency=currency)
        return req,{'allowed':{1},'invoices':[inv],'lines':[line]}

    def workbook(self,req,data,movements=None):
        wb=Workbook();report.add_statistics(wb,[req],movements or [],data);protect_text_cells(wb)
        raw=BytesIO();wb.save(raw);raw.seek(0);return load_workbook(raw)

    def test_frozen_zero_values_remain_numeric(self):
        req,data=self.data(Decimal('0'),Decimal('0'))
        wb=self.workbook(req,data);row=list(wb['Bookkeeping'].values)[2]
        self.assertEqual(row[3],'OLD - =FROZEN BRANCH');self.assertEqual(row[4],'=FROZEN MATERIAL')
        self.assertEqual(row[6:11],(2,'m',0,'USD',0));self.assertEqual(row[11],'Finalized')

    def test_missing_values_are_unknown_not_zero(self):
        req,data=self.data(None,None);row=list(self.workbook(req,data)['Bookkeeping'].values)[2]
        self.assertEqual(row[8],'Unknown');self.assertEqual(row[10],'Unknown')

    def test_no_finalized_invoice_explicit(self):
        req,data=self.data();data['invoices']=[];data['lines']=[]
        req.classification='MICROCOM'
        row=list(self.workbook(req,data)['Bookkeeping'].values)[2]
        self.assertEqual(row[11],'Invoice not issued or not finalized (on demand)');self.assertEqual(row[8],'Unknown')

    def test_mixed_classifications_keep_activity_without_false_missing_values(self):
        requests=[]
        for pk,classification in enumerate(['CLIENT','MICROCOM',None],1):
            req=fixture();req.pk=pk;req.classification=classification;req.request_number=f'REQ-{pk}'
            requests.append(req)
        data={'allowed':{1,2,3},'invoices':[],'lines':[]}
        mat=requests[0].material_items.all()[0].material
        movements=[Obj(material=mat,created_at=r.finalized_at,movement_type='OUT',quantity=Decimal('1'),request_id=r.pk) for r in requests]
        for language in ['en','fr']:
            with override(language):
                from django.utils.translation import gettext as _
                wb=Workbook();report.add_statistics(wb,requests,movements,data)
                rows=list(wb[_('Bookkeeping')].values)[2:]
                self.assertEqual([r[11] for r in rows],[_('Internal invoice not applicable'),_('Invoice not issued or not finalized (on demand)'),_('Classification unavailable')])
                self.assertEqual(rows[0][8],_('Not applicable'))
                monthly=list(wb[_('Monthly Statistics')].values)
                self.assertIn(('2027-01',_('Approved Material Requests'),'',3),monthly)
                self.assertIn(('2027-01',_('Stock Movements'),'',3),monthly)
                self.assertIn(('2027-01',_('Quantity Issued'),'pcs',3),monthly)
                self.assertIn(('2027-01',_('MICROCOM invoices not issued or not finalized (on demand)'),'',1),monthly)
                self.assertFalse(any(r[1]==_('Missing Frozen Values') for r in monthly[2:]))
                branches=list(wb[_('Succursale Summary')].values)[2:]
                counts=[r for r in branches if r[1]==_('MICROCOM invoices not issued or not finalized (on demand)')]
                self.assertEqual(sum(r[3] for r in counts),1)

    def test_mixed_finalized_and_optional_invoices_reconcile(self):
        finalized,data=self.data();finalized.classification='MICROCOM'
        pending=fixture();pending.pk=2;pending.classification='MICROCOM'
        client=fixture();client.pk=3;client.classification='CLIENT'
        legacy=fixture();legacy.pk=4
        data['allowed']={1,2,3,4}
        wb=Workbook();report.add_statistics(wb,[finalized,pending,client,legacy],[],data)
        rows=list(wb['Monthly Statistics'].values)[2:]
        self.assertIn(('2027-01','Known Authorized Invoice Totals','USD',Decimal('5')),rows)
        self.assertIn(('2027-01','MICROCOM invoices not issued or not finalized (on demand)','',1),rows)
        self.assertFalse(any(row[1]=='Missing Frozen Values' for row in rows))
        self.assertEqual(len(list(wb['Bookkeeping'].values)[2:]),4)
        with override('fr'):
            from django.utils.translation import gettext
            self.assertEqual(gettext('Internal invoice not applicable'),'Facture interne non applicable')
            self.assertEqual(gettext('Invoice not issued or not finalized (on demand)'),'Facture non émise ou non finalisée (sur demande)')

    def test_missing_frozen_branch_no_current_fallback(self):
        req,data=self.data();data['invoices'][0].succursale_snapshot={};req.succursale='CURRENT SECRET'
        row=list(self.workbook(req,data)['Bookkeeping'].values)[2]
        self.assertEqual(row[3],'Frozen succursale unavailable')

    def test_no_financial_sheets_metadata_or_values_when_denied(self):
        req,data=self.data();wb=self.workbook(req,None)
        self.assertNotIn('Bookkeeping',wb.sheetnames)
        strings=[c.value for s in wb for row in s for c in row if isinstance(c.value,str)]
        self.assertFalse(any('Currency' in value or 'Authorized' in value or 'FAC/FROZEN' in value for value in strings))

    def test_permission_absence_does_not_query_invoice_models(self):
        req,_=self.data();user=Obj(is_active=False)
        self.assertIsNone(report.load_bookkeeping(user,[req],100))

    def test_financial_formula_cells_literal(self):
        req,data=self.data();sheet=self.workbook(req,data)['Bookkeeping']
        self.assertEqual(sheet['E3'].data_type,'s');self.assertEqual(sheet['E3'].value,'=FROZEN MATERIAL')

    def test_stored_invoice_total_is_not_recalculated(self):
        req,data=self.data();data['invoices'][0].total=Decimal('19.99')
        wb=self.workbook(req,data)
        metrics=list(wb['Succursale Summary'].values)
        self.assertIn(('OLD - =FROZEN BRANCH [1]','Known Authorized Invoice Totals','USD',19.99),metrics)
        self.assertIn(('=CATEGORY','Known Authorized Stored Line Totals','USD',5),list(wb['Material Group Summary'].values))

    def test_material_balance_not_repeated_per_request_line(self):
        req,_=self.data();req.material_items=related(req.material_items.all()*2)
        metrics=list(self.workbook(req,None)['Material Group Summary'].values)
        self.assertIn(('=CATEGORY','Available Central Stock','pcs',10),metrics)

    def test_month_boundary_and_document_count(self):
        req,data=self.data();req.material_documents=related([Obj(kind='BC',allocated_at=req.finalized_at)])
        rows=list(self.workbook(req,data)['Monthly Statistics'].values)
        self.assertIn(('2027-01','Approved Material Requests',None,1),rows)
        self.assertIn(('2027-01','BC Documents',None,1),rows)

    def test_month_uses_kinshasa_instant_without_rewriting_issue_date(self):
        req,data=self.data();data['invoices'][0].issue_date=date(2026,12,31)
        wb=self.workbook(req,data)
        self.assertIn(('2027-01','Known Authorized Invoice Totals','USD',5),list(wb['Monthly Statistics'].values))
        self.assertEqual(wb['Bookkeeping']['B3'].value.date(),date(2026,12,31))

    def test_out_and_return_not_netting_invoice_values(self):
        req,data=self.data();mat=req.material_items.all()[0].material
        movements=[Obj(material=mat,created_at=req.finalized_at,movement_type=kind,quantity=Decimal(qty),request_id=1) for kind,qty in [('OUT','3'),('RETURN','1')]]
        wb=self.workbook(req,data,movements)
        self.assertIn(('2027-01','Quantity Issued','pcs',3),list(wb['Monthly Statistics'].values))
        self.assertEqual(wb['Bookkeeping']['G3'].value,2)

    def test_distinct_unit_and_currency_totals(self):
        req,data=self.data();inv=data['invoices'][0];line=data['lines'][0]
        second=Obj(**vars(inv));second.pk=2;second.currency='EUR';second.total=Decimal('7')
        other=Obj(**vars(line));other.invoice_id=2;other.currency='EUR';other.line_total=Decimal('7')
        data['invoices'].append(second);data['lines'].append(other)
        rows=list(self.workbook(req,data)['Monthly Statistics'].values)
        self.assertIn(('2027-01','Known Authorized Invoice Totals','USD',5),rows)
        self.assertIn(('2027-01','Known Authorized Invoice Totals','EUR',7),rows)

    def test_large_decimal_evidence_preserved_as_text(self):
        self.assertEqual(report.exact_number(Decimal('1234567890123456.78')),'1234567890123456.78')

    def test_french_sheets(self):
        req,data=self.data()
        with override('fr'):
            wb=self.workbook(req,data)
            self.assertIn('Comptabilité interne',wb.sheetnames)
            self.assertIn('Synthèse par succursale',wb.sheetnames)
