"""Focused HTTP presentation coverage; use isolated PostgreSQL settings only."""
from decimal import Decimal
from html.parser import HTMLParser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Invoice, InvoiceAuditEvent
from .services import draft_revision
from .test_lifecycle import LifecycleFixtures


class InvoiceWorkflowPresentationTests(LifecycleFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def edit_data(self, invoice, price="1.2345", **changes):
        return {"revision": draft_revision(invoice, self.user), "note": "Entered note",
            "prices-TOTAL_FORMS": "1", "prices-INITIAL_FORMS": "1",
            "prices-MIN_NUM_FORMS": "0", "prices-MAX_NUM_FORMS": "1000",
            "prices-0-line_id": str(invoice.lines.get().pk), "prices-0-unit_price": price, **changes}

    def test_creation_context_is_read_only_and_permissions_unchanged(self):
        url = reverse("invoicing:create", args=[self.req.pk])
        before = self.source_snapshot()
        for lang in ("en", "fr"):
            self.client.cookies["django_language"] = lang
            response = self.client.get(url)
            self.assertContains(response, self.req.request_number)
            self.assertContains(response, self.configuration.company_name)
            self.assertContains(response, self.branch.name)
            self.assertContains(response, self.material.code)
            self.assertContains(response, 'scope="col"', count=2)
            self.assertContains(response, 'id="invoice-create-form"')
            self.assertContains(response, "Quantit\u00e9 approuv\u00e9e" if lang == "fr" else "Approved quantity")
        self.assertFalse(Invoice.objects.exists())
        self.assertEqual(self.source_snapshot(), before)
        other = get_user_model().objects.create_user(username="workflow-no-access")
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.client.post(url, {"currency": "USD"}).status_code, 403)

    def test_price_errors_are_associated_and_values_are_preserved(self):
        invoice = self.create()
        url = reverse("invoicing:edit", args=[invoice.pk])
        for lang in ("en", "fr"):
            self.client.cookies["django_language"] = lang
            response = self.client.post(url, self.edit_data(invoice, "1.23456"))
            self.assertTrue(response.context["prices"].errors[0])
            self.assertContains(response, 'for="id_prices-0-unit_price"')
            self.assertContains(response, 'id="id_prices-0-unit_price_error"')
            self.assertContains(response, 'aria-describedby="id_prices-0-unit_price_helptext id_prices-0-unit_price_error"')
            self.assertContains(response, 'value="1.23456"')
            self.assertContains(response, "Entered note")
            self.assertContains(response, self.material.code)
            label = response.context["prices"].forms[0].fields["unit_price"].label
            self.assertIn("Prix unitaire pour" if lang == "fr" else "Unit price for", label)
            self.assertIn(self.material.code, label)
        self.assertIsNone(invoice.lines.get().unit_price)

    def test_save_retains_precision_zero_and_unknown_without_refresh(self):
        from unittest.mock import patch
        invoice = self.create()
        url = reverse("invoicing:edit", args=[invoice.pk])
        before = self.source_snapshot()
        for raw, expected in (("1.2345", Decimal("1.2345")), ("0", Decimal("0")), ("", None)):
            invoice.refresh_from_db()
            with patch("invoicing.views.refresh_draft") as refresh:
                response = self.client.post(url, self.edit_data(invoice, raw))
                self.assertEqual(response.status_code, 302)
                refresh.assert_not_called()
            line = invoice.lines.get()
            self.assertEqual(line.unit_price, expected)
            self.assertEqual(line.quantity, 10)
        self.assertEqual(self.source_snapshot(), before)

    def test_refresh_is_a_separate_post_form_with_unique_revision_ids(self):
        invoice = self.create()
        page = self.client.get(reverse("invoicing:edit", args=[invoice.pk]))
        class Forms(HTMLParser):
            def __init__(self):
                super().__init__(); self.forms = []; self.current = None; self.ids = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get("id"): self.ids.append(attrs["id"])
                if tag == "form":
                    self.current = {"attrs": attrs, "fields": []}; self.forms.append(self.current)
                if self.current is not None and tag in ("input", "textarea"):
                    self.current["fields"].append(attrs.get("name"))
            def handle_endtag(self, tag):
                if tag == "form": self.current = None
        parsed = Forms(); parsed.feed(page.content.decode())
        refresh = next(f for f in parsed.forms if f["attrs"].get("id") == "invoice-refresh-form")
        self.assertEqual(refresh["attrs"]["method"], "post")
        self.assertEqual(refresh["attrs"]["action"], reverse("invoicing:refresh", args=[invoice.pk]))
        self.assertEqual(set(refresh["fields"]), {"csrfmiddlewaretoken", "revision"})
        self.assertEqual(parsed.ids.count("id_revision"), 1)
        self.assertContains(page, 'class="invoice-section invoice-refresh-section"')
        self.assertContains(page, "css/invoice_workflow.css")

    def test_review_total_uses_stored_lines_and_preserves_unknown_zero_precision(self):
        invoice = self.create()
        url = reverse("invoicing:finalize", args=[invoice.pk])
        self.assertIsNone(self.client.get(url).context["review_total"])
        for price, expected in (("1.2345", Decimal("12.35")), ("0", Decimal("0.00"))):
            self.price(invoice, price)
            for lang in ("en", "fr"):
                self.client.cookies["django_language"] = lang
                page = self.client.get(url)
                self.assertEqual(page.context["review_total"], expected)
                self.assertContains(page, self.material.code)
                self.assertContains(page, "pcs")
                self.assertContains(page, "USD")
                self.assertContains(page, self.configuration.company_name)
                self.assertContains(page, self.branch.physical_address.splitlines()[0])
                self.assertContains(page, "Confirmer la finalisation" if lang == "fr" else "Confirm finalization")
                self.assertContains(page, 'scope="col"', count=4)
                self.assertContains(page, 'name="confirm"')
        invoice.refresh_from_db()
        self.assertIsNone(invoice.total)
        self.assertIsNone(invoice.number)

    def test_stale_and_tampered_revisions_cannot_save_or_finalize(self):
        invoice = self.create()
        stale = self.edit_data(invoice)
        self.price(invoice, "2")
        for revision in (stale["revision"], "tampered"):
            response = self.client.post(reverse("invoicing:edit", args=[invoice.pk]), {**stale, "revision": revision})
            self.assertTrue(response.context["form"].non_field_errors())
            self.assertEqual(invoice.lines.get().unit_price, Decimal("2"))
        self.verified_sequence()
        response = self.client.post(reverse("invoicing:finalize", args=[invoice.pk]),
            {"revision": "tampered", "confirm": "on", "series": "MAIN"})
        self.assertTrue(response.context["form"].non_field_errors())
        invoice.refresh_from_db(); self.assertEqual(invoice.status,"DRAFT")

    def test_finalization_requires_confirmation_and_duplicate_post_saves_once(self):
        invoice = self.create(); self.price(invoice); self.verified_sequence()
        url = reverse("invoicing:finalize", args=[invoice.pk])
        data = {"revision": draft_revision(invoice,self.user), "series": "MAIN"}
        invalid = self.client.post(url, data)
        self.assertIn("confirm", invalid.context["form"].errors)
        self.assertContains(invalid, 'id="id_confirm_error"')
        self.assertEqual(self.client.post(url, {**data,"confirm":"on"}).status_code,302)
        invoice.refresh_from_db(); frozen = (invoice.number, invoice.total)
        self.assertEqual(self.client.post(url, {**data,"confirm":"on"}).status_code,302)
        invoice.refresh_from_db(); self.assertEqual((invoice.number,invoice.total),frozen)
        self.assertEqual(InvoiceAuditEvent.objects.filter(invoice=invoice,event_type="FINALIZED").count(),1)
