"""Presentation regressions; all business processing stays in the existing services."""
import os
from pathlib import Path
from django.test import TestCase
from .test_material_entries import Fixtures
from .entry_services import new_token


class EntryPresentationTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def payload(self, mode):
        return {**self.data, **(self.new if mode == "new" else {"material": self.material.pk}),
                "mode": mode, "action": "verify", "token": new_token(self.user, mode)}

    def evidence(self, name, response):
        # Optional local-only browser fixtures, never required by CI.
        if not os.environ.get("MATERIAL_ENTRY_UI_EVIDENCE"):
            return
        root = Path(__file__).resolve().parent.parent
        target = root / "local_artifacts" / "entry_ui"
        target.mkdir(parents=True, exist_ok=True)
        text = response.content.decode().replace('"/static/', '"' + (root / "static").as_uri() + '/')
        (target / (name + ".html")).write_text(text, encoding="utf-8")

    def test_forms_group_stock_and_delivery_and_render_progress(self):
        for language in ("en", "fr"):
            self.client.cookies["django_language"] = language
            for mode in ("new", "existing"):
                response = self.client.get("/materials/entries/?mode=" + mode)
                self.assertContains(response, 'class="entry-progress"')
                self.assertContains(response, 'aria-current="step"')
                self.assertContains(response, 'class="entry-action-bar entry-action-bar--edit"')
                self.assertContains(response, 'class="entry-search-icon"')
                self.assertRegex(response.content.decode(), r'name="action"\s+value="verify"')
                self.assertContains(response, 'novalidate')
                self.assertContains(response, ("Entr\u00e9e de stock initiale" if language == "fr" else "Initial Stock Entry") if mode == "new" else ("Informations de livraison" if language == "fr" else "Delivery information"))
                self.assertContains(response, "Param\u00e8tres du catalogue et du stock" if language == "fr" and mode == "new" else "Material and stock" if language == "en" and mode == "existing" else "Material Entries" if language == "en" else "Entr\u00e9es de stock")
                self.assertEqual(response.content.decode().count('name="quantity"'), 1)
                self.evidence(language + "-" + mode, response)

    def test_review_formats_date_without_altering_iso_hidden_fields(self):
        for language in ("en", "fr"):
            self.client.cookies["django_language"] = language
            for mode in ("new", "existing"):
                response = self.client.post("/materials/entries/", self.payload(mode))
                self.assertTrue(response.context["review"])
                self.assertContains(response, 'id="review-title" tabindex="-1" autofocus')
                self.assertContains(response, "V\u00e9rification de la r\u00e9ception" if language == "fr" else "Receipt verification")
                self.assertContains(response, "03/11/2026" if language == "fr" else "2026-11-03")
                self.assertContains(response, 'name="received_on" value="2026-11-03"')
                self.assertContains(response, 'name="action" value="modify"')
                self.assertContains(response, 'name="action" value="confirm"')
                if mode == "existing": self.assertContains(response, 'entry-stock-flow--review')
                else: self.assertContains(response, 'entry-quantity-highlight')
                self.evidence(language + "-" + mode + "-review", response)


class ReceiptConfirmationPresentationTests(Fixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def page(self, receipt):
        return self.client.get("/materials/entries/", {"receipt": receipt.pk, "mode": "existing"})

    def test_recorded_snapshot_reference_navigation_and_bilingual_layout(self):
        from django.urls import reverse
        receipt, _ = self.receive()
        self.material.name = "Renamed catalogue"
        self.material.code = "RENAMED"
        self.material.unit = "boxes"
        self.material.stock_quantity = 99
        self.material.save()
        for language in ("en", "fr"):
            self.client.cookies["django_language"] = language
            response = self.page(receipt)
            html = response.content.decode()
            panel = html.split('<section class="entry-success entry-confirmation"', 1)[1].split('</section>', 1)[0]
            self.assertIn("Cable", panel)
            self.assertIn("CAB", panel)
            self.assertNotIn("Renamed catalogue", panel)
            self.assertNotIn("boxes", panel)
            self.assertIn(receipt.reference, panel)
            self.assertIn("Supplier", panel)
            self.assertIn("DEL-1", panel)
            self.assertIn(self.user.username, panel)
            self.assertContains(response, reverse("material_receipt_detail", args=[receipt.pk]))
            self.assertContains(response, reverse("material_receipt_history"))
            self.assertLess(html.index('id="receipt-completed-title"'), html.index('id="saved-drafts-title"'))
            self.assertLess(html.index('id="receipt-completed-title"'), html.index('id="material-entry-form"'))
            self.assertIn("Réception enregistrée" if language == "fr" else "Receipt completed", panel)
            self.assertIn("03/11/2026" if language == "fr" else "2026-11-03", panel)
            item = response.context["confirmation"]["line_rows"][0]
            self.assertEqual(str(item["line"].stock_after), "12.50")
            self.assertEqual(item["material"]["unit"], "m")

    def test_optional_delivery_fields_and_multiple_lines(self):
        from .models import MaterialReceiptLine
        from requests_app.models import StockMovement
        receipt, _ = self.receive(receipt_data={**self.data, "supplier": "", "delivery_reference": ""})
        movement = StockMovement.objects.create(material=self.material, quantity=1, movement_type="IN", performed_by=self.user)
        MaterialReceiptLine.objects.create(receipt=receipt, material=self.material, quantity=1,
            stock_after=13.50, movement=movement, material_snapshot={"version": 1, "name": "Second recorded line", "code": "SECOND", "unit": "m", "category_name": "Tools", "category_code": "TOOLS"})
        response = self.page(receipt)
        panel = response.content.decode().split('<section class="entry-success entry-confirmation"', 1)[1].split('</section>', 1)[0]
        self.assertIn("Second recorded line", panel)
        self.assertEqual(len(response.context["confirmation"]["line_rows"]), 2)
        self.assertNotIn("<dt>Supplier</dt>", panel)
        self.assertNotIn("<dt>Delivery/reference number</dt>", panel)

    def test_confirmation_retry_and_refresh_do_not_duplicate_receipt(self):
        from .test_material_entries import reviewed_payload
        from .models import MaterialReceipt
        from requests_app.models import StockMovement
        payload = reviewed_payload(self.user, {**self.data, "material": self.material.pk,
            "mode": "existing", "token": new_token(self.user, "existing")})
        first = self.client.post("/materials/entries/", payload)
        second = self.client.post("/materials/entries/", payload)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(first.url, second.url)
        self.assertEqual(self.client.get(first.url).status_code, 200)
        self.assertEqual(self.client.get(first.url).status_code, 200)
        self.assertEqual(MaterialReceipt.objects.count(), 1)
        self.assertEqual(StockMovement.objects.count(), 1)
        self.material.refresh_from_db()
        self.assertEqual(str(self.material.stock_quantity), "12.50")


class EntryPhaseTwoLayoutTests(EntryPresentationTests):
    def test_new_material_has_two_sections_with_each_field_once(self):
        from html.parser import HTMLParser
        class Fields(HTMLParser):
            def __init__(self):
                super().__init__(); self.sections = []; self.current = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "fieldset":
                    self.current = []; self.sections.append(self.current)
                if self.current is not None and tag in ("input", "select", "textarea") and attrs.get("name"):
                    self.current.append(attrs["name"])
            def handle_endtag(self, tag):
                if tag == "fieldset": self.current = None
        response = self.client.get("/materials/entries/?mode=new")
        html = response.content.decode().split('<form method="post" novalidate id="material-entry-form">')[1].split('</form>')[0]
        fields = Fields(); fields.feed(html)
        self.assertEqual(len(fields.sections), 2)
        self.assertEqual(set(fields.sections[0]), set(self.new) | {"description", "unit_price"})
        self.assertEqual(set(fields.sections[1]), set(self.data))
        self.assertEqual(len(fields.sections[0]), len(set(fields.sections[0])))
        self.assertNotContains(response, "purchase price")
        self.assertContains(response, '<details class="entry-section entry-drafts-panel">')
        self.assertContains(response, 'class="entry-drafts-count">0</span>')
        self.assertContains(response, 'data-limited=')

    def test_invalid_fields_keep_values_and_translated_errors(self):
        for language in ("en", "fr"):
            self.client.cookies["django_language"] = language
            response = self.client.post("/materials/entries/", {**self.payload("new"), "name": "Preserved name", "quantity": "-2", "supplier": "Preserved supplier"})
            self.assertContains(response, 'value="Preserved name"')
            self.assertContains(response, 'value="Preserved supplier"')
            self.assertTrue(response.context["receipt_form"].errors)
            self.assertFalse(response.context["review"])


class DraftDisclosurePresentationTests(TestCase):
    def test_pagination_keeps_disclosure_open_and_shows_total_count(self):
        from unittest.mock import patch
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(username="draft-disclosure", can_manage_stock=True)
        self.client.force_login(user)
        # Reuse the real view and paginator without changing draft storage.
        with patch("inventory.entry_views.list_drafts", return_value=[]):
            response = self.client.get("/materials/entries/?draft_page=2")
        self.assertContains(response, '<details class="entry-section entry-drafts-panel" open>')
        self.assertContains(response, 'class="entry-drafts-count">0</span>')
