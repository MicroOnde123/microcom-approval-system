"""Deferred PostgreSQL tests. Never run against the development database."""
from datetime import timedelta
import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TransactionTestCase

from . import services
from .models import Invoice, InvoiceLine, InvoiceAuditEvent, DocumentSequence
from .test_lifecycle import LifecycleFixtures


class FinalizationClockDatabaseTests(LifecycleFixtures, TransactionTestCase):
    def _post_teardown(self):
        try:
            super()._post_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE invoicing_finalreference")

    def prepare(self):
        invoice = self.create(); self.price(invoice); sequence = self.verified_sequence()
        return invoice, sequence

    def test_model_validation_delay_longer_than_guard_window_succeeds(self):
        invoice, sequence = self.prepare()
        original = Invoice.full_clean
        def delayed(instance, *args, **kwargs):
            original(instance, *args, **kwargs)
            time.sleep(6)
        with patch.object(Invoice, "full_clean", delayed):
            result = self.finalize(invoice)
        self.assertEqual(result.status, "FINALIZED")
        self.assertEqual(result.issue_date, services.business_date(result.finalized_at, result.business_timezone))
        self.assertEqual(result.total, 20)
        sequence.refresh_from_db(); self.assertEqual(sequence.next_counter, 2)

    def test_stale_business_date_is_rejected_and_everything_rolls_back(self):
        invoice, sequence = self.prepare()
        before = {model: list(model.objects.order_by("pk").values())
            for model in (Invoice, InvoiceLine, InvoiceAuditEvent, DocumentSequence)}
        original = services._issuance_sequence
        def yesterday(*args, **kwargs):
            seq, moment, day = original(*args, **kwargs)
            return seq, moment, day - timedelta(days=1)
        with patch.object(services, "_issuance_sequence", side_effect=yesterday), self.assertRaises(ValidationError):
            self.finalize(invoice)
        self.assertEqual(before, {model: list(model.objects.order_by("pk").values()) for model in before})
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM invoicing_finalreference WHERE document_type='INVOICE' AND document_id=%s", [invoice.pk])
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_audit_failure_after_update_still_rolls_back(self):
        invoice, sequence = self.prepare()
        with patch.object(services, "_event", side_effect=ValidationError("Synthetic failure")), self.assertRaises(ValidationError):
            self.finalize(invoice)
        invoice.refresh_from_db(); sequence.refresh_from_db()
        self.assertEqual(invoice.status, "DRAFT"); self.assertIsNone(invoice.number)
        self.assertIsNone(invoice.finalized_at); self.assertIsNone(invoice.total)
        self.assertEqual(sequence.next_counter, 1)
