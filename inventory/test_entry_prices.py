"""Independent Material Entries pricing; synthetic PostgreSQL data only."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
from .models import MaterialPriceChange, MaterialReceipt
from .pricing import update_price, price_state, price_change_context
from .test_pricing import PricingFixtures, ConcurrentPricingTests
from .test_entry_drafts import DraftFixtures


class EntryPriceTests(PricingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.stock = get_user_model().objects.create_user(username="price-stock", can_manage_stock=True)
        self.url = reverse("material_entry_price", args=[self.material.pk])
        self.client.force_login(self.stock)

    def post_data(self, **changes):
        revision = self.client.get(self.url).json()["revision"]
        return {"price": "5", "currency": "USD", "reason": "Catalogue correction", "revision": revision, **changes}

    def test_stock_personnel_and_admin_can_edit_independently(self):
        for actor, value in ((self.stock, "5"), (self.user, "7")):
            self.client.force_login(actor)
            self.assertEqual(self.client.post(self.url, self.post_data(price=value)).status_code, 200)
            self.material.refresh_from_db()
            self.assertEqual((self.material.unit_price, self.material.stock_quantity), (Decimal(value), 10))
            record = MaterialPriceChange.objects.first()
            self.assertEqual((record.new_price, record.user_id, record.reason, record.source),
                             (Decimal(value), actor.pk, "Catalogue correction", "service"))
            self.assertFalse(MaterialReceipt.objects.exists())
            self.assertFalse(self.material.stock_movements.exists())
        # Pricing access alone does not require or grant Admin access.
        self.client.force_login(self.stock)
        self.assertNotEqual(self.client.get(reverse("admin:inventory_material_change", args=[self.material.pk])).status_code, 200)

    def test_django_price_permission_without_stock_permission(self):
        editor = get_user_model().objects.create_user(username="catalogue-editor")
        editor.user_permissions.add(Permission.objects.get(codename="change_material"))
        self.client.force_login(editor)
        self.assertEqual(self.client.get(reverse("material_entries")+"?mode=existing").status_code, 200)
        self.assertEqual(self.client.post(self.url, self.post_data()).status_code, 200)
        self.assertEqual(self.client.post(reverse("material_entries"), {"mode": "existing"}).status_code, 403)

    def test_unauthorized_inactive_csrf_and_methods(self):
        data = self.post_data()
        for actor in (None, get_user_model().objects.create_user(username="technician")):
            self.client.logout()
            if actor: self.client.force_login(actor)
            self.assertEqual(self.client.post(self.url, data).status_code, 403)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.stock.is_active = False; self.stock.save()
        self.client.force_login(self.stock)
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        csrf = Client(enforce_csrf_checks=True); csrf.force_login(self.user)
        self.assertEqual(csrf.post(self.url, data).status_code, 403)
        self.assertEqual(self.client.put(self.url).status_code, 405)
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_currency_unknown_zero_and_identical_retry(self):
        data = self.post_data(price="0")
        self.assertEqual(self.client.post(self.url, data).status_code, 200)
        self.assertEqual(self.client.post(self.url, data).status_code, 409)
        self.assertEqual(MaterialPriceChange.objects.count(), 1)
        self.assertEqual(self.client.post(self.url, self.post_data(price="0", currency="EUR")).status_code, 200)
        record = MaterialPriceChange.objects.first()
        self.assertEqual((record.old_price, record.new_price, record.old_currency, record.new_currency),
                         (Decimal("0"), Decimal("0"), "USD", "EUR"))
        self.assertEqual(self.client.post(self.url, self.post_data(price="", currency="EUR")).status_code, 200)
        self.material.refresh_from_db(); self.assertIsNone(self.material.unit_price)
        self.assertEqual(self.material.stock_quantity, 10)

    def test_invalid_values_reasons_and_tampered_or_stale_revision(self):
        for changes in ({"price": "-1"}, {"price": "invalid"}, {"price": "1.234"},
                        {"currency": "BAD"}, {"reason": "   "}):
            self.assertEqual(self.client.post(self.url, self.post_data(**changes)).status_code, 400)
        self.assertEqual(self.client.post(self.url, self.post_data(revision="tampered")).status_code, 409)
        stale = self.post_data()
        self.assertEqual(self.client.post(self.url, self.post_data(price="3")).status_code, 200)
        self.assertEqual(self.client.post(self.url, stale).status_code, 409)
        self.assertEqual(MaterialPriceChange.objects.count(), 1)

    def test_stock_permission_is_checked_by_database_and_admin_context_stays_restricted(self):
        self.stock.can_manage_stock = False
        get_user_model().objects.filter(pk=self.stock.pk).update(can_manage_stock=False)
        # Simulate stale application evidence; the trigger rechecks the actual role.
        self.stock.can_manage_stock = True
        with self.assertRaises(IntegrityError):
            update_price(self.material.pk, self.stock, price=Decimal("2"), currency="USD", reason="Revoked", expected_state=price_state(self.material))
        with self.assertRaises(PermissionDenied):
            with price_change_context(self.stock, "No admin permission", "admin"): pass
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_translated_interface_and_errors(self):
        for language, label, success, required in (
            ("fr", "Modifier le prix", "Le prix du catalogue a \u00e9t\u00e9 enregistr\u00e9.", "Ce champ est obligatoire."),
            ("en", "Modify Price", "Catalogue price saved successfully.", "This field is required.")):
            page = self.client.get(reverse("material_entries")+"?mode=existing", HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(page, label)
            response = self.client.post(self.url, self.post_data(reason=""), HTTP_ACCEPT_LANGUAGE=language)
            self.assertIn(required, response.json()["errors"]["reason"])
            response = self.client.post(self.url, self.post_data(price="2" if language == "fr" else "3"), HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.json()["message"], success)


class EntryPriceDraftTests(DraftFixtures, TestCase):
    def test_price_save_preserves_exact_draft_and_all_receipt_values(self):
        payload = self.payload("existing", quantity="5", supplier="Supplier", delivery_reference="REF", notes="Partial receipt")
        _, draft = self.save(payload)
        before = (draft.data, draft.version, draft.status, draft.updated_at)
        url = reverse("material_entry_price", args=[self.material.pk])
        revision = self.client.get(url).json()["revision"]
        self.assertEqual(self.client.post(url, {"price": "8", "currency": "EUR", "reason": "Catalogue", "revision": revision}).status_code, 200)
        draft.refresh_from_db()
        self.assertEqual((draft.data, draft.version, draft.status, draft.updated_at), before)
        response = self.client.get(self.resume_url(draft))
        for field in ("quantity", "supplier", "delivery_reference", "notes", "received_on"):
            self.assertEqual(str(response.context["receipt_form"][field].value()), str(payload[field]))
        self.assertEqual(response.context["selected_material"].unit_price, Decimal("8"))
        self.assertFalse(MaterialReceipt.objects.exists())


class StockPriceConcurrencyTests(ConcurrentPricingTests):
    def setUp(self):
        super().setUp()
        self.user.is_superuser = False
        self.user.is_staff = False
        self.user.can_manage_stock = True
        self.user.save()
