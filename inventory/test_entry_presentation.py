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
                self.assertContains(response, 'class="entry-action-bar"')
                self.assertContains(response, 'class="entry-search-icon"')
                self.assertContains(response, 'name="action" value="verify"')
                self.assertContains(response, 'novalidate')
                self.assertContains(response, "Informations de livraison" if language == "fr" else "Delivery information")
                self.assertContains(response, "Param\u00e8tres de stock" if language == "fr" and mode == "new" else "Material and stock" if language == "en" and mode == "existing" else "Material Entries" if language == "en" else "Entr\u00e9es de stock")
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
