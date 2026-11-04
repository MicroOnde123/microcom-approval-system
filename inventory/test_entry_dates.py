"""Date presentation, ISO boundaries and receipt workflow regressions."""
from datetime import date
from decimal import Decimal
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override
from .entry_forms import ReceiptForm
from .entry_services import new_token
from .models import MaterialReceipt
from .receipt_history import ReceiptHistoryFilter
from .test_material_entries import Fixtures
from requests_app.models import StockMovement


class DateFieldTests(SimpleTestCase):
    def test_iso_and_french_input_normalize_without_locale_ambiguity(self):
        for language in ("en", "fr", "en", "fr"):
            with override(language):
                for value in ("2024-02-29", "29/02/2024"):
                    form = ReceiptForm({"token": "test", "quantity": "1", "received_on": value})
                    self.assertTrue(form.is_valid(), form.errors)
                    self.assertEqual(form.cleaned_data["received_on"], date(2024, 2, 29))
                    self.assertEqual(form["received_on"].value(), "2024-02-29")
                    self.assertIn('value="2024-02-29"', form["received_on"].as_hidden())
                    self.assertIn('value="29/02/2024"' if language == "fr" else 'value="2024-02-29"', str(form["received_on"]))

    def test_impossible_invalid_and_required_dates_have_localized_errors(self):
        for language in ("en", "fr"):
            with override(language):
                for value in ("31/02/2026", "29/02/2025", "2026-02-30", "01/13/2026", "nonsense", ""):
                    form = ReceiptForm({"token": "test", "quantity": "1", "received_on": value})
                    self.assertFalse(form.is_valid())
                    expected = ("Ce champ est obligatoire." if language == "fr" else "This field is required.") if not value else (
                        "Saisissez une date valide." if language == "fr" else "Enter a valid date.")
                    self.assertEqual(form.errors["received_on"], [expected])
                    if value: self.assertIn(f'value="{value}"', str(form["received_on"]))

    def test_optional_filters_and_reversed_french_ranges(self):
        self.assertTrue(ReceiptHistoryFilter({}).is_valid())
        with override("fr"):
            form = ReceiptHistoryFilter({"date_from": "04/11/2026", "date_to": "01/11/2026"})
            self.assertFalse(form.is_valid())
            self.assertIn("La date de fin doit", form.errors["date_to"][0])


class DatePageTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def language(self, language):
        self.client.post(reverse("set_language"), {"language": language, "next": "/materials/entries/"})

    def payload(self, mode):
        return {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "token": new_token(self.user, mode), "received_on": "03/11/2026", "action": "verify"}

    def test_rendered_fields_and_calendar_labels_switch_without_restart(self):
        for language in ("en", "fr", "en", "fr"):
            self.language(language)
            for mode in ("new", "existing"):
                response = self.client.get("/materials/entries/", {"mode": mode})
                self.assertContains(response, "DD/MM/YYYY" if language == "fr" else "YYYY-MM-DD")
                self.assertContains(response, "Choisir une date" if language == "fr" else "Choose date")
                self.assertContains(response, 'aria-haspopup="dialog"')
                self.assertNotContains(response, 'type="date"')

    def test_review_modify_confirm_and_retry_keep_iso_and_same_receipt(self):
        for mode in ("new", "existing"):
            self.language("fr")
            data = self.payload(mode)
            before = (MaterialReceipt.objects.count(), StockMovement.objects.count())
            review = self.client.post("/materials/entries/", data)
            self.assertTrue(review.context["review"])
            self.assertContains(review, "03/11/2026")
            self.assertContains(review, 'name="received_on" value="2026-11-03"')
            self.assertEqual(before, (MaterialReceipt.objects.count(), StockMovement.objects.count()))
            proof = review.context["review_proof"]
            modify = self.client.post("/materials/entries/", {**data, "action": "modify", "review_proof": proof})
            self.assertContains(modify, 'value="03/11/2026"')
            self.assertEqual(modify.context["receipt_form"]["supplier"].value(), data["supplier"])
            self.language("en")
            changed = self.client.post("/materials/entries/", {**data, "received_on": "2026-11-04", "action": "confirm", "review_proof": proof})
            self.assertFalse(changed.context["review"])
            self.assertEqual(before, (MaterialReceipt.objects.count(), StockMovement.objects.count()))
            confirmation = {**data, "received_on": "2026-11-03", "action": "confirm", "review_proof": proof}
            saved = self.client.post("/materials/entries/", confirmation)
            retry = self.client.post("/materials/entries/", {**confirmation, "received_on": "03/11/2026"})
            self.assertEqual(saved.status_code, 302)
            self.assertEqual(saved.url, retry.url)
            self.assertEqual(MaterialReceipt.objects.count(), before[0] + 1)
            self.assertEqual(StockMovement.objects.count(), before[1] + 1)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, Decimal("12.50"))

    def test_rendered_invalid_dates_never_process_stock(self):
        for language in ("en", "fr"):
            self.language(language)
            for mode in ("new", "existing"):
                for value in ("", "31/02/2026", "2026-02-30", "wrong"):
                    response = self.client.post("/materials/entries/", {**self.payload(mode), "received_on": value})
                    self.assertEqual(response.status_code, 200)
                    expected = ("obligatoire" if language == "fr" else "This field is required.") if not value else (
                        "Saisissez une date valide." if language == "fr" else "Enter a valid date.")
                    self.assertContains(response, expected)
                    self.assertFalse(response.context["review"])
        self.assertFalse(MaterialReceipt.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_history_filters_links_and_historical_date_displays(self):
        first, _ = self.receive(receipt_data={**self.data, "received_on": "2026-11-01"})
        second, _ = self.receive()
        for language in ("en", "fr"):
            self.language(language)
            response = self.client.get(reverse("material_receipt_history"), {"date_from": "03/11/2026", "date_to": "03/11/2026", "q": "CAB", "page": "1"})
            self.assertEqual([row["receipt"].pk for row in response.context["receipt_rows"]], [second.pk])
            self.assertIn("date_from=2026-11-03", response.context["history_query"])
            self.assertIn("page=1", response.context["history_query"])
            for receipt in (first, second):
                detail = self.client.get(reverse("material_receipt_detail", args=[receipt.pk]), {"date_from": "2026-11-01", "page": "1"})
                expected = receipt.received_on.strftime("%d/%m/%Y" if language == "fr" else "%Y-%m-%d")
                self.assertContains(detail, expected)
                recorded = timezone.localtime(receipt.created_at).strftime("%d/%m/%Y" if language == "fr" else "%Y-%m-%d")
                self.assertContains(detail, recorded)
                self.assertIn("date_from=2026-11-01", detail.context["history_url"])
            invalid = self.client.get(reverse("material_receipt_history"), {"date_from": "31/02/2026"})
            self.assertContains(invalid, "Saisissez une date valide." if language == "fr" else "Enter a valid date.")
            reversed_dates = self.client.get(reverse("material_receipt_history"), {"date_from": "04/11/2026", "date_to": "01/11/2026"})
            self.assertContains(reversed_dates, "La date de fin doit" if language == "fr" else "The end date must")
