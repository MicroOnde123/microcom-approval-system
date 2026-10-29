"""Deferred: run only against an explicitly authorized isolated PostgreSQL DB."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from core.models import CompanyDocumentSettings
from .models import DocumentSequence
from .year_preparation import prepare_invoice_year


class PreparationPostgreSQLTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL financial triggers and row locks required")
        CompanyDocumentSettings.objects.create(pk=1, company_name="Synthetic", company_address="Synthetic", contact_details="Synthetic")
        self.admin = get_user_model().objects.create_superuser(username="annual-test-admin", password="synthetic-only")
        self.source = DocumentSequence.objects.create(document_type="INVOICE", year=2026, series="MAIN",
            number_format="FAC/{number:04d}/{year}", starting_value=17, next_counter=17)
        self.source.attest(self.admin, "Synthetic numbering history")
        self.clock = patch("invoicing.year_preparation.database_now", return_value=datetime(2026, 10, 1, tzinfo=timezone.utc))
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_idempotency_and_counter_preservation(self):
        self.assertEqual(prepare_invoice_year()["prepared"], ["MAIN"])
        self.assertEqual(prepare_invoice_year()["existing"], ["MAIN"])
        self.source.refresh_from_db()
        self.assertEqual(self.source.next_counter, 17)
        target = DocumentSequence.objects.get(year=2027)
        self.assertEqual(target.next_counter, 1)
        self.assertFalse(target.is_verified)
        self.assertIsNone(target.verified_at)
        self.assertEqual(target.verification_evidence, "")

    def test_concurrent_preparation(self):
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return prepare_invoice_year()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(sum(len(report["prepared"]) for report in reports), 1)
        self.assertEqual(DocumentSequence.objects.filter(year=2027).count(), 1)

    def test_conflict_is_non_mutating(self):
        other = DocumentSequence.objects.create(document_type="INVOICE", year=2026, series="OTHER", number_format=self.source.number_format)
        other.attest(self.admin, "Synthetic numbering history")
        self.assertTrue(prepare_invoice_year()["conflicts"])
        self.assertFalse(DocumentSequence.objects.filter(year=2027).exists())

    def test_boundary_uses_kinshasa_year(self):
        with patch("invoicing.year_preparation.database_now", return_value=datetime(2026, 12, 31, 23, tzinfo=timezone.utc)):
            report = prepare_invoice_year()
        self.assertEqual(report["year"], 2028)
        self.assertFalse(report["prepared"])  # No approved 2027 source.
