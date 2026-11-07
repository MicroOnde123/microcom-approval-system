"""Invoice detail rendering through HTTP; isolated PostgreSQL only."""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.db import connection
from django.test.utils import CaptureQueriesContext
from inventory.pricing import update_price, price_state
from .test_lifecycle import LifecycleFixtures
from .services import draft_revision
from .models import Invoice, InvoiceAuditEvent


class InvoiceDetailPresentationTests(LifecycleFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def url(self, invoice):
        return reverse("invoicing:detail", args=[invoice.pk])

    def test_draft_unknown_zero_precision_currency_and_structure(self):
        invoice = self.create(currency="EUR")
        for lang in ("en", "fr"):
            self.client.cookies["django_language"] = lang
            response = self.client.get(self.url(invoice))
            self.assertContains(response, "Inconnu" if lang == "fr" else "Unknown")
            self.assertContains(response, "EUR")
            self.assertContains(response, 'id="invoice-summary-title"')
            self.assertContains(response, 'id="invoice-parties-title"')
            self.assertContains(response, 'scope="col"', count=7)
            self.assertContains(response, '<caption class="invoice-sr-only">', count=2)
            self.assertContains(response, "css/invoice_detail.css")
            self.assertNotContains(response, 'id="finalization-success-title"')
            self.assertContains(response, reverse("invoicing:edit", args=[invoice.pk]))
            self.assertContains(response, reverse("invoicing:finalize", args=[invoice.pk]))
        self.client.cookies["django_language"] = "en"
        self.price(invoice, "0")
        zero = self.client.get(self.url(invoice))
        self.assertContains(zero, "0.0000 EUR")
        self.assertEqual(zero.context["draft_total"], Decimal("0.00"))
        self.price(invoice, "1.2345")
        response = self.client.get(self.url(invoice))
        self.assertContains(response, "1.2345 EUR")
        self.assertEqual(response.context["draft_total"], invoice.lines.get().line_total)
        invoice.refresh_from_db()
        self.assertIsNone(invoice.total)

    def test_finalized_detail_uses_frozen_snapshots_and_read_only_actions(self):
        invoice = self.create(); self.price(invoice,"1.2345"); self.verified_sequence()
        invoice = self.finalize(invoice)
        expected = invoice.lines.get()
        update_price(self.material.pk, self.admin, price=Decimal("99"), currency="EUR", reason="Later catalogue", expected_state=price_state(self.material))
        self.material.name = "CURRENT CATALOGUE NAME"; self.material.save(update_fields=["name"])
        self.branch.name = "CURRENT BRANCH NAME"; self.branch.save()
        before = list(Invoice.objects.values()), list(InvoiceAuditEvent.objects.values())
        for lang in ("en", "fr"):
            self.client.cookies["django_language"] = lang
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(self.url(invoice))
            self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries))
            self.assertContains(response, invoice.number)
            self.assertContains(response, expected.description_snapshot)
            self.assertContains(response, invoice.company_snapshot["company_name"])
            self.assertContains(response, invoice.succursale_snapshot["name"])
            self.assertNotContains(response, "CURRENT CATALOGUE NAME")
            self.assertNotContains(response, "CURRENT BRANCH NAME")
            self.assertContains(response, "1,2345 USD" if lang == "fr" else "1.2345 USD")
            self.assertContains(response, reverse("invoicing:print", args=[invoice.pk]))
            self.assertContains(response, reverse("invoicing:download_invoice", args=[invoice.pk]))
            self.assertNotContains(response, reverse("invoicing:edit", args=[invoice.pk]))
            self.assertFalse(response.context["finalization_success"])
        self.assertEqual((list(Invoice.objects.values()), list(InvoiceAuditEvent.objects.values())), before)

    def test_success_is_one_time_and_bound_to_invoice_after_actual_finalize(self):
        invoice = self.create(); self.price(invoice); self.verified_sequence()
        for lang in ("fr",):
            self.client.cookies["django_language"] = lang
            response = self.client.post(reverse("invoicing:finalize", args=[invoice.pk]),
                {"series": "MAIN", "confirm": "on", "revision": draft_revision(invoice,self.user)})
            self.assertRedirects(response, self.url(invoice), fetch_redirect_response=False)
            page = self.client.get(response.url)
            self.assertTrue(page.context["finalization_success"])
            self.assertContains(page, 'id="finalization-success-title"')
            self.assertContains(page, "Facture finalis")
            invoice.refresh_from_db()
            self.assertEqual(page.context["invoice"].total, invoice.total)
            self.assertFalse(self.client.get(response.url).context["finalization_success"])
            self.assertFalse(self.client.get(self.url(invoice)+"?success=1").context["finalization_success"])
            retry = self.client.post(reverse("invoicing:finalize", args=[invoice.pk]), {"confirm": "on"})
            self.assertEqual(retry.status_code,302)
            self.assertFalse(self.client.get(retry.url).context["finalization_success"])

    def test_permission_denial_and_view_only_actions(self):
        invoice = self.create()
        other = get_user_model().objects.create_user(username="invoice-ui-other")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url(invoice)).status_code,403)
        other.user_permissions.add(Permission.objects.get(codename="view_invoice"))
        self.assertEqual(self.client.get(self.url(invoice)).status_code,403)
        self.user.user_permissions.remove(*Permission.objects.filter(codename__in=["change_invoice","finalize_invoice"]))
        self.client.force_login(self.user)
        response = self.client.get(self.url(invoice))
        self.assertEqual(response.status_code,200)
        self.assertNotContains(response, reverse("invoicing:edit", args=[invoice.pk]))
        self.assertNotContains(response, reverse("invoicing:finalize", args=[invoice.pk]))
