"""HTTP regressions for receipt payload verification, including PostgreSQL races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.utils.translation import gettext, override

from .entry_services import new_token, receive_stock
from .entry_views import material_entries
from .models import Material, MaterialCategory, MaterialReceipt, MaterialReceiptLine
from .test_material_entries import Fixtures, reviewed_payload
from requests_app.models import StockMovement


class RetryFixtures(Fixtures):
    def payload(self, mode):
        return reviewed_payload(self.user, {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "token": new_token(self.user, mode)})

    def snapshot(self):
        return [list(model.objects.order_by("pk").values()) for model in
                (Material, MaterialReceipt, MaterialReceiptLine, StockMovement)]


class ReceiptRetryViewTests(RetryFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_identical_retries_reach_service_and_preserve_prg_and_stock(self):
        for mode in ("new", "existing"):
            with self.subTest(mode=mode):
                payload = self.payload(mode)
                with patch("inventory.entry_views.receive_stock", wraps=receive_stock) as service:
                    first = self.client.post("/materials/entries/", payload)
                    self.assertEqual(first.status_code, 302)
                    before = self.snapshot()
                    for _ in range(2):
                        retry = self.client.post("/materials/entries/", payload)
                        self.assertEqual(retry.status_code, 302)
                        self.assertEqual(retry.url, first.url)
                        self.assertEqual(self.snapshot(), before)
                    self.assertEqual(service.call_count, 3)
                self.assertContains(self.client.get(first.url), "Receipt completed")
        self.assertEqual(MaterialReceipt.objects.count(), 2)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_altered_receipt_and_material_details_are_rejected_in_both_languages(self):
        other = Material.objects.create(name="Other", code="OTHER", category=self.category, stock_quantity=7)
        category = MaterialCategory.objects.create(name="Other category", code="OTHER")
        receipt_changes = {"quantity": "3", "received_on": "2026-11-04", "supplier": "Different",
                           "delivery_reference": "Different", "notes": "Different"}
        material_changes = {"name": "Different", "code": "DIFFERENT", "category": category.pk,
                            "description": "Different", "unit": "boxes", "minimum_stock_level": "2",
                            "unit_price": "10", "currency": "EUR", "is_active": ""}
        for mode in ("new", "existing"):
            payload = self.payload(mode)
            self.assertEqual(self.client.post("/materials/entries/", payload).status_code, 302)
            before = self.snapshot()
            changes = {**receipt_changes, **(material_changes if mode == "new" else {"material": other.pk})}
            for language in ("en", "fr"):
                self.client.cookies["django_language"] = language
                with override(language):
                    message = gettext("This receipt form has already been used with different data.")
                for field, value in changes.items():
                    with self.subTest(mode=mode, language=language, field=field):
                        with patch("inventory.entry_views.receive_stock", wraps=receive_stock) as service:
                            response = self.client.post("/materials/entries/", reviewed_payload(self.user, {**payload, field: value}))
                            self.assertEqual(service.call_count, 1)
                        self.assertContains(response, message)
                        self.assertNotIn("Location", response)
                        self.assertEqual(self.snapshot(), before)
            self.client.cookies["django_language"] = "en"

    def test_invalid_retry_forms_do_not_reach_stock_service_or_change_records(self):
        for mode in ("new", "existing"):
            payload = self.payload(mode)
            self.assertEqual(self.client.post("/materials/entries/", payload).status_code, 302)
            before = self.snapshot()
            changes = {"quantity": "-1", "received_on": "invalid", "supplier": "x" * 201}
            changes.update({"name": "", "unit_price": "-1"} if mode == "new" else {"material": "invalid"})
            for field, value in changes.items():
                with self.subTest(mode=mode, field=field), patch("inventory.entry_views.receive_stock") as service:
                    response = self.client.post("/materials/entries/", {**payload, field: value})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context["receipt_form"].errors or response.context["material_form"].errors)
                    service.assert_not_called()
                    self.assertEqual(self.snapshot(), before)

    def test_fresh_duplicate_material_code_is_still_rejected(self):
        payload = {**self.payload("new"), "code": self.material.code}
        before = self.snapshot()
        response = self.client.post("/materials/entries/", payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["receipt_form"].errors or response.context["material_form"].errors)
        self.assertEqual(self.snapshot(), before)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks and concurrent unique inserts required")
class ConcurrentReceiptRetryViewTests(RetryFixtures, TransactionTestCase):
    def submit_concurrently(self, payloads):
        barrier = Barrier(2)
        def synchronized_service(**kwargs):
            barrier.wait(timeout=10)
            return receive_stock(**kwargs)
        def worker(payload):
            close_old_connections()
            try:
                request = RequestFactory().post("/materials/entries/", payload)
                request.user = self.user
                request._dont_enforce_csrf_checks = True
                response = material_entries(request)
                return response.status_code, response.get("Location"), response.content.decode()
            finally:
                close_old_connections()
        with patch("inventory.entry_views.receive_stock", side_effect=synchronized_service):
            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(worker, payloads))

    def test_concurrent_identical_http_retries(self):
        for mode in ("new", "existing"):
            with self.subTest(mode=mode):
                payload = self.payload(mode)
                results = self.submit_concurrently([payload, payload])
                self.assertEqual([result[0] for result in results], [302, 302])
                self.assertEqual(results[0][1], results[1][1])
                material = Material.objects.get(code="BOLT") if mode == "new" else Material.objects.get(pk=self.material.pk)
                self.assertEqual(material.stock_quantity, 2.5 if mode == "new" else 12.5)
        self.assertEqual(MaterialReceipt.objects.count(), 2)
        self.assertEqual(MaterialReceiptLine.objects.count(), 2)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_concurrent_different_payloads_have_exactly_one_winner(self):
        for mode in ("new", "existing"):
            with self.subTest(mode=mode):
                payload = self.payload(mode)
                results = self.submit_concurrently([payload, reviewed_payload(self.user, {**payload, "quantity": "3"})])
                self.assertEqual(sorted(result[0] for result in results), [200, 302])
                rejected = next(result for result in results if result[0] == 200)
                self.assertIn("This receipt form has already been used with different data.", rejected[2])
                material = Material.objects.get(code="BOLT") if mode == "new" else Material.objects.get(pk=self.material.pk)
                line = MaterialReceiptLine.objects.get(material=material)
                self.assertEqual(material.stock_quantity, line.quantity + (0 if mode == "new" else 10))
                before = self.snapshot()
                winning_payload = payload if line.quantity == 2.5 else reviewed_payload(self.user, {**payload, "quantity": "3"})
                request = RequestFactory().post("/materials/entries/", winning_payload)
                request.user = self.user
                request._dont_enforce_csrf_checks = True
                self.assertEqual(material_entries(request).status_code, 302)
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(MaterialReceipt.objects.count(), 2)
        self.assertEqual(StockMovement.objects.count(), 2)
