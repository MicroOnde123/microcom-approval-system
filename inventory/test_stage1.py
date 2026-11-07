"""Phase 2 Stage 1: synthetic catalogue, admin and compatibility regressions."""
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import activate, deactivate, override

from core.document_config import validate_logo_reference, validate_number_format
from core.models import CompanyDocumentSettings
from requests_app.models import RequestApproval, StockMovement
from requests_app.services import resubmit_request, return_step
from requests_app.test_stock_safety import StockSafetyFixtures
from .models import Material, Succursale


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Stage1Tests(StockSafetyFixtures, TestCase):
    def setUp(self):
        # LocaleMiddleware activates the response language; contain it so a
        # French admin request cannot change the language of a later test.
        activate("en")
        self.addCleanup(deactivate)
        super().setUp()

    def administrator(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)

    def priced_material(self, **values):
        return Material(category=self.category, name="Synthetic priced material", code="PRICE", **values)

    def test_succursale_lifecycle_has_no_stock_or_department_side_effects(self):
        before = self.snapshot()
        branch = Succursale.objects.create(code="SYNTHETIC", name="Synthetic succursale")
        self.assertIsNotNone(branch.created_at)
        branch.name = "Renamed synthetic succursale"
        branch.is_active = False
        branch.save()
        branch.refresh_from_db()
        self.assertFalse(branch.is_active)
        self.assertEqual(branch.name, "Renamed synthetic succursale")
        self.assertEqual(self.snapshot(), before)
        self.assertNotIn("stock_quantity", {field.name for field in Succursale._meta.fields})

    def snapshot(self):
        from accounts.models import Department
        from requests_app.models import Request, RequestMaterialItem
        return {model.__name__: list(model.objects.order_by("pk").values()) for model in
                (Department, Request, RequestMaterialItem, StockMovement, Material)}

    def test_duplicate_succursale_code_rejected_by_validation_and_database(self):
        Succursale.objects.create(code="UNIQUE", name="Synthetic")
        with self.assertRaises(ValidationError):
            Succursale(code="UNIQUE", name="Another").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Succursale.objects.create(code="UNIQUE", name="Another")

    def test_admin_can_create_edit_and_deactivate_succursale(self):
        self.administrator()
        data = {"code": "ADMIN", "name": "Synthetic", "physical_address": "Synthetic address", "is_active": "on", "_save": "Save"}
        self.assertEqual(self.client.post(reverse("admin:inventory_succursale_add"), data).status_code, 302)
        branch = Succursale.objects.get(code="ADMIN")
        data.update(name="Changed synthetic")
        data.pop("is_active")
        self.assertEqual(self.client.post(reverse("admin:inventory_succursale_change", args=[branch.pk]), data).status_code, 302)
        branch.refresh_from_db()
        self.assertFalse(branch.is_active)
        self.assertEqual(branch.name, "Changed synthetic")

    def test_new_admin_permissions_are_not_granted_by_stock_flag(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        for name in ("inventory_succursale_add", "core_companydocumentsettings_add"):
            self.assertEqual(self.client.get(reverse("admin:" + name)).status_code, 403)
        permission = Permission.objects.get(content_type__app_label="inventory", codename="add_succursale")
        self.user.user_permissions.add(permission)
        self.assertEqual(self.client.get(reverse("admin:inventory_succursale_add")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:core_companydocumentsettings_add")).status_code, 403)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("admin:inventory_succursale_add")).status_code, 302)

    def test_unknown_and_explicit_zero_price_are_distinct(self):
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        self.assertIsNone(self.material.currency)
        material = self.priced_material(unit_price=Decimal("0.00"))
        material.full_clean()
        self.assertEqual(material.currency, "USD")
        material.save()
        material.refresh_from_db()
        self.assertEqual(material.unit_price, Decimal("0.00"))
        self.assertEqual(material.currency, "USD")

    def test_document_currency_default_applies_only_to_newly_supplied_prices(self):
        CompanyDocumentSettings.objects.create(default_currency="CDF")
        material = self.priced_material(unit_price=Decimal("12.50"))
        material.full_clean()
        self.assertEqual(material.currency, "CDF")
        material.currency = "EUR"
        material.full_clean()
        self.assertEqual(material.currency, "EUR")
        self.material.refresh_from_db()
        self.assertIsNone(self.material.currency)

    def test_negative_prices_rejected_by_validation_and_database(self):
        for language, text in (("en", "Unit price cannot be negative."),
                               ("fr", "Le prix unitaire ne peut pas être négatif.")):
            with override(language), self.assertRaisesMessage(ValidationError, text):
                self.priced_material(unit_price=Decimal("-0.01"), currency="USD").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Material.objects.filter(pk=self.material.pk).update(unit_price=-1, currency="USD")

    def test_currency_codes_and_priced_currency_database_protection(self):
        for code in ("USD", "CDF", "EUR"):
            self.priced_material(unit_price=1, currency=code).full_clean()
        for code in ("usd", "US", "ZZZ", "123"):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                self.priced_material(unit_price=1, currency=code).full_clean()
        for values in ({"currency": "ZZZ"}, {"unit_price": 1, "currency": None}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Material.objects.filter(pk=self.material.pk).update(**values)

    def test_unpriced_request_final_approval_and_return_unchanged(self):
        self.assertIsNone(self.req.amount)
        self.assertEqual(self.req.approvals.get().approver_user_id, self.user.pk)
        self.issue()
        self.assertEqual(self.balance(), 90)
        self.restore(3)
        self.assertEqual(self.balance(), 93)
        self.material.refresh_from_db()
        self.assertIsNone(self.material.unit_price)
        self.assertIsNone(self.material.currency)
        self.req.refresh_from_db()
        self.assertIsNone(self.req.amount)
        self.assertTrue(self.req.stock_deducted)

    def test_existing_resubmission_rebuilds_approval_rows_as_before(self):
        previous = self.req.approvals.get()
        return_step(previous, self.user, "Synthetic correction")
        self.req.refresh_from_db()
        resubmit_request(self.req, self.other)
        self.assertFalse(RequestApproval.objects.filter(pk=previous.pk).exists())
        current = self.req.approvals.get()
        self.req.refresh_from_db()
        self.assertEqual(current.approver_user_id, self.user.pk)
        self.assertEqual(self.req.current_step_order, current.step_order)
        self.assertFalse(StockMovement.objects.exists())
        self.issue()
        self.assertEqual(self.balance(), 90)

    def test_admin_pricing_and_validation_in_both_languages(self):
        self.administrator()
        for language, label, error in (("en", "Unit price", "Unit price cannot be negative."),
                                       ("fr", "Prix unitaire", "Le prix unitaire ne peut pas être négatif.")):
            url = reverse("admin:inventory_material_change", args=[self.material.pk])
            response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response, label)
            form = response.context["adminform"].form
            data = {name: form[name].value() if form[name].value() is not None else "" for name in form.fields}
            data.update(unit_price="-1", currency="USD", _save="Save")
            response = self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, error)
            data.update(unit_price="0", currency="", price_change_reason="Synthetic catalogue correction")
            self.assertEqual(self.client.post(url, data, HTTP_ACCEPT_LANGUAGE=language).status_code, 302)
            self.material.refresh_from_db()
            self.assertEqual(self.material.unit_price, 0)
            self.assertEqual(self.material.currency, "USD")
            self.assertEqual(self.material.stock_quantity, 100)

    def test_settings_empty_identity_singleton_and_supported_currency(self):
        settings = CompanyDocumentSettings()
        settings.full_clean()
        settings.save()
        self.assertEqual(settings.company_name, "")
        self.assertEqual(settings.company_address, "")
        self.assertEqual(settings.contact_details, "")
        self.assertEqual(settings.logo_reference, "images/microcom_logo.png")
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompanyDocumentSettings.objects.create(pk=2)
        settings.default_currency = "ZZZ"
        with override("fr"), self.assertRaisesMessage(ValidationError, "Sélectionnez une devise prise en charge"):
            settings.full_clean()

    def test_document_preferences_validate_without_issuing_documents(self):
        for value in ("FAC/{number:04d}/{year}", "INTERNAL-{number}"):
            validate_number_format(value)
        for value in ("FAC", "{number.__class__}", "{number:1000000d}", "{number}{number}", "{number!r}", "{unknown}"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_number_format(value)
        validate_logo_reference("images/microcom_logo.png")
        for value in ("../secret.png", "https://example.invalid/logo.png", "/absolute/logo.png"):
            with self.assertRaises(ValidationError):
                validate_logo_reference(value)

    def test_bilingual_new_admin_interfaces_and_singleton_add_control(self):
        self.administrator()
        for language, branch_label, settings_label in (("en", "Succursale name", "Verified company address"),
                                                       ("fr", "Nom de la succursale", "Adresse vérifiée de l’entreprise")):
            self.assertContains(self.client.get(reverse("admin:inventory_succursale_add"), HTTP_ACCEPT_LANGUAGE=language), branch_label)
            self.assertContains(self.client.get(reverse("admin:core_companydocumentsettings_add"), HTTP_ACCEPT_LANGUAGE=language), settings_label)
        data = {"company_name": "Synthetic company", "company_address": "Synthetic address",
                "contact_details": "Synthetic contacts", "logo_reference": "images/microcom_logo.png",
                "default_currency": "EUR", "invoice_number_format": "FAC/{number:04d}/{year}",
                "document_number_format": "", "business_timezone": "Africa/Kinshasa", "_save": "Save"}
        self.assertEqual(self.client.post(reverse("admin:core_companydocumentsettings_add"), data).status_code, 302)
        self.assertEqual(CompanyDocumentSettings.objects.count(), 1)
        self.assertEqual(self.client.get(reverse("admin:core_companydocumentsettings_add")).status_code, 403)
