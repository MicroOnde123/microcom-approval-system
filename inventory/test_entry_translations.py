"""Rendered EN/FR regressions, including language changes within one process."""
import ast
import gettext
import re
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.translation.template import templatize
from .entry_services import new_token
from .models import Material, MaterialCategory, MaterialReceipt, MaterialReceiptLine
from .test_material_entries import Fixtures
from requests_app.models import StockMovement


class EntryTranslationTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def language(self, language, client=None):
        client = client or self.client
        response = client.post(reverse("set_language"), {"language": language, "next": "/materials/entries/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.cookies["django_language"].value, language)

    def payload(self, mode="existing"):
        return {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "token": new_token(self.user, mode), "action": "verify"}

    def test_required_errors_in_summary_and_fields_after_repeated_language_switches(self):
        for language in ("en", "fr", "en", "fr"):
            self.language(language)
            response = self.client.post("/materials/entries/", {"mode": "new"}, HTTP_ACCEPT_LANGUAGE="en")
            expected = "Ce champ est obligatoire." if language == "fr" else "This field is required."
            self.assertContains(response, expected)
            self.assertGreaterEqual(response.content.decode().count(expected), 10)
            if language == "fr": self.assertNotContains(response, "This field is required.")
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 10)

    def test_invalid_quantity_date_choice_and_length_messages_are_rendered(self):
        cases = [
            ("existing", {"quantity": "abc"}, "Enter a number.", "Saisissez un nombre."),
            ("existing", {"quantity": "NaN"}, "Enter a number.", "Saisissez un nombre."),
            ("existing", {"quantity": "-1"}, "Ensure this value is greater than or equal", "sup\u00e9rieure ou \u00e9gale"),
            ("existing", {"quantity": "0"}, "Ensure this value is greater than or equal", "sup\u00e9rieure ou \u00e9gale"),
            ("existing", {"quantity": "0.001"}, "decimal places", "chiffres apr\u00e8s la virgule"),
            ("existing", {"quantity": "123456789.12"}, "digits in total", "chiffres au total"),
            ("existing", {"received_on": "2026-02-30"}, "Enter a valid date.", "Saisissez une date valide."),
            ("existing", {"material": 999999}, "Select a valid choice.", "S\u00e9lectionnez un choix valide."),
            ("new", {"currency": "JPY"}, "Select a valid choice.", "S\u00e9lectionnez un choix valide."),
            ("new", {"category": 999999}, "Select a valid choice.", "S\u00e9lectionnez un choix valide."),
            ("new", {"minimum_stock_level": "-1"}, "Ensure this value is greater than or equal", "sup\u00e9rieure ou \u00e9gale"),
            ("new", {"unit_price": "-1"}, "Unit price cannot be negative.", "n\u00e9gatif"),
            ("new", {"name": "n" * 151}, "at most 150 characters", "au plus 150 caract\u00e8res"),
        ]
        for language in ("en", "fr"):
            self.language(language)
            for mode, changes, english, french in cases:
                with self.subTest(language=language, changes=changes):
                    response = self.client.post("/materials/entries/", {**self.payload(mode), **changes})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, french if language == "fr" else english)
                    self.assertFalse(response.context["review"])
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertEqual(Material.objects.count(), 1)

    def test_duplicate_material_code_has_a_complete_localized_sentence(self):
        for language, expected in [("en", "A material with this code already exists."), ("fr", "Un mat\u00e9riel avec ce code existe d\u00e9j\u00e0.")]:
            self.language(language)
            response = self.client.post("/materials/entries/", {**self.payload("new"), "code": self.material.code})
            self.assertContains(response, expected)
            self.assertFalse(MaterialReceipt.objects.exists())

    def test_category_errors_and_javascript_message_sources(self):
        url = reverse("create_material_category")
        for language in ("en", "fr"):
            self.language(language)
            response = self.client.post(url, {})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["errors"]["name"], ["Ce champ est obligatoire." if language == "fr" else "This field is required."])
            response = self.client.post(url, {"category-name": "Other", "category-code": self.category.code})
            self.assertEqual(response.status_code, 409)
            self.assertIn("existe d\u00e9j\u00e0" if language == "fr" else "already exists", response.json()["errors"]["code"][0])
            response = self.client.post(url, {"category-name": "Other", "category-code": "c" * 31})
            self.assertIn("caract\u00e8res" if language == "fr" else "characters", response.json()["errors"]["code"][0])
            page = self.client.get("/materials/entries/")
            for english, french in [("No matching results.", "Aucun r\u00e9sultat correspondant."), ("Use standard selector", "Utiliser la liste standard"), ("Saving category...", "Enregistrement de la cat\u00e9gorie..."), ("Category created and selected.", "Cat\u00e9gorie cr\u00e9\u00e9e et s\u00e9lectionn\u00e9e.")]:
                self.assertContains(page, french if language == "fr" else english)
        self.assertEqual(MaterialCategory.objects.count(), 1)

    def test_invalid_operation_and_review_proof_messages(self):
        for language in ("en", "fr"):
            self.language(language)
            response = self.client.post("/materials/entries/", {**self.payload(), "token": "invalid"})
            self.assertContains(response, "Formulaire de r\u00e9ception invalide" if language == "fr" else "Invalid receipt form.")
            response = self.client.post("/materials/entries/", {**self.payload(), "action": "confirm", "review_proof": "invalid"})
            self.assertContains(response, "Les informations v\u00e9rifi\u00e9es ont chang\u00e9" if language == "fr" else "The reviewed details have changed")
        self.assertFalse(MaterialReceipt.objects.exists())

    def test_history_filter_errors_and_review_dates(self):
        for language in ("en", "fr"):
            self.language(language)
            response = self.client.get(reverse("material_receipt_history"), {"date_from": "invalid"})
            self.assertContains(response, "Saisissez une date valide." if language == "fr" else "Enter a valid date.")
            response = self.client.get(reverse("material_receipt_history"), {"date_from": "2026-11-04", "date_to": "2026-11-01"})
            self.assertContains(response, "La date de fin doit" if language == "fr" else "The end date must")
            response = self.client.post("/materials/entries/", self.payload())
            self.assertContains(response, "03/11/2026" if language == "fr" else "2026-11-03")
            self.assertContains(response, 'name="received_on" value="2026-11-03"')
            self.assertContains(response, "Confirmer et enregistrer" if language == "fr" else "Confirm and Save")

    def test_success_details_and_modify_remain_translated_after_language_switch(self):
        payload = self.payload()
        self.language("en")
        review = self.client.post("/materials/entries/", payload)
        proof = review.context["review_proof"]
        self.language("fr")
        modified = self.client.post("/materials/entries/", {**payload, "action": "modify", "review_proof": proof})
        self.assertContains(modified, "V\u00e9rifier les informations")
        self.assertEqual(modified.context["receipt_form"]["received_on"].value(), "2026-11-03")
        confirmed = self.client.post("/materials/entries/", {**payload, "action": "confirm", "review_proof": proof})
        self.assertEqual(confirmed.status_code, 302)
        self.assertContains(self.client.get(confirmed.url), "R\u00e9ception enregistr\u00e9e")
        receipt = MaterialReceipt.objects.get()
        self.assertContains(self.client.get(reverse("material_receipt_detail", args=[receipt.pk])), "Historique des r\u00e9ceptions")
        self.language("en")
        self.assertContains(self.client.get(confirmed.url), "Receipt completed")

    def test_permission_and_csrf_responses_are_localized_without_changing_status(self):
        other = get_user_model().objects.create_user(username="no-stock")
        client = Client()
        client.force_login(other)
        for language in ("en", "fr"):
            self.language(language, client)
            for url in ("/materials/entries/", reverse("material_receipt_history"), reverse("material_receipt_detail", args=[9999])):
                response = client.get(url)
                self.assertContains(response, "Vous n\u2019avez pas l\u2019autorisation" if language == "fr" else "You do not have permission", status_code=403)
            response = client.post(reverse("create_material_category"), {})
            self.assertEqual(response.status_code, 403)
            self.assertIn("autorisation" if language == "fr" else "permission", response.json()["errors"]["__all__"][0])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for language in ("en", "fr"):
            client.cookies["django_language"] = language
            response = client.post("/materials/entries/", self.payload())
            self.assertContains(response, "Votre formulaire n\u2019a pas pu" if language == "fr" else "Your form could not be verified", status_code=403)


class EntryCatalogAuditTests(SimpleTestCase):
    def test_all_inventory_template_messages_have_french_catalog_entries(self):
        root = Path(__file__).resolve().parent.parent
        with (root / "locale/fr/LC_MESSAGES/django.mo").open("rb") as stream:
            catalog = gettext.GNUTranslations(stream)._catalog
        literal = r"(u?'(?:\\.|[^'\\])*')"
        paths = list((root / "templates/inventory").rglob("*.html"))
        paths += list((root / "inventory/templates/inventory").rglob("*.html"))
        for path in paths:
            code = templatize(path.read_text(encoding="utf-8"))
            for match in re.finditer(r"gettext\(" + literal + r"\)", code):
                message = ast.literal_eval(match.group(1))
                self.assertIn(message, catalog, f"Missing French message in {path.name}: {message}")
        for name in ("entry_forms.py", "entry_views.py", "entry_review.py", "entry_services.py", "receipt_history.py", "entry_i18n.py"):
            tree = ast.parse((root / "inventory" / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in {"_", "gettext", "gettext_lazy"}
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    self.assertIn(node.args[0].value, catalog,
                                  f"Missing French message in {name}: {node.args[0].value}")

    def test_other_modules_keep_standard_error_handlers(self):
        from .entry_i18n import csrf_failure, permission_denied
        request = RequestFactory().get("/requests/")
        with patch("inventory.entry_i18n.default_permission_denied") as denied:
            permission_denied(request, PermissionError())
            denied.assert_called_once()
        with patch("inventory.entry_i18n.default_csrf_failure") as csrf:
            csrf_failure(request, reason="synthetic")
            csrf.assert_called_once_with(request, reason="synthetic")
