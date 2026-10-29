"""Database-dependent list regressions; run only on a separately approved test DB."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from inventory.models import Material
from requests_app.models import RequestMaterialItem
from requests_app.services import approve_step
from . import views
from .models import Invoice, InvoiceLine, InvoiceAuditEvent, DocumentSequence, DocumentArtifact
from .test_lifecycle import LifecycleFixtures
from . import test_list_display_offline as display_helper


class InvoiceListDatabaseTests(LifecycleFixtures, TestCase):
    def page(self, user=None):
        request = RequestFactory().get("/invoices/"); request.user = user or self.user
        rows = []
        def render(request, template, context):
            rows.extend(context["page_obj"])
            # Real list template without session-saving middleware or navigation.
            for invoice in rows:
                display_helper.InvoiceListOfflineTests().render(invoice)
            return HttpResponse("rendered")
        with patch.object(views, "render", side_effect=render):
            views.invoice_list(request)
        return rows

    def test_complete_missing_and_zero_prices(self):
        invoice = self.create()
        row = self.page()[0]
        self.assertEqual(row.list_line_count, 1); self.assertEqual(row.list_priced_line_count, 0)
        self.price(invoice, "0")
        row = self.page()[0]
        self.assertEqual(row.list_priced_line_count, 1); self.assertEqual(row.list_provisional_total, Decimal("0.00"))
        self.price(invoice, "80")
        self.assertEqual(self.page()[0].list_provisional_total, Decimal("800.00"))
        invoice.refresh_from_db(); self.assertIsNone(invoice.total); self.assertIsNone(invoice.number)

    def test_empty_invoice_does_not_look_complete(self):
        invoice = self.create(); line = invoice.lines.get()
        line.issue_allocation.delete(); line.delete()
        row = self.page()[0]
        self.assertEqual(row.list_line_count, 0); self.assertIsNone(row.list_provisional_total)

    def test_multiple_lines_sum_existing_half_up_totals(self):
        req, _ = self.make_request(Decimal("0.5"))
        material = Material.objects.create(category=self.category, name="Second", code="SECOND-LIST", stock_quantity=10)
        RequestMaterialItem.objects.create(request=req, material=material, quantity=Decimal("0.5"))
        approve_step(req.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
        self.req = req
        invoice = self.create(); self.price(invoice, "0.01")
        row = self.page()[0]
        self.assertEqual(row.list_line_count, 2); self.assertEqual(row.list_priced_line_count, 2)
        self.assertEqual(row.list_provisional_total, Decimal("0.02"))

    def test_finalized_total_and_number_are_authoritative(self):
        invoice = self.create(); self.price(invoice); self.verified_sequence()
        invoice = self.finalize(invoice); row = self.page()[0]
        self.assertEqual(row.number, invoice.number); self.assertEqual(row.total, invoice.total)
        self.assertIsNone(row.list_provisional_total)

    def test_view_permission_does_not_expand_assignment_scope(self):
        self.create()
        self.other.user_permissions.add(Permission.objects.get(content_type__app_label="invoicing", codename="view_invoice"))
        self.assertEqual(self.page(self.other), [])

    def test_query_count_is_bounded_and_rendering_has_no_writes(self):
        self.create(); self.user.has_perm("invoicing.view_invoice")
        models = (Invoice, InvoiceLine, InvoiceAuditEvent, DocumentSequence, DocumentArtifact)
        before = {model: list(model.objects.order_by("pk").values()) for model in models}
        with CaptureQueriesContext(connection) as first:
            self.page()
        self.assertEqual(before, {model: list(model.objects.order_by("pk").values()) for model in models})
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in first.captured_queries))
        req, _ = self.make_request()
        approve_step(req.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
        self.req = req; self.create()
        with CaptureQueriesContext(connection) as second:
            self.page()
        self.assertEqual(len(first), len(second))
