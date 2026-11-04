from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, RequestFactory, Client
from django.utils.translation import override
from .entry_services import receive_stock, new_token
from .entry_views import material_entries
from .models import Material, MaterialCategory, MaterialReceipt, MaterialReceiptLine
from requests_app.models import StockMovement


def reviewed_payload(user, payload):
    """Build a valid review proof for focused service/HTTP regression fixtures."""
    from .entry_forms import ReceiptForm, ExistingReceiptForm, NewMaterialForm
    from .entry_review import service_arguments, sign_review
    mode = payload["mode"]
    receipt = (ReceiptForm if mode == "new" else ExistingReceiptForm)(payload)
    material = NewMaterialForm(payload, defer_unique_validation=True)
    assert receipt.is_valid(), receipt.errors
    if mode == "new":
        assert material.is_valid(), material.errors
    return {**payload, "action": "confirm", "review_proof": sign_review(service_arguments(user, mode, receipt, material))}


class Fixtures:
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="stock", can_manage_stock=True)
        self.category = MaterialCategory.objects.create(name="Tools", code="TOOLS")
        self.material = Material.objects.create(name="Cable", code="CAB", category=self.category, unit="m", stock_quantity=10)
        self.data = {"quantity": "2.50", "received_on": "2026-11-03", "supplier": "Supplier", "delivery_reference": "DEL-1", "notes": "Test"}
        self.new = {"name": "Bolt", "code": "BOLT", "category": self.category.pk, "unit": "pcs", "minimum_stock_level": "1", "currency": "USD", "is_active": True}

    def receive(self, token=None, mode="existing", **kwargs):
        return receive_stock(user=self.user, mode=mode, token=token or new_token(self.user, mode), receipt_data=kwargs.pop("receipt_data", self.data), material_id=self.material.pk if mode == "existing" else None, material_data=self.new if mode == "new" else None, **kwargs)


class MaterialEntryTests(Fixtures, TestCase):
    def test_registration_and_in_movement(self):
        receipt, created = self.receive(mode="new")
        material = Material.objects.get(code="BOLT")
        self.assertTrue(created)
        self.assertEqual(material.stock_quantity, Decimal("2.50"))
        line = receipt.lines.get()
        self.assertEqual(line.movement.movement_type, "IN")
        self.assertIsNone(line.movement.request_id)
        self.assertEqual(line.movement.performed_by, self.user)
        self.assertEqual(line.quantity, Decimal("2.50"))
        self.assertEqual(receipt.supplier, "Supplier")

    def test_existing_receipt_preserves_history_and_retry(self):
        old = StockMovement.objects.create(material=self.material, quantity=1, movement_type="IN")
        token = new_token(self.user, "existing")
        first, _ = self.receive(token)
        retry, created = self.receive(token)
        self.assertEqual(first.pk, retry.pk)
        self.assertFalse(created)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, Decimal("12.50"))
        self.assertTrue(StockMovement.objects.filter(pk=old.pk).exists())
        self.assertEqual(StockMovement.objects.count(), 2)
        with self.assertRaises(ValidationError):
            self.receive(token, receipt_data={**self.data, "quantity": "3"})

    def test_new_retry_does_not_create_duplicate_material(self):
        token = new_token(self.user, "new")
        self.receive(token, "new")
        self.assertFalse(self.receive(token, "new")[1])
        self.assertEqual(Material.objects.filter(code="BOLT").count(), 1)

    def test_invalid_quantities_and_duplicate_codes(self):
        for quantity in ("-1", "0", "NaN", "Infinity", "0.001", "100000000"):
            with self.subTest(quantity=quantity), self.assertRaises(ValidationError):
                self.receive(receipt_data={**self.data, "quantity": quantity})
        self.new["code"] = "CAB"
        with self.assertRaises(ValidationError):
            self.receive(mode="new")
        self.assertFalse(MaterialReceipt.objects.exists())
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)

    def test_rollback_new_and_existing(self):
        for mode in ("new", "existing"):
            with patch("inventory.entry_services.MaterialReceiptLine.objects.create", side_effect=RuntimeError("failure")):
                with self.assertRaises(RuntimeError):
                    self.receive(mode=mode)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)
        self.assertFalse(Material.objects.filter(code="BOLT").exists())
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_new_material_starts_at_zero_and_failed_token_can_retry(self):
        token = new_token(self.user, "new")
        saved_quantities = []
        original_save = Material.save
        def capture(instance, *args, **kwargs):
            if instance.code == "BOLT":
                saved_quantities.append(instance.stock_quantity)
            return original_save(instance, *args, **kwargs)
        with patch("inventory.entry_services.MaterialReceiptLine.objects.create", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError): self.receive(token, "new")
        with patch.object(Material, "save", capture):
            self.receive(token, "new")
        self.assertEqual(saved_quantities, [0, Decimal("2.50")])
        self.assertEqual(MaterialReceipt.objects.count(), 1)

    def test_stock_overflow_rolls_back(self):
        self.material.stock_quantity = Decimal("99999999.99")
        self.material.save()
        with self.assertRaises(ValidationError):
            self.receive()
        self.assertFalse(MaterialReceipt.objects.exists())

    def test_permissions_service_and_view(self):
        self.assertEqual(self.client.get("/materials/entries/").status_code, 302)
        for active, manage, superuser, allowed in [(True, False, False, False), (False, True, True, False), (True, True, False, True), (True, False, True, True)]:
            self.user.is_active, self.user.can_manage_stock, self.user.is_superuser = active, manage, superuser
            self.user.save()
            request = RequestFactory().get("/materials/entries/")
            request.user = self.user
            if allowed:
                self.assertEqual(material_entries(request).status_code, 200)
                self.receive()
            else:
                with self.assertRaises(PermissionDenied): material_entries(request)
                with self.assertRaises(PermissionDenied): self.receive()

    def test_language_and_stock_display(self):
        self.client.force_login(self.user)
        for language, title, action in [("en", "Material Entries", "Register New Material"), ("fr", "Entr\u00e9es de stock", "Enregistrer un nouveau mat\u00e9riel")]:
            with override(language):
                response = self.client.get("/materials/entries/", HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, title)
                self.assertContains(response, action)
                self.assertContains(response, "csrfmiddlewaretoken")
        response = self.client.get("/materials/entries/?mode=existing")
        self.assertContains(response, "material-stock-options")
        self.assertContains(response, '10.00')
        self.assertNotContains(response, 'Category:')

    def test_post_redirect_and_browser_retry(self):
        self.client.force_login(self.user)
        for mode in ("new", "existing"):
            payload = {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}), "mode": mode, "token": new_token(self.user, mode)}
            payload = reviewed_payload(self.user, payload)
            first = self.client.post("/materials/entries/", payload)
            self.assertEqual(first.status_code, 302)
            second = self.client.post("/materials/entries/", payload)
            self.assertEqual(first.url, second.url)
            self.assertContains(self.client.get(first.url), "Receipt completed")
        self.assertEqual(MaterialReceipt.objects.count(), 2)

    def test_token_ownership_and_csrf(self):
        other = get_user_model().objects.create_user(username="other", can_manage_stock=True)
        with self.assertRaises(ValidationError):
            self.receive(new_token(other, "existing"))
        with self.assertRaises(ValidationError):
            self.receive("forged")
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post("/materials/entries/", {}).status_code, 403)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks required")
class ConcurrentReceiptTests(Fixtures, TransactionTestCase):
    def run_receipts(self, tokens, mode="existing"):
        barrier = Barrier(2)
        def worker(token):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                return self.receive(token, mode)[0].pk
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, tokens))

    def test_parallel_distinct_receipts(self):
        self.run_receipts([new_token(self.user, "existing") for _ in range(2)])
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 15)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_parallel_retry(self):
        for mode in ("existing", "new"):
            token = new_token(self.user, mode)
            ids = self.run_receipts([token, token], mode)
            self.assertEqual(ids[0], ids[1])
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, Decimal("12.50"))
        self.assertEqual(Material.objects.get(code="BOLT").stock_quantity, Decimal("2.50"))
        self.assertEqual(StockMovement.objects.count(), 2)
