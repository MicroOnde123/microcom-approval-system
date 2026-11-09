"""Admin currency defaults using synthetic records and isolated test settings."""
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils.translation import override

from core.models import CompanyDocumentSettings
from inventory.admin import MaterialAdmin, MaterialAdminForm
from inventory.models import Material, MaterialCategory, MaterialPriceChange
from inventory.pricing import price_state, update_price
from requests_app.models import StockMovement


class MaterialCurrencyDefaultTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="currency-admin", password="synthetic")
        self.category = MaterialCategory.objects.create(name="Synthetic", code="CURR")
        self.material = Material.objects.create(
            category=self.category, code="CURR", name="Synthetic material",
            unit="pcs", stock_quantity=Decimal("25.50"), minimum_stock_level=2)

    def data(self, material=None, **overrides):
        form = MaterialAdminForm(instance=material)
        data = {name: form[name].value() if form[name].value() is not None else ""
                for name in form.fields}
        data["price_change_reason"] = "Verify material currency default through Admin"
        data.update(overrides)
        return data

    def save_edit(self, material_id, **overrides):
        # Each edit starts with fresh DB state and all three signed revisions.
        # Use the real Admin save path so its authorization/audit checks run.
        with transaction.atomic():
            material = Material.objects.get(pk=material_id)
            form = MaterialAdminForm(
                data=self.data(material, **overrides), instance=material)
            self.assertTrue(form.is_valid(), form.errors)
            request = RequestFactory().post("/")
            request.user = self.user
            MaterialAdmin(Material, admin.site).save_model(
                request, form.save(commit=False), form, change=True)
        return Material.objects.get(pk=material_id)

    def set_price(self, price, currency):
        material = Material.objects.get(pk=self.material.pk)
        return update_price(
            material.pk, self.user, price=Decimal(price), currency=currency,
            reason="Prepare saved currency regression fixture",
            expected_state=price_state(material))

    def test_new_form_defaults_to_usd_in_both_languages(self):
        CompanyDocumentSettings.objects.create(default_currency="USD")
        for language in ("en", "fr"):
            with self.subTest(language=language), override(language):
                form = MaterialAdminForm()
                self.assertEqual(form["currency"].value(), "USD")
                self.assertIn('value="USD" selected', str(form["currency"]))
                self.assertIsNone(form.instance.currency)

    def test_existing_blank_currency_displays_usd_without_writing(self):
        CompanyDocumentSettings.objects.create(default_currency="USD")
        for language in ("en", "fr"):
            with self.subTest(language=language), override(language):
                material = Material.objects.get(pk=self.material.pk)
                form = MaterialAdminForm(instance=material)
                self.assertEqual(form["currency"].value(), "USD")
                self.assertIsNone(form.instance.currency)
        self.material.refresh_from_db()
        self.assertIsNone(self.material.currency)
        self.assertIsNone(self.material.unit_price)
        self.assertEqual(self.material.stock_quantity, Decimal("25.50"))

    def test_existing_usd_cdf_eur_retained_despite_different_company_currency(self):
        CompanyDocumentSettings.objects.create(default_currency="CDF")
        for currency in ("USD", "CDF", "EUR"):
            material = self.set_price("12.50", currency)
            for language in ("en", "fr"):
                with self.subTest(currency=currency, language=language), override(language):
                    form = MaterialAdminForm(instance=Material.objects.get(pk=material.pk))
                    self.assertEqual(form["currency"].value(), currency)
            self.material.refresh_from_db()
            self.assertEqual(self.material.currency, currency)
            self.assertEqual(self.material.unit_price, Decimal("12.50"))

    def test_company_currency_used_for_new_and_unassigned_materials(self):
        configuration = CompanyDocumentSettings.objects.create(default_currency="CDF")
        for currency in ("CDF", "EUR", "USD"):
            configuration.default_currency = currency
            configuration.save()
            self.assertEqual(MaterialAdminForm()["currency"].value(), currency)
            self.assertEqual(MaterialAdminForm(instance=self.material)["currency"].value(), currency)

    def test_usd_fallback_without_company_settings(self):
        self.assertFalse(CompanyDocumentSettings.objects.exists())
        self.assertEqual(MaterialAdminForm()["currency"].value(), "USD")
        self.assertEqual(MaterialAdminForm(instance=self.material)["currency"].value(), "USD")

    def test_usd_fallback_when_company_currency_is_empty(self):
        CompanyDocumentSettings.objects.create(default_currency="")
        self.assertEqual(MaterialAdminForm()["currency"].value(), "USD")
        self.assertEqual(MaterialAdminForm(instance=self.material)["currency"].value(), "USD")

    def test_opening_forms_leaves_all_saved_material_and_movement_fields_unchanged(self):
        CompanyDocumentSettings.objects.create(default_currency="USD")
        for currency in ("USD", "CDF", "EUR"):
            Material.objects.create(
                category=self.category, code="SAVED-" + currency, name="Synthetic priced material",
                currency=currency, unit_price=Decimal("8.25"), stock_quantity=Decimal("17.50"))
        StockMovement.objects.create(
            material=self.material, quantity=Decimal("25.50"), movement_type="IN",
            note="Synthetic existing movement")
        before_materials = list(Material.objects.order_by("pk").values())
        before_movements = list(StockMovement.objects.order_by("pk").values())
        for language in ("en", "fr"):
            with override(language):
                for material in Material.objects.all():
                    str(MaterialAdminForm(instance=material)["currency"])
                str(MaterialAdminForm()["currency"])
        self.assertEqual(list(Material.objects.order_by("pk").values()), before_materials)
        self.assertEqual(list(StockMovement.objects.order_by("pk").values()), before_movements)

    def test_explicit_selected_currency_is_saved_not_defaulted(self):
        CompanyDocumentSettings.objects.create(default_currency="USD")
        for currency in ("CDF", "EUR", "USD"):
            for language in ("en", "fr"):
                with self.subTest(currency=currency, language=language), override(language):
                    # A separate record prevents state leaking between subtests.
                    material = Material.objects.create(
                        category=self.category, code=f"EDIT-{currency}-{language}",
                        name="Synthetic edit", stock_quantity=Decimal("25.50"))
                    saved = self.save_edit(material.pk, unit_price="3.25", currency=currency)
                    record = MaterialPriceChange.objects.get(material=saved)
                    self.assertEqual((record.user_id, record.source), (self.user.pk, "admin"))
                    self.assertEqual((record.old_price, record.old_currency), (None, None))
                    self.assertEqual((record.new_price, record.new_currency), (Decimal("3.25"), currency))
                    self.assertEqual(record.reason, "Verify material currency default through Admin")
                    self.assertEqual(saved.currency, currency)
                    self.assertEqual(saved.unit_price, Decimal("3.25"))
                    self.assertEqual(saved.stock_quantity, Decimal("25.50"))
                    self.assertFalse(StockMovement.objects.exists())

    def test_blank_submitted_currency_with_price_uses_company_currency(self):
        CompanyDocumentSettings.objects.create(default_currency="CDF")
        saved = self.save_edit(self.material.pk, unit_price="4.50", currency="")
        self.assertEqual(saved.currency, "CDF")
        self.assertEqual(saved.unit_price, Decimal("4.50"))

    def test_blank_submitted_currency_with_price_falls_back_to_usd(self):
        saved = self.save_edit(self.material.pk, unit_price="0", currency="")
        self.assertEqual(saved.currency, "USD")
        self.assertEqual(saved.unit_price, Decimal("0"))

    def test_explicit_blank_submission_with_price_uses_company_not_saved_currency(self):
        CompanyDocumentSettings.objects.create(default_currency="USD")
        self.set_price("7.50", "EUR")
        saved = self.save_edit(self.material.pk, currency="")
        self.assertEqual((saved.currency, saved.unit_price), ("USD", Decimal("7.50")))
        record = saved.price_changes.order_by("-pk").first()
        self.assertEqual((record.old_currency, record.new_currency), ("EUR", "USD"))
        self.assertEqual(record.user_id, self.user.pk)

    def test_invalid_currency_and_negative_price_remain_invalid_in_both_languages(self):
        for language in ("en", "fr"):
            for overrides, field in (({"unit_price": "1", "currency": "ZZZ"}, "currency"),
                                     ({"unit_price": "-1", "currency": "EUR"}, "unit_price")):
                with self.subTest(language=language, field=field), override(language):
                    material = Material.objects.get(pk=self.material.pk)
                    form = MaterialAdminForm(
                        data=self.data(material, **overrides), instance=material)
                    self.assertFalse(form.is_valid())
                    self.assertIn(field, form.errors)
                    self.material.refresh_from_db()
                    self.assertIsNone(self.material.currency)
                    self.assertIsNone(self.material.unit_price)

    def test_admin_get_and_add_post_in_both_languages(self):
        self.client.force_login(self.user)
        CompanyDocumentSettings.objects.create(default_currency="USD")
        for language in ("en", "fr"):
            with self.subTest(language=language):
                url = reverse("admin:inventory_material_add")
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["adminform"].form["currency"].value(), "USD")
                data = self.data(category=self.category.pk, code="NEW-" + language,
                                 name="Synthetic new material", unit="pcs", stock_quantity="5",
                                 minimum_stock_level="0", unit_price="2.50", currency="USD",
                                 is_active="on", _save="Save")
                self.assertEqual(self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language).status_code, 302)
                saved = Material.objects.get(code="NEW-" + language)
                self.assertEqual((saved.currency, saved.unit_price), ("USD", Decimal("2.50")))
                response = self.client.get(reverse("admin:inventory_material_change", args=[self.material.pk]),
                                           HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.context["adminform"].form["currency"].value(), "USD")
        self.material.refresh_from_db()
        self.assertIsNone(self.material.currency)
        self.assertEqual(self.material.stock_quantity, Decimal("25.50"))
        self.assertFalse(StockMovement.objects.exists())
