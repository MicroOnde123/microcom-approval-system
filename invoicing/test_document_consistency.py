"""Synthetic document presentation and delivery; no database or network."""
from copy import deepcopy
from decimal import Decimal
import base64
import io
import json
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.utils.translation import override
from .admin import DocumentSequenceAdmin
from .models import DocumentSequence
from .document_presentation import amount_words
from .print_delivery import print_response
from .pdf import render_pdf
from .return_note_pdf import render_pdf as render_return
from .test_return_note_pdf import snapshot
from .pdf_test_tools import pdf_text
from inventory.test_address_offline import AddressOfflineTests


class DocumentConsistencyTests(unittest.TestCase):
    def test_invoice_address_and_language_are_frozen_presentation(self):
        source = AddressOfflineTests().snapshot(); before = deepcopy(source)
        for language in ("en", "fr"):
            text = pdf_text(render_pdf(source, language))
            for line in source["branch"]["physical_address"].splitlines():
                self.assertIn("".join(line.split()), "".join(text.split()))
            self.assertIn("two US dollars" if language == "en" else source["amount_words_fr"], text)
        self.assertEqual(source, before)
        del source["branch"]["physical_address"]
        self.assertTrue(render_pdf(source, "en").startswith(b"%PDF-"))

    def test_return_note_reuses_client_layout_without_issuer_and_retains_financial_values(self):
        source = snapshot(); source["branch"]["physical_address"] = "Avenue Équateur 12\nKinshasa"
        before = deepcopy(source)
        for language in ("en", "fr"):
            text = pdf_text(render_return(source, language))
            for value in (source["branch"]["name"], "Avenue Équateur 12", source["number"],
                          source["original"]["number"], "2.00", "4.00", "6.00", "42"):
                self.assertIn(value, text)
            for value in source["company"].values(): self.assertNotIn(value, text)
            self.assertIn("two US dollars" if language == "en" else source["amount_words_fr"], text)
        self.assertEqual(source, before)

    def test_english_words_zero_cents_and_large_amounts_preserve_french(self):
        for amount, currency, text in (("0", "EUR", "zero euros"), ("1.01", "USD", "one US dollar and one cent"),
                                      ("150", "USD", "one hundred and fifty US dollars"),
                                      ("1.50", "CDF", "one Congolese franc and fifty centimes"),
                                      ("1000000", "CDF", "one million Congolese francs")):
            self.assertEqual(amount_words(Decimal(amount), currency, "en", "frozen"), text)
            self.assertEqual(amount_words(Decimal(amount), currency, "fr", "frozen"), "frozen")

    def test_private_print_response_contains_only_authorized_pdf_and_no_public_url(self):
        for language, label in (("en", "Download PDF"), ("fr", "Télécharger PDF")):
            with override(language):
                response = print_response(RequestFactory().post("/synthetic/"), b"%PDF-synthetic", "safe.pdf")
            body = response.content.decode()
            encoded = json.loads(re.search(r'<script id="private-pdf"[^>]*>(.*?)</script>', body).group(1))
            self.assertEqual(base64.b64decode(encoded), b"%PDF-synthetic")
            self.assertIn(label, body); self.assertIn("data-pdf-frame", body)
            self.assertIn('lang="' + language + '"', body)
            self.assertIn("private, no-store", response["Cache-Control"])
            self.assertNotIn("http://", body); self.assertNotIn("https://", body)

    def test_admin_protects_sequences_used_by_finalized_return_notes(self):
        sequence = Mock()
        sequence.invoice_documents.filter.return_value.exists.return_value = False
        sequence.creditnote_documents.filter.return_value.exists.return_value = False
        sequence.materialreturnnote_documents.filter.return_value.exists.return_value = True
        admin = DocumentSequenceAdmin(DocumentSequence, AdminSite())
        fields = admin.get_readonly_fields(SimpleNamespace(), sequence)
        for field in ("document_type", "year", "series", "number_format", "starting_value", "verification_evidence"):
            self.assertIn(field, fields)

    def test_active_language_controls_return_note_generation_with_document_authorization(self):
        from . import return_note_views as views, return_note_access as access
        user = SimpleNamespace(is_authenticated=True)
        request = RequestFactory().post("/synthetic/", {"language": "en"}); request.user = user
        note = SimpleNamespace(pk=1, invoice=SimpleNamespace(request_id=7))
        with override("fr"), patch.object(access, "ui_enabled", return_value=True), \
                patch.object(views.issuance, "get_material_return_note", return_value=note), \
                patch.object(views, "authorize_return_note") as permission, \
                patch.object(views, "generate_pdf", return_value=SimpleNamespace(pk=2)) as generate, \
                patch.object(views, "download_pdf", return_value=(None, io.BytesIO(b"%PDF-synthetic"))):
            response = views.pdf(request, 1)
        permission.assert_called_once_with(user, 7, document=True)
        generate.assert_called_once_with(1, user, language="fr")
        self.assertIn(b"data-pdf-frame", response.content)
