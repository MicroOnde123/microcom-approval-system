"""Synthetic workbook tests: no database or network access."""
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace as Obj
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings
from django.utils.translation import override, gettext
from openpyxl import Workbook, load_workbook

from . import stock_report_export as export
from .views import export_material_report_excel


def related(rows):
    return Obj(all=lambda: rows)


def fixture():
    material=Obj(pk=1,name='=HYPERLINK("https://invalid","x")',code='=CODE',unit='pcs',stock_quantity=Decimal('10'),category=Obj(name='=CATEGORY'))
    item=Obj(material_id=1,material=material,quantity=Decimal('2'))
    return Obj(pk=1,request_number='=REQUEST',submitted_by=Obj(full_name='=USER',username='sample'),
        department=Obj(name='=ORIGIN'),request_for_department=Obj(name='=DEPARTMENT'),request_for_department_id=1,
        finalized_at=datetime(2026,12,31,23,30,tzinfo=timezone.utc),date_needed=date(2026,12,31),
        material_items=related([item]),approvals=related([]),material_documents=related([]),
        description='=DESCRIPTION',material_issue_note='=NOTE',classification=None,succursale_id=None)


class StockExportOfflineTests(TestCase):
    def test_approved_analytics_never_claim_physical_issuance(self):
        for language, dashboard, graphs, quantity, lines, top in (
            ('en', 'Dashboard', 'Graphs', 'Approved Quantity', 'Approved Material Lines',
             'Top 10 Materials by Approved Quantity'),
            ('fr', 'Tableau de bord', 'Graphiques', 'Quantité approuvée', "Lignes d'articles approuvées",
             'Top 10 des articles par quantité approuvée'),
        ):
            with self.subTest(language=language):
                # Approved quantity exists, but there are no recorded OUT movements.
                wb = self.render_export(language=language, movements=[])
                self.assertEqual(wb[dashboard]['D16'].value, quantity)
                self.assertEqual(wb[dashboard]['D17'].value, 2)
                self.assertEqual(wb[dashboard]['D9'].value, lines)
                self.assertEqual(wb[graphs]['Z1'].value, quantity)
                self.assertEqual(wb[graphs]['AF1'].value, lines)
                titles = [chart.title.tx.rich.p[0].r[0].t for chart in wb[graphs]._charts]
                self.assertEqual(titles[0], top)
                self.assertEqual(titles[2], lines + (' Over Time' if language == 'en' else ' dans le temps'))
                self.assertFalse(any('issued' in title.lower() or 'sorties' in title.lower() or 'sortis' in title.lower()
                                     for title in titles))

    def render_export(self,req=None,language='en',movements=None,params=None):
        req=req or fixture()
        request=RequestFactory().get('/materials/reports/export-excel/',params or {})
        request.user=Obj(is_authenticated=True,is_active=True,is_superuser=False,can_manage_stock=True,has_perm=lambda permission: False)
        with override(language),patch('requests_app.views.get_filtered_material_report_requests',return_value=[req]),patch.object(export,'movement_scope',return_value=movements or []),patch.object(export,'enforce_size',return_value=100),patch('requests_app.stock_report_inventory.load_current_inventory',return_value=[]),patch('requests_app.stock_report_entries.load_material_entries',return_value=[]),patch('requests_app.stock_report_reconciliation.load_issuance_returns',return_value=[]),patch('requests_app.stock_report_operational.load_warehouse_movements',return_value=([],0)):
            response=export_material_report_excel(request)
        self.assertEqual(response.status_code,200)
        return load_workbook(BytesIO(response.content))

    def test_original_sheets_and_four_charts_retained(self):
        wb=self.render_export()
        self.assertEqual(wb.sheetnames[:4],['Material Report','Dashboard','Graphs','Stock Movements'])
        self.assertEqual(wb.sheetnames[4:],['Succursale Summary','Material Group Summary','Monthly Statistics','Current Stock Inventory','Material Entries','Issuance and Returns'])
        self.assertEqual(len(wb['Graphs']._charts),4)
        self.assertEqual(wb.active.max_column,20)
        self.assertEqual(wb.active.freeze_panes,'A5')
        self.assertEqual(wb.active.auto_filter.ref,'A4:T5')

    def test_all_user_text_is_literal_in_saved_workbook(self):
        wb=self.render_export()
        for cell in wb.active[5]:
            if isinstance(cell.value,str):self.assertEqual(cell.data_type,'s')
        self.assertEqual(wb.active['A5'].value,'=REQUEST')
        self.assertEqual(wb.active['G5'].data_type,'s')
        for sheet in wb:
            for row in sheet:
                for cell in row:self.assertNotEqual(cell.data_type,'f')

    def test_formula_prefixes_and_numeric_values_preserved(self):
        wb=Workbook();values=['=1+1','+SUM(A1)','-1','@name','\t=1+1',Decimal('2.5'),0]
        wb.active.append(values);export.protect_text_cells(wb)
        data=BytesIO();wb.save(data);data.seek(0);sheet=load_workbook(data).active
        for index,value in enumerate(values[:5],1):
            self.assertEqual(sheet.cell(1,index).value,value);self.assertEqual(sheet.cell(1,index).data_type,'s')
        self.assertEqual(sheet['F1'].value,2.5);self.assertEqual(sheet['G1'].value,0)

    def test_missing_classification_and_documents(self):
        req=fixture();values=export.request_extras(req)
        self.assertEqual(values[:4],['Classification unavailable','Classification unavailable','Not issued','Not issued'])
        self.assertIn('BC not issued',values[4])

    def test_client_branch_is_not_applicable(self):
        req=fixture();req.classification='CLIENT';req.succursale_id=999;req.succursale='Must not show'
        self.assertEqual(export.request_extras(req)[1],'Not applicable')

    def test_microcom_missing_and_present_branch(self):
        req=fixture();req.classification='MICROCOM'
        self.assertEqual(export.request_extras(req)[1],'Missing succursale')
        req.succursale_id=1;req.succursale='Existing branch'
        self.assertEqual(export.request_extras(req)[1],'Existing branch')

    def test_existing_bc_bs_only(self):
        req=fixture();req.material_documents=related([Obj(kind='BC',reference='BC/0001/2026'),Obj(kind='BS',reference='BS/0001/2026')])
        self.assertEqual(export.request_extras(req)[2:4],['BC/0001/2026','BS/0001/2026'])

    def test_kinshasa_dates_and_months(self):
        self.assertEqual(export.reporting_time(datetime(2026,12,31,23,30,tzinfo=timezone.utc)),'2027-01-01 00:30')
        wb=self.render_export()
        self.assertEqual(wb.active['F5'].value,'2027-01-01 00:30')
        self.assertEqual(wb.active['D2'].value,'Africa/Kinshasa')
        self.assertEqual(wb['Graphs']['AE2'].value,'Jan 2027')

    def test_movement_rows_and_missing_link_actor(self):
        req=fixture();material=req.material_items.all()[0].material
        movement=Obj(created_at=req.finalized_at,material=material,quantity=Decimal('1'),request_id=None,performed_by=None,movement_type='IN',get_movement_type_display=lambda:'Stock In')
        wb=self.render_export(req,movements=[movement]);sheet=wb['Stock Movements']
        self.assertEqual(sheet['A4'].value,'2027-01-01 00:30')
        self.assertEqual(sheet['H4'].value,'No linked request');self.assertEqual(sheet['I4'].value,'Actor unavailable')
        self.assertEqual(sheet['B4'].data_type,'s')

    def test_linked_movement_reuses_refs(self):
        req=fixture();req.material_documents=related([Obj(kind='BC',reference='BC/0001/2026',allocated_at=req.finalized_at)])
        movement=Obj(created_at=req.finalized_at,material=req.material_items.all()[0].material,quantity=Decimal('1'),request_id=1,request=req,performed_by=Obj(full_name='=ACTOR',username='sample'),movement_type='RETURN',get_movement_type_display=lambda:'Return to Stock')
        wb=self.render_export(req,movements=[movement])
        self.assertEqual(wb['Stock Movements']['J4'].value,'BC/0001/2026')
        self.assertEqual(wb['Stock Movements']['I4'].data_type,'s')

    def test_french_sheets_headers_messages(self):
        wb=self.render_export(language='fr')
        self.assertEqual(wb.sheetnames[:4],['Rapport de matériel','Tableau de bord','Graphiques','Mouvements de stock'])
        self.assertEqual(wb.active['R4'].value,'Référence BC')
        self.assertEqual(wb.active['R5'].value,'Non émis')

    def test_dates_validate_without_database(self):
        for params in [{'date_from':'not-a-date'},{'date_from':'2026-02-30'},{'date_from':'2026-10-02','date_to':'2026-10-01'}]:
            self.assertFalse(export.ExportFilterForm(params).is_valid())
        self.assertTrue(export.ExportFilterForm({'date_from':'2026-10-01','date_to':'2026-10-02'}).is_valid())

    def test_invalid_filters_fail_before_query(self):
        req=RequestFactory().get('/',{'date_from':'bad'});req.user=Obj(is_authenticated=True,is_superuser=True)
        with patch('requests_app.views.get_filtered_material_report_requests') as query:
            self.assertEqual(export_material_report_excel(req).status_code,400);query.assert_not_called()

    def test_permissions_fail_before_query(self):
        req=RequestFactory().get('/');req.user=Obj(is_authenticated=True,is_superuser=False,can_manage_stock=False)
        with patch('requests_app.views.get_filtered_material_report_requests') as query:
            self.assertEqual(export_material_report_excel(req).status_code,403);query.assert_not_called()

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=3)
    def test_combined_limit_and_boundary(self):
        rows=MagicMock();movements=MagicMock();movements.count.return_value=1
        with patch.object(export.RequestMaterialItem,'objects') as manager:
            manager.filter.return_value.count.return_value=2
            self.assertEqual(export.enforce_size(rows,movements),3)
            movements.count.return_value=2
            with self.assertRaises(ValidationError):export.enforce_size(rows,movements)

    @override_settings(STOCK_REPORT_EXPORT_MAX_ROWS=0)
    def test_invalid_limit_fails_closed(self):
        with self.assertRaises(ValidationError):export.enforce_size(MagicMock(),MagicMock())

    def test_loaded_limit_rechecked(self):
        with self.assertRaises(ValidationError):export.enforce_loaded_size([fixture()],[1,2,3],3)

    def test_row_limit_returns_bilingual_error(self):
        req=RequestFactory().get('/');req.user=Obj(is_authenticated=True,is_superuser=True)
        with override('fr'),patch('requests_app.views.get_filtered_material_report_requests'),patch.object(export,'movement_scope'),patch.object(export,'enforce_size',side_effect=ValidationError(gettext('The Excel export exceeds %(limit)s rows. Narrow the filters and try again.') % {'limit':3})):
            self.assertEqual(export_material_report_excel(req).status_code,413)

    def test_movement_scope_uses_same_request_filters(self):
        rows=MagicMock()
        with patch.object(export.StockMovement,'objects') as manager:
            export.movement_scope(rows,{})
            empty=manager.filter.call_args.args[0]
            self.assertEqual(empty.connector,'OR')
            export.movement_scope(rows,{'date_from':date(2026,1,1)})
            filtered=manager.filter.call_args.args[0]
            self.assertNotIn(('request__isnull',True),filtered.children)

    def test_no_issuance_or_financial_code(self):
        import inspect
        source=inspect.getsource(export)
        self.assertNotIn('issue_document(',source);self.assertNotIn('.save(',source)
        self.assertNotIn('invoicing',source);self.assertNotIn('unit_price',source)
