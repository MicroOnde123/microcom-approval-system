from unittest.mock import patch
from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from .test_material_entries import Fixtures
from .entry_services import new_token, receive_stock
from .models import Material, MaterialReceipt, MaterialReceiptLine
from requests_app.models import StockMovement


class EntryReviewTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def payload(self, mode):
        return {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "token": new_token(self.user, mode)}

    def snapshot(self):
        return [list(model.objects.order_by("pk").values()) for model in (Material, MaterialReceipt, MaterialReceiptLine, StockMovement)]

    def test_verify_modify_verify_confirm_without_intermediate_writes(self):
        for mode in ("new", "existing"):
            with self.subTest(mode=mode):
                data = self.payload(mode)
                before = self.snapshot()
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.post("/materials/entries/", {**data, "action": "verify"})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["review"])
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
                proof = response.context["review_proof"]
                modified = self.client.post("/materials/entries/", {**data, "action": "modify", "review_proof": proof})
                self.assertFalse(modified.context["review"])
                self.assertEqual(modified.context["receipt_form"]["quantity"].value(), data["quantity"])
                for field in self.data:
                    self.assertEqual(modified.context["receipt_form"][field].value(), data[field])
                self.assertEqual(modified.context["receipt_form"]["token"].value(), data["token"])
                if mode == "new":
                    self.assertEqual(modified.context["material_form"]["name"].value(), "Bolt")
                self.assertEqual(self.snapshot(), before)
                verified = self.client.post("/materials/entries/", {**data, "action": "verify"})
                confirmed = {**data, "action": "confirm", "review_proof": verified.context["review_proof"]}
                with patch("inventory.entry_views.receive_stock", wraps=receive_stock) as service:
                    saved = self.client.post("/materials/entries/", confirmed)
                    self.assertEqual(saved.status_code, 302)
                    service.assert_called_once()
                after = self.snapshot()
                retry = self.client.post("/materials/entries/", confirmed)
                self.assertEqual(retry.url, saved.url)
                self.assertEqual(self.snapshot(), after)

    def test_missing_forged_or_changed_confirmation_is_rejected(self):
        for mode in ("new", "existing"):
            data = self.payload(mode)
            review = self.client.post("/materials/entries/", {**data, "action": "verify"})
            proof = review.context["review_proof"]
            before = self.snapshot()
            variants = [{"review_proof": ""}, {"review_proof": "forged"}, {"quantity": "3"},
                        {"supplier": "Changed"}, {"token": new_token(self.user, mode)}]
            if mode == "new": variants.append({"name": "Changed"})
            for change in variants:
                with self.subTest(mode=mode, change=change), patch("inventory.entry_views.receive_stock") as service:
                    response = self.client.post("/materials/entries/", {**data, "action": "confirm", "review_proof": proof, **change})
                    self.assertContains(response, "The reviewed details have changed")
                    service.assert_not_called()
                    self.assertEqual(self.snapshot(), before)

    def test_invalid_review_and_confirm_preserve_fields_and_stock(self):
        for action in ("verify", "confirm"):
            data = {**self.payload("existing"), "quantity": "-1", "action": action}
            before = self.snapshot()
            response = self.client.post("/materials/entries/", data)
            self.assertFalse(response.context["review"])
            self.assertIn("quantity", response.context["receipt_form"].errors)
            self.assertEqual(response.context["receipt_form"]["supplier"].value(), self.data["supplier"])
            self.assertEqual(self.snapshot(), before)

    def test_stock_estimate_placement_and_inactive_selection_preserved(self):
        self.material.is_active = False
        self.material.save()
        data = self.payload("existing")
        response = self.client.post("/materials/entries/", {**data, "action": "verify"})
        self.assertTrue(response.context["review"])
        self.assertEqual(response.context["current_stock"], 10)
        self.assertEqual(response.context["estimated_stock"], 12.5)
        form = self.client.get("/materials/entries/?mode=existing")
        text = form.content.decode()
        self.assertLess(text.index('id="id_material"'), text.index('id="id_quantity"'))
        self.assertContains(form, "Estimated stock after receipt")
        self.assertContains(form, 'data-search-select')
        self.assertNotContains(form, 'href="?mode=history"')

    def test_confirmation_recalculates_changed_stock_and_revalidates(self):
        data = self.payload("existing")
        reviewed = self.client.post("/materials/entries/", {**data, "action": "verify"})
        self.material.stock_quantity = 20
        self.material.save()
        response = self.client.post("/materials/entries/", {**data, "action": "confirm", "review_proof": reviewed.context["review_proof"]})
        self.assertEqual(response.status_code, 302)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_quantity, 22.5)
        self.assertEqual(MaterialReceiptLine.objects.get().stock_after, 22.5)

    def test_bilingual_controls_and_application_validation(self):
        for language, verify, confirm, modify in [("en", "Verify details", "Confirm and Save", "Modify"),
                ("fr", "V\u00e9rifier les informations", "Confirmer et enregistrer", "Modifier")]:
            self.client.cookies["django_language"] = language
            response = self.client.get("/materials/entries/")
            self.assertContains(response, verify)
            self.assertContains(response, 'novalidate')
            self.assertContains(response, 'data-search-select')
            review = self.client.post("/materials/entries/", {**self.payload("new"), "action": "verify"})
            self.assertContains(review, confirm)
            self.assertContains(review, modify)

    def test_rendered_hidden_fields_round_trip_without_javascript(self):
        from html.parser import HTMLParser
        class HiddenForms(HTMLParser):
            def __init__(self):
                super().__init__()
                self.forms = []
                self.form = None
            def handle_starttag(self, tag, attributes):
                attrs = dict(attributes)
                if tag == "form":
                    self.form = {}
                    self.forms.append(self.form)
                elif tag == "input" and self.form is not None and attrs.get("type") == "hidden":
                    self.form[attrs["name"]] = attrs.get("value", "")
            def handle_endtag(self, tag):
                if tag == "form": self.form = None
        for mode in ("new", "existing"):
            payload = {**self.payload(mode), "action": "verify"}
            if mode == "new": payload["is_active"] = ""
            response = self.client.post("/materials/entries/", payload)
            parser = HiddenForms()
            parser.feed(response.content.decode())
            hidden = next(form for form in parser.forms if "review_proof" in form)
            saved = self.client.post("/materials/entries/", {**hidden, "action": "confirm"})
            self.assertEqual(saved.status_code, 302, saved.content.decode()[-500:])
        self.assertFalse(Material.objects.get(code="BOLT").is_active)
