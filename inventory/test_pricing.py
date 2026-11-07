"""Synthetic catalogue pricing regressions; run with PostgreSQL migrations."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.translation import activate, deactivate

from .models import Material, MaterialCategory, MaterialPriceChange
from .pricing import price_state, update_price


class PricingFixtures:
    def setUp(self):
        activate("en")
        self.addCleanup(deactivate)
        self.user = get_user_model().objects.create_superuser(username="price-admin", password="synthetic")
        self.category = MaterialCategory.objects.create(name="Synthetic", code="PRICE")
        self.material = Material.objects.create(category=self.category, name="Cable", code="PRICE-1", unit="m", stock_quantity=10)

    def update(self, price="2.50", currency="USD", **kwargs):
        self.material.refresh_from_db()
        return update_price(self.material.pk, self.user, price=Decimal(price) if price is not None else None,
            currency=currency, reason=kwargs.pop("reason", "Synthetic correction"),
            expected_state=kwargs.pop("expected_state", price_state(self.material)), **kwargs)


class PricingTests(PricingFixtures, TestCase):
    def form_data(self, language="en"):
        self.client.force_login(self.user)
        url = reverse("admin:inventory_material_change", args=[self.material.pk])
        response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
        form = response.context["adminform"].form
        data = {name: form[name].value() if form[name].value() is not None else "" for name in form.fields}
        return url, data

    def test_authorized_admin_stock_only_edit(self):
        url, data = self.form_data()
        data.update(stock_quantity="15")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 15)
        self.assertIsNone(self.material.unit_price)
        self.assertFalse(MaterialPriceChange.objects.exists())
        self.assertFalse(self.material.stock_movements.exists())  # Explicitly deferred Admin limitation.

    def test_authorized_admin_combined_stock_price_edit(self):
        url, data = self.form_data()
        data.update(stock_quantity="15", unit_price="5", currency="EUR", price_change_reason="Combined")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual((self.material.stock_quantity, self.material.unit_price, self.material.currency),
                         (Decimal("15"), Decimal("5"), "EUR"))
        record = MaterialPriceChange.objects.get()
        self.assertEqual((record.old_price, record.old_currency), (None, None))
        self.assertEqual((record.new_price, record.new_currency, record.user_id, record.reason, record.source),
                         (Decimal("5"), "EUR", self.user.pk, "Combined", "admin"))
        self.assertFalse(self.material.stock_movements.exists())

    def test_authorized_admin_add_with_nonzero_stock(self):
        _, data = self.form_data()
        data.update(code="OPENING-STOCK", stock_quantity="3", unit_price="5", currency="USD")
        self.assertEqual(self.client.post(reverse("admin:inventory_material_add"), data).status_code, 302)
        material = Material.objects.get(code="OPENING-STOCK")
        self.assertEqual((material.stock_quantity, material.unit_price, material.currency),
                         (Decimal("3"), Decimal("5"), "USD"))
        self.assertFalse(MaterialPriceChange.objects.exists())
        self.assertFalse(material.stock_movements.exists())

    def test_invalid_combined_edits_leave_all_values_unchanged(self):
        for changes in ({"unit_price": "-1", "price_change_reason": "Invalid price"},
                        {"unit_price": "5", "price_change_reason": ""},
                        {"unit_price": "5", "currency": "BAD", "price_change_reason": "Invalid currency"},
                        {"unit_price": "5", "stock_quantity": "invalid", "price_change_reason": "Invalid stock"}):
            url, data = self.form_data()
            data.update(stock_quantity="15", currency="USD")
            data.update(changes)
            self.assertEqual(self.client.post(url, data).status_code, 200)
            self.material.refresh_from_db()
            self.assertEqual((self.material.stock_quantity, self.material.unit_price, self.material.currency),
                             (Decimal("10"), None, None))
            self.assertFalse(MaterialPriceChange.objects.exists())

    def test_audit_failure_rolls_back_combined_admin_edit(self):
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE inventory_materialpricechange ADD CONSTRAINT synthetic_combined_failure CHECK(reason <> 'fail combined')")
        url, data = self.form_data()
        data.update(stock_quantity="15", unit_price="5", currency="EUR", price_change_reason="fail combined")
        with self.assertRaises(IntegrityError):
            self.client.post(url, data)
        self.material.refresh_from_db()
        self.assertEqual((self.material.stock_quantity, self.material.unit_price, self.material.currency),
                         (Decimal("10"), None, None))
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_stale_admin_stock_price_and_currency_updates_cannot_overwrite(self):
        for changes, message in (
            ({"stock_quantity": "15"}, "Stock has changed"),
            ({"unit_price": "5", "currency": "EUR", "price_change_reason": "Price"}, "The material price has changed"),
            ({"currency": "USD", "price_change_reason": "Currency"}, "The material price has changed")):
            url, stale = self.form_data()
            _, fresh = self.form_data()
            fresh.update(changes)
            self.assertEqual(self.client.post(url, fresh).status_code, 302)
            before = Material.objects.values().get(pk=self.material.pk)
            audits = list(MaterialPriceChange.objects.values())
            stale.update(stock_quantity="99", unit_price="99", currency="CDF", price_change_reason="Stale")
            self.assertContains(self.client.post(url, stale), message)
            self.assertEqual(Material.objects.values().get(pk=self.material.pk), before)
            self.assertEqual(list(MaterialPriceChange.objects.values()), audits)

    def test_stale_catalogue_fields_and_missing_or_tampered_revision_are_rejected(self):
        for field, value in (("description", "Concurrent description"), ("name", "Concurrent name"),
                             ("code", "CONCURRENT"), ("unit", "piece"),
                             ("minimum_stock_level", Decimal("3")), ("is_active", False),
                             ("category_id", MaterialCategory.objects.create(name="Other", code="OTHER").pk)):
            url, data = self.form_data()
            Material.objects.filter(pk=self.material.pk).update(**{field: value})
            data.update(unit_price="5", currency="USD", price_change_reason="Stale edit")
            self.assertContains(self.client.post(url, data), "Catalogue information has changed")
            self.material.refresh_from_db()
            self.assertEqual(getattr(self.material, field), value)
            self.assertIsNone(self.material.unit_price)
            self.assertFalse(MaterialPriceChange.objects.exists())
        for token in ("", "tampered"):
            url, data = self.form_data()
            data["original_catalogue"] = token
            self.assertContains(self.client.post(url, data), "Catalogue information has changed")
        # Reloading provides a current revision and permits an ordinary edit.
        url, data = self.form_data()
        data["description"] = "Reviewed correction"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.description, "Reviewed correction")

    def test_stock_and_catalogue_conflicts_render_in_both_languages(self):
        for language, stock_error, catalogue_error in (
            ("fr", "Le stock a changé", "Les informations du catalogue ont changé"),
            ("en", "Stock has changed", "Catalogue information has changed")):
            url, data = self.form_data(language)
            Material.objects.filter(pk=self.material.pk).update(stock_quantity=15 if language == "fr" else 20)
            data["stock_quantity"] = "99"
            self.assertContains(self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language), stock_error)
            url, data = self.form_data(language)
            Material.objects.filter(pk=self.material.pk).update(description=language)
            self.assertContains(self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language), catalogue_error)

    def test_admin_change_requires_reason_and_records_actor_values(self):
        url, data = self.form_data()
        data.update(unit_price="0", currency="USD")
        self.assertContains(self.client.post(url, data), "Enter a reason for the price or currency change.")
        self.assertFalse(MaterialPriceChange.objects.exists())
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        data["price_change_reason"] = "First known price"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        record = MaterialPriceChange.objects.get()
        self.assertEqual((record.old_price, record.old_currency), (None, None))
        self.assertEqual((record.new_price, record.new_currency), (Decimal("0"), "USD"))
        self.assertEqual((record.user_id, record.source, record.reason), (self.user.pk, "admin", "First known price"))
        self.assertIsNotNone(record.changed_at)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)

    def test_currency_only_and_unknown_price_changes_are_audited(self):
        self.update("0")
        url, data = self.form_data()
        data.update(currency="EUR")
        self.assertContains(self.client.post(url, data), "Enter a reason for the price or currency change.")
        self.assertEqual(MaterialPriceChange.objects.count(), 1)
        data.update(currency="EUR", price_change_reason="Currency correction")
        self.assertEqual(self.client.post(url, data).status_code, 302)
        record = MaterialPriceChange.objects.first()
        self.assertEqual((record.old_price, record.new_price, record.old_currency, record.new_currency),
                         (Decimal("0"), Decimal("0"), "USD", "EUR"))
        self.update(None, "EUR")
        self.assertIsNone(MaterialPriceChange.objects.first().new_price)
        self.update(None, "CDF")
        self.assertEqual(MaterialPriceChange.objects.first().old_currency, "EUR")

    def test_unchanged_save_and_new_material_need_no_reason_or_audit(self):
        url, data = self.form_data()
        data["name"] = "Renamed"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        data.pop("original_stock")
        data.pop("original_price")
        data.update(code="PRICE-2", stock_quantity="0", unit_price="12.50", currency="EUR")
        self.assertEqual(self.client.post(reverse("admin:inventory_material_add"), data).status_code, 302)
        self.assertEqual(Material.objects.get(code="PRICE-2").unit_price, Decimal("12.50"))
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_stale_admin_form_and_tampered_token_are_rejected(self):
        url, data = self.form_data()
        self.update("4")
        data.update(unit_price="5", currency="USD", price_change_reason="Stale price")
        self.assertContains(self.client.post(url, data), "The material price has changed.")
        data["original_price"] = "tampered"
        self.assertContains(self.client.post(url, data), "The material price has changed.")
        self.material.refresh_from_db()
        self.assertEqual(self.material.unit_price, 4)
        self.assertEqual(MaterialPriceChange.objects.count(), 1)

    def test_restored_price_does_not_make_old_revision_valid(self):
        original = price_state(self.material)
        self.update("1")
        self.update(None, None)
        with self.assertRaises(ValidationError):
            self.update("3", expected_state=original)
        self.assertEqual(MaterialPriceChange.objects.count(), 2)

    def test_ledger_is_immutable_and_cannot_be_forged(self):
        self.update()
        record = MaterialPriceChange.objects.get()
        for operation in (record.save, record.delete):
            with self.assertRaises(ValidationError):
                operation()
        for sql, args in (
            ("UPDATE inventory_materialpricechange SET reason='tampered' WHERE id=%s", [record.pk]),
            ("DELETE FROM inventory_materialpricechange WHERE id=%s", [record.pk]),
            ("INSERT INTO inventory_materialpricechange (material_id,old_price,new_price,old_currency,new_currency,user_id,changed_at,reason,source) VALUES (%s,NULL,1,NULL,'USD',%s,now(),'forged','admin')", [self.material.pk, self.user.pk]),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, args)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MaterialPriceChange.objects.all().update(reason="bulk tampering")
        self.assertEqual(MaterialPriceChange.objects.get().reason, "Synthetic correction")

    def test_unaudited_catalogue_updates_are_rejected_but_stock_updates_work(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Material.objects.filter(pk=self.material.pk).update(unit_price=7, currency="USD")
        Material.objects.filter(pk=self.material.pk).update(stock_quantity=11)
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        self.assertEqual(self.material.stock_quantity, 11)

    def test_audit_failure_and_outer_failure_roll_back_price_and_ledger(self):
        with connection.cursor() as cursor:
            cursor.execute("ALTER TABLE inventory_materialpricechange ADD CONSTRAINT synthetic_audit_failure CHECK(reason <> 'fail audit')")
        with self.assertRaises(IntegrityError):
            self.update(reason="fail audit")
        with self.assertRaisesMessage(ValueError, "rollback"), transaction.atomic():
            self.update()
            raise ValueError("rollback")
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_permissions_and_read_only_history(self):
        self.update()
        viewer = get_user_model().objects.create_user(username="price-viewer", is_staff=True)
        self.client.force_login(viewer)
        history = reverse("admin:inventory_materialpricechange_changelist")
        detail = reverse("admin:inventory_materialpricechange_change", args=[MaterialPriceChange.objects.get().pk])
        self.assertEqual(self.client.get(history).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename="view_materialpricechange"))
        self.assertContains(self.client.get(history), "Synthetic correction")
        self.assertEqual(self.client.get(detail).status_code, 200)
        self.assertEqual(self.client.post(detail, {"reason": "tampered"}).status_code, 403)
        with self.assertRaises(PermissionDenied):
            update_price(self.material.pk, viewer, price=1, currency="USD", reason="No", expected_state=price_state(self.material))
        viewer.user_permissions.add(Permission.objects.get(codename="change_material"))
        viewer = get_user_model().objects.get(pk=viewer.pk)
        self.material.refresh_from_db()
        update_price(self.material.pk, viewer, price=Decimal("3"), currency="USD", reason="Authorized", expected_state=price_state(self.material))
        viewer.is_active = False
        viewer.save()
        with self.assertRaises(PermissionDenied):
            update_price(self.material.pk, viewer, price=4, currency="USD", reason="Inactive", expected_state=price_state(self.material))

    def test_admin_csrf_and_stock_flag_do_not_grant_price_editing(self):
        from django.test import Client
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        url = reverse("admin:inventory_material_change", args=[self.material.pk])
        self.assertEqual(csrf_client.post(url, {"unit_price": "7"}).status_code, 403)
        stock_user = get_user_model().objects.create_user(username="stock-only", is_staff=True, can_manage_stock=True)
        self.client.force_login(stock_user)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"unit_price": "7"}).status_code, 403)
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_revoked_permission_is_checked_again_by_database(self):
        actor = get_user_model().objects.create_user(username="revoked-editor")
        actor.user_permissions.add(Permission.objects.get(codename="change_material"))
        self.assertTrue(actor.has_perm("inventory.change_material"))
        actor.user_permissions.clear()
        # The Python permission cache still says yes; the database must fail closed.
        with self.assertRaises(IntegrityError):
            update_price(self.material.pk, actor, price=Decimal("1"), currency="USD", reason="Revoked",
                         expected_state=price_state(self.material))
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        self.assertFalse(MaterialPriceChange.objects.exists())

    def test_rendered_labels_and_errors_follow_language_switch(self):
        for language, label, error in (("fr", "Motif du changement de prix", "Indiquez le motif du changement de prix ou de devise."),
                                       ("en", "Price change reason", "Enter a reason for the price or currency change.")):
            url, data = self.form_data(language)
            self.assertContains(self.client.get(url, HTTP_ACCEPT_LANGUAGE=language), label)
            data.update(unit_price="1", currency="USD")
            self.assertContains(self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language), error)
        self.update()
        self.assertContains(self.client.get(reverse("admin:inventory_materialpricechange_changelist"), HTTP_ACCEPT_LANGUAGE="fr"), "Historique des prix du matériel")


class ConcurrentPricingTests(PricingFixtures, TransactionTestCase):
    def test_two_editors_with_same_revision_have_exactly_one_winner(self):
        expected = price_state(self.material)
        barrier = Barrier(2)

        def edit(value):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=15)
                try:
                    update_price(self.material.pk, actor, price=Decimal(value), currency="USD", reason="Concurrent", expected_state=expected)
                    return "saved"
                except ValidationError:
                    return "stale"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ["2", "3"]))
        self.assertCountEqual(results, ["saved", "stale"])
        record = MaterialPriceChange.objects.get()
        self.material.refresh_from_db()
        self.assertEqual(self.material.unit_price, record.new_price)
        self.assertEqual(self.material.stock_quantity, 10)


# Reuse the real invoice lifecycle fixtures without modifying invoice services.
from invoicing.test_lifecycle import LifecycleFixtures


class InvoicePricePreservationTests(LifecycleFixtures, TestCase):
    def test_catalogue_price_update_preserves_final_invoice_and_document_snapshot(self):
        from invoicing.documents import _snapshot
        invoice = self.create()
        self.price(invoice, "2.00")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        before = _snapshot(invoice)
        lines = list(invoice.lines.values())
        movements = list(self.material.stock_movements.values())
        update_price(self.material.pk, self.admin, price=Decimal("99.00"), currency="EUR",
                     reason="New catalogue price", expected_state=price_state(self.material))
        invoice.refresh_from_db()
        self.assertEqual(_snapshot(invoice), before)
        self.assertEqual(list(invoice.lines.values()), lines)
        self.assertEqual(list(self.material.stock_movements.values()), movements)
        self.assertEqual(MaterialPriceChange.objects.get().new_price, Decimal("99.00"))
