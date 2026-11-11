"""Detached PDF pagination and required bilingual wording; no database use."""
import io,unittest
from copy import deepcopy
from types import SimpleNamespace
from datetime import date
from pypdf import PdfReader
from .adjusted_pdf import render,CLARIFICATION
from django.core.exceptions import ValidationError

class AdjustedPdfTests(unittest.TestCase):
    def fixture(self):
        line={'id':1,'code':'DEMO','description':'Fictional training switch','unit':'pcs','original_quantity':'10.00',
            'returned_quantity':'3.00','net_quantity':'7.00','unit_price':'100.0000','original_value':'1000.00','returned_value':'300.00','net_value':'700.00'}
        snapshot={'branding':{'strategy':'no-logo'},'company':{'company_name':'MICROCOM TRAINING','company_address':'Fictional address'},
            'branch':{'code':'DEMO','name':'Training branch'},'invoice_number':'FAC/DEMO','request_reference':'REQ/DEMO',
            'currency':'USD','original_total':'1000.00','returned_total':'300.00','net_total':'700.00','lines':[line],
            'returns':[{'number':'BR/DEMO','issue_date':'2026-11-11','total':'300.00'}]}
        return SimpleNamespace(snapshot=snapshot,number='EAR/DEMO',issue_date=date(2026,11,11),issuer_name='Training issuer')

    def test_many_materials_paginate_with_reference(self):
        s=self.fixture();s.snapshot['lines']*=75
        pages=PdfReader(io.BytesIO(render(s,'en'))).pages
        self.assertGreater(len(pages),1)
        for page in pages:self.assertIn('EAR/DEMO',page.extract_text())

    def test_long_description_splits_readably(self):
        s=self.fixture();s.snapshot['lines'][0]['description']='Fictional material description '*400
        pdf=PdfReader(io.BytesIO(render(s,'fr')))
        self.assertGreater(len(pdf.pages),1)
        self.assertIn('700.00',' '.join(p.extract_text() for p in pdf.pages))

    def test_mandatory_clarifications_and_fractional_precision(self):
        s=self.fixture();s.snapshot['lines'][0]['unit_price']='0.1234'
        for language,phrase in [('en',CLARIFICATION),('fr',"Ce document présente le rapprochement des valeurs du matériel après les retours enregistrés.")]:
            text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(render(s,language))).pages)
            self.assertIn(phrase,' '.join(text.split()));self.assertIn('0.1234',text)

    def test_unsupported_language_is_rejected(self):
        with self.assertRaises(ValidationError):render(self.fixture(),'de')

    def test_portrait_invoice_layout_multiple_returns_and_detached_values(self):
        statement = self.fixture()
        statement.snapshot['branch']['physical_address'] = '100 Fictional Avenue'
        statement.snapshot['returns'] = [
            {'number': 'BR/FIRST', 'issue_date': '2026-11-10', 'total': '200.00'},
            {'number': 'BR/SECOND', 'issue_date': '2026-11-11', 'total': '100.00'},
        ]
        before = deepcopy(statement.snapshot)
        for language in ('en', 'fr'):
            pdf = PdfReader(io.BytesIO(render(statement, language)))
            for page in pdf.pages:
                self.assertAlmostEqual(float(page.mediabox.width), 595.2756, places=2)
                self.assertAlmostEqual(float(page.mediabox.height), 841.8898, places=2)
                self.assertIn('EAR/DEMO', page.extract_text())
            text = ' '.join(page.extract_text() for page in pdf.pages)
            for value in ('FAC/DEMO', 'BR/FIRST', 'BR/SECOND', '200.00', '100.00', '1000.00', '300.00', '700.00', '100 Fictional Avenue'):
                self.assertIn(value, text)
            self.assertIn('État récapitulatif après retours' if language == 'fr' else 'Adjusted Invoice Statement', text)
        self.assertEqual(statement.snapshot, before)

    def test_many_returns_repeat_table_header_and_keep_footer(self):
        statement = self.fixture()
        statement.snapshot['returns'] = [
            {'number': 'BR/DEMO/%03d' % i, 'issue_date': '2026-11-11', 'total': '1.00'}
            for i in range(100)
        ]
        for language in ('en', 'fr'):
            pdf = PdfReader(io.BytesIO(render(statement, language)))
            self.assertGreater(len(pdf.pages), 1)
            text = ' '.join(page.extract_text() for page in pdf.pages)
            self.assertIn('BR/DEMO/099', text)
            for number, page in enumerate(pdf.pages, 1):
                self.assertIn('EAR/DEMO', page.extract_text())
                self.assertIn('Page ' + str(number), page.extract_text())
