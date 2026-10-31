"""Pending isolated-PostgreSQL regression coverage. Never run against development."""
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase
from django.utils.translation import override

from .models import Invoice, InvoiceLine, InvoiceAuditEvent
from .documents import _snapshot
from .pdf import render_pdf
from .pdf_test_tools import pdf_text
from .test_lifecycle import LifecycleFixtures


class InvoiceAddressTests(LifecycleFixtures, TransactionTestCase):
    def _post_teardown(self):
        try:
            super()._post_teardown()
        finally:
            # Match the existing isolated-test cleanup for this unmanaged table.
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE invoicing_finalreference")

    def test_missing_address_rolls_back_before_number_and_financial_writes(self):
        invoice = self.create(); self.price(invoice); sequence = self.verified_sequence()
        before = list(Invoice.objects.filter(pk=invoice.pk).values())
        lines = list(InvoiceLine.objects.filter(invoice=invoice).values())
        audits = InvoiceAuditEvent.objects.filter(invoice=invoice).count()
        self.branch.physical_address = " \n "; self.branch.save(update_fields=["physical_address"])
        for language in ("en", "fr"):
            with override(language), self.assertRaises(ValidationError):
                self.finalize(invoice)
        self.assertEqual(list(Invoice.objects.filter(pk=invoice.pk).values()), before)
        self.assertEqual(list(InvoiceLine.objects.filter(invoice=invoice).values()), lines)
        self.assertEqual(InvoiceAuditEvent.objects.filter(invoice=invoice).count(), audits)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, sequence.starting_value)

    def test_address_at_issuance_is_frozen_and_legacy_document_supported(self):
        invoice = self.create(); self.price(invoice); self.verified_sequence()
        self.branch.physical_address = "12, avenue Équateur\nKinshasa"
        self.branch.save(update_fields=["physical_address"])
        invoice = self.finalize(invoice)
        frozen = deepcopy(invoice.succursale_snapshot)
        self.assertEqual(frozen["physical_address"], self.branch.physical_address)
        self.branch.physical_address = "NEW LIVE ADDRESS"; self.branch.save(update_fields=["physical_address"])
        invoice.refresh_from_db(); self.assertEqual(invoice.succursale_snapshot, frozen)
        for language in ("en", "fr"):
            text = pdf_text(render_pdf(_snapshot(invoice), language=language))
            # Address is drawn only from the immutable snapshot.
            self.assertIn("12, avenue Équateur", text); self.assertNotIn("NEW LIVE ADDRESS", text)
            self.assertIn(frozen["name"], text)
            self.assertEqual(_snapshot(invoice)["branch"]["physical_address"], frozen["physical_address"])
        invoice.succursale_snapshot = {key: value for key, value in frozen.items() if key != "physical_address"}
        self.assertTrue(render_pdf(_snapshot(invoice), language="fr").startswith(b"%PDF-"))
