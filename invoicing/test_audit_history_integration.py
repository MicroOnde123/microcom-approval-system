"""Deferred database-backed tests; require a separately authorized test database."""
from unittest.mock import patch

from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from . import views
from .models import InvoiceAuditEvent
from .test_lifecycle import LifecycleFixtures


class AuditHistoryIntegrationTests(LifecycleFixtures, TestCase):
    def page(self, invoice):
        request = RequestFactory().get("/invoices/%s/" % invoice.pk); request.user = self.user
        context = {}
        def render(request, template, values):
            context.update(values)
            for row in values["audit_history"]:
                str(row["event"].actor)
            return HttpResponse("rendered")
        with patch.object(views, "render", side_effect=render):
            views.invoice_detail(request, invoice.pk)
        return context

    def test_audit_rows_unchanged_and_all_queries_are_reads(self):
        invoice = self.create(); self.price(invoice)
        self.user.has_perm("invoicing.view_invoice")
        before = list(InvoiceAuditEvent.objects.order_by("pk").values())
        with CaptureQueriesContext(connection) as queries:
            context = self.page(invoice)
        self.assertEqual(len(context["audit_history"]), len(before))
        self.assertEqual(list(InvoiceAuditEvent.objects.order_by("pk").values()), before)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries.captured_queries))

    def test_query_count_does_not_grow_with_history(self):
        invoice = self.create(); self.user.has_perm("invoicing.view_invoice")
        with CaptureQueriesContext(connection) as first:
            self.page(invoice)
        event = InvoiceAuditEvent.objects.get(invoice=invoice)
        for _ in range(10):
            InvoiceAuditEvent.objects.create(invoice=invoice, actor=self.user, event_type=event.event_type,
                document_identifier=event.document_identifier, details=event.details)
        with CaptureQueriesContext(connection) as second:
            context = self.page(invoice)
        self.assertEqual(len(context["audit_history"]), 11)
        self.assertEqual(len(first), len(second))
