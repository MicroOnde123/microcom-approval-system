"""Statement display regression tests; no database writes or live records."""
from types import SimpleNamespace
from uuid import uuid4
from django.test import SimpleTestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.utils.translation import override
from .test_adjusted_pdf import AdjustedPdfTests
from .templatetags.adjusted_presentation import statement_amount, readable_reference

class AdjustedPresentationTests(SimpleTestCase):
    def test_amounts_preserve_precision_and_references(self):
        self.assertEqual(statement_amount('1000.00'), '1,000.00')
        self.assertEqual(statement_amount('0.1234'), '0.1234')
        self.assertEqual(readable_reference(str(uuid4())), '')
        self.assertEqual(readable_reference('REQ/2026/001'), 'REQ/2026/001')

    def test_bilingual_summary_names_amounts_and_no_uuid(self):
        snapshot = AdjustedPdfTests().fixture().snapshot
        key = str(uuid4()); snapshot['request_reference'] = key
        for language in ('en', 'fr'):
            with override(language):
                html = render_to_string('invoicing/adjusted/summary.html', {'snapshot': snapshot})
                self.assertNotIn(key, html)
                self.assertIn('1,000.00 USD', html)
                self.assertIn('Fictional training switch', html)
                self.assertIn('statement-material-code', html)
                self.assertIn('tabindex="0"', html)
        self.assertEqual(snapshot['request_reference'], key)

    def test_document_actions_permissions_and_post_routes(self):
        statement = AdjustedPdfTests().fixture()
        request = RequestFactory().get('/invoices/adjusted-statements/1/')
        request.user = AnonymousUser()
        statement.pk = 1; statement.invoice_id = 99; statement.issued_at = statement.issue_date
        for language in ('en', 'fr'):
            with override(language):
                for permitted in (True, False):
                    html = render_to_string('invoicing/adjusted/detail.html', {
                        'request': request, 'statement': statement, 'snapshot': statement.snapshot, 'can_document': permitted})
                    self.assertEqual('class="statement-actions"' in html, permitted)
                    if permitted:
                        self.assertIn('action="/invoices/adjusted-statements/1/print/"', html)
                        self.assertIn('action="/invoices/adjusted-statements/1/download/"', html)
                        self.assertIn('btn btn-secondary', html)
                        self.assertIn('method="post"', html)
