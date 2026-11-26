"""Synthetic, database-free contracts; Excel interaction is separately manual."""
from decimal import Decimal
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch
from django.utils.translation import override, gettext as _
from openpyxl import Workbook, load_workbook
from .stock_report_interactive import enhance
from .stock_report_export import protect_text_cells
from . import test_stock_export_offline as offline


def sample(language='en'):
    with override(language):
        with patch('requests_app.stock_report_interactive.enhance'):
            wb = offline.StockExportOfflineTests().render_export(language=language)
        sheet = wb.create_sheet(_('Bookkeeping'))
        sheet.append(['Synthetic frozen invoice evidence only'])
        sheet.append([_('Invoice Reference'), _('Invoice Issue Date'), _('Request Number'), _('Succursale'),
                      _('Frozen Material'), _('Material Category (current)'), _('Net Quantity'), _('Frozen Unit'),
                      _('Frozen Unit Price'), _('Currency'), _('Stored Line Total'), _('Bookkeeping Status')])
        for ref, branch, material, quantity, price, currency, value in [
            ('DEMO-1','Branch A','Cable',2,10,'USD',20),
            ('DEMO-2','Branch B','Connector',3,5,'USD',15),
            ('DEMO-3','Branch A','Cable',4,1000,'CDF',4000),
            ('DEMO-4','Branch B','Unknown',1,None,'USD',None)]:
            sheet.append([ref,'2026-11-26','DEMO-REQUEST',branch,material,'Synthetic',quantity,'pcs',
                          price if price is not None else _('Unknown'),currency,
                          value if value is not None else _('Unknown'),_('Finalized')])
        sheet.auto_filter.ref = 'A2:L6'
        protect_text_cells(wb)
        enhance(wb)
        return wb


class InteractiveWorkbookTests(TestCase):
    def test_currency_units_and_frozen_values(self):
        for lang in ['en','fr']:
            with self.subTest(lang=lang),override(lang):
                wb=sample(lang);summary=wb['Totaux visibles' if lang=='fr' else 'Visible Totals']
                rows=[r for r in summary.iter_rows(min_row=5,values_only=True) if r[1]==_('Stored Line Total')]
                self.assertEqual({r[2]:r[3] for r in rows},{'USD':Decimal(35),'CDF':Decimal(4000)})
                self.assertEqual(wb[_('Bookkeeping')]['I3'].value,10)
                self.assertEqual(wb[_('Bookkeeping')]['K3'].value,20)
                for row in rows:
                    self.assertTrue(row[4].startswith('=SUMIFS('));self.assertIn('[Stored Line Total]',row[4]) if lang=='en' else self.assertIn(_('Stored Line Total'),row[4])
                    self.assertNotIn('OFFSET',row[4])
                self.assertEqual(wb.calculation.calcMode,'auto')
                self.assertTrue(wb.calculation.fullCalcOnLoad)

    def test_round_trip_tables_and_no_external_dependencies(self):
        for lang in ['en','fr']:
            with self.subTest(lang=lang):
                raw=BytesIO();sample(lang).save(raw);raw.seek(0);wb=load_workbook(raw)
                tables=[table for sheet in wb for table in sheet.tables.values()]
                self.assertEqual(len(tables),6)
                self.assertEqual(len({t.name for t in tables}),len(tables))
                self.assertFalse(wb._external_links)
                self.assertIsNone(wb.vba_archive)
                for table in tables:self.assertIsNotNone(table.autoFilter)

    def test_empty_table_message_stays_outside_data(self):
        wb=Workbook();sheet=wb.active;sheet.title='Material Entries'
        sheet.append(['Title']);sheet.append(['Metadata']);sheet.append(['Note'])
        sheet.append(['Unit','Quantity Received']);sheet.append(['No receipts'])
        sheet.auto_filter.ref='A4:B4';enhance(wb)
        self.assertEqual(sheet.tables['MicrocomDetail4'].ref,'A4:C5')
        self.assertIsNone(sheet['A5'].value)
        self.assertEqual(sheet['A6'].value,'No receipts')
        self.assertEqual(wb['Visible Totals']['D5'].value,0)

    def test_export_injection_is_not_a_formula(self):
        wb=sample();self.assertEqual(wb['Material Report']['G5'].data_type,'s')
        self.assertTrue(wb['Material Report']['G5'].value.startswith('='))
        for sheet in wb:
            for row in sheet:
                for cell in row:
                    if cell.data_type=='f':
                        if sheet.title=='Visible Totals':
                            self.assertEqual(cell.column,5);self.assertTrue(cell.value.startswith('=SUMIFS('))
                        else:
                            self.assertTrue(sheet.column_dimensions[cell.column_letter].hidden)
                            self.assertTrue(cell.value.startswith('=SUBTOTAL(103,'))

    def test_no_financial_sheet_or_currency_leak_without_permission(self):
        wb=offline.StockExportOfflineTests().render_export()
        self.assertNotIn('Bookkeeping',wb.sheetnames)
        self.assertFalse(any(row[2] in ('USD','CDF') for row in wb['Visible Totals'].iter_rows(min_row=5,values_only=True)))

    def test_quantities_never_combine_incompatible_units(self):
        wb=Workbook();sheet=wb.active;sheet.title='Material Report'
        sheet.append(['Quantity','Unit']);sheet.append([2,'pcs']);sheet.append([3,'m']);sheet.append([4,'pcs'])
        sheet.auto_filter.ref='A1:B4';enhance(wb)
        self.assertEqual({r[2]:r[3] for r in wb['Visible Totals'].iter_rows(min_row=5,values_only=True)}, {'pcs':6,'m':3})

    def test_precise_text_evidence_preserved_not_silently_coerced(self):
        wb=Workbook();sheet=wb.active;sheet.title='Material Report'
        sheet.append(['Quantity','Unit']);sheet.append(['12345678901234567.89','pcs'])
        sheet.auto_filter.ref='A1:B2';enhance(wb)
        self.assertEqual(sheet['A2'].value,'12345678901234567.89')
        self.assertIn('precision-preserving text',wb['Visible Totals']['A2'].value)
        self.assertEqual(wb['Visible Totals']['D5'].value,0)

    def test_generated_summary_budget_is_enforced(self):
        from django.test import override_settings
        from django.core.exceptions import ValidationError
        with override_settings(STOCK_REPORT_EXPORT_MAX_SUMMARY_ROWS=1):
            with self.assertRaises(ValidationError):enhance(Workbook())
    def test_raw_ooxml_table_contracts_in_both_languages(self):
        import zipfile
        import xml.etree.ElementTree as ET
        from openpyxl.utils.cell import range_boundaries, get_column_letter
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        for language in ('en','fr'):
            with self.subTest(language=language):
                wb=sample(language);raw=BytesIO();wb.save(raw);raw.seek(0)
                with zipfile.ZipFile(raw) as archive:
                    tables=[ET.fromstring(archive.read(name)) for name in archive.namelist() if name.startswith('xl/tables/')]
                    self.assertEqual(len({t.get('id') for t in tables}),6)
                    self.assertEqual(len({t.get('displayName').casefold() for t in tables}),6)
                    for table in tables:
                        left,top,right,bottom=range_boundaries(table.get('ref'))
                        self.assertGreater(bottom,top)
                        columns=table.find('s:tableColumns',ns)
                        self.assertEqual(int(columns.get('count')),right-left+1)
                        self.assertEqual(len(columns),right-left+1)
                        self.assertEqual(len({c.get('id') for c in columns}),len(columns))
                        self.assertEqual(len({c.get('name').casefold() for c in columns}),len(columns))
                        self.assertEqual(table.find('s:autoFilter',ns).get('ref'),table.get('ref'))
                        self.assertEqual(columns[-1].get('name'),'VisibleRow')
                        self.assertTrue(columns[-1].find('s:calculatedColumnFormula',ns).text.startswith('SUBTOTAL(103,'))
                    for index,sheet in enumerate(wb.worksheets,1):
                        xml=ET.fromstring(archive.read(f'xl/worksheets/sheet{index}.xml'))
                        if sheet.tables:
                            self.assertIsNone(xml.find('s:autoFilter',ns),'Table must own the filter; no overlapping worksheet filter')
                            table=next(iter(sheet.tables.values()))
                            left,top,right,bottom=range_boundaries(table.ref)
                            self.assertTrue(sheet.column_dimensions[get_column_letter(right)].hidden)
                            self.assertEqual([sheet.cell(top,c).value for c in range(left,right+1)], [c.name for c in table.tableColumns])
                            for row in range(top+1,bottom+1):
                                self.assertTrue(sheet.cell(row,right).value.startswith('=SUBTOTAL(103,'))
                        for formula in xml.findall('.//s:f',ns):
                            self.assertFalse(formula.text.startswith('='))
                            self.assertNotIn('OFFSET(',formula.text)
                            self.assertNotIn('SUMPRODUCT(',formula.text)
                            self.assertNotIn('#Headers',formula.text)
                            self.assertTrue(formula.text.startswith(('SUMIFS(', 'SUBTOTAL(103,')))
