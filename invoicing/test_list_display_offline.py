"""Focused database-free invoice-list template and view orchestration tests."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.template import Context, Engine
from django.test import RequestFactory
from django.utils.translation import override

from . import views


class InvoiceListOfflineTests(unittest.TestCase):
    def invoice(self, **changes):
        values = dict(pk=1, status="DRAFT", number=None, total=None, currency="USD",
            request_reference_snapshot="", request=SimpleNamespace(request_number="REQ-SYNTHETIC"),
            get_status_display="Draft", list_line_count=1, list_priced_line_count=1,
            list_provisional_total=Decimal("80.00"))
        values.update(changes)
        return SimpleNamespace(**values)

    def render(self, invoice, language="en"):
        # Render the real list, with an inert base and URL tag to avoid app routing.
        from django.template import Library
        library = Library()
        @library.simple_tag(name="url")
        def inert_url(*args, **kwargs):
            return "/synthetic/"
        engine = Engine(loaders=[("django.template.loaders.locmem.Loader",
            {"base.html": "{% block content %}{% endblock %}"})],
            libraries={"i18n": "django.templatetags.i18n"})
        engine.template_builtins.append(library)
        template = engine.from_string(Path("templates/invoicing/list.html").read_text(encoding="utf-8"))
        with override(language):
            return template.render(Context({"page_obj": Paginator([invoice], 25).page(1), "candidate_requests": []}))

    def test_complete_pricing_and_translated_reference(self):
        self.assertIn("Draft #1", self.render(self.invoice()))
        self.assertIn("80.00 USD — Provisional", self.render(self.invoice()))
        french = self.render(self.invoice(), "fr")
        self.assertIn("Brouillon n° 1", french)
        self.assertIn("Provisoire", french)

    def test_missing_or_empty_lines_do_not_show_partial_total(self):
        for changes in ({"list_priced_line_count": 0}, {"list_line_count": 0, "list_priced_line_count": 0},
                        {"list_line_count": 2, "list_priced_line_count": 1}):
            invoice = self.invoice(**changes)
            self.assertIn("Incomplete pricing", self.render(invoice))
            self.assertNotIn("80.00", self.render(invoice))
            self.assertIn("Tarification incomplète", self.render(invoice, "fr"))

    def test_zero_price_is_complete(self):
        self.assertIn("0.00 USD — Provisional", self.render(self.invoice(list_provisional_total=Decimal("0.00"))))

    def test_sum_of_rounded_lines_is_displayed_without_recalculation(self):
        # Two stored .01 increments must display .02, not a re-rounded raw product.
        invoice = self.invoice(list_line_count=2, list_priced_line_count=2, list_provisional_total=Decimal("0.02"))
        self.assertIn("0.02 USD — Provisional", self.render(invoice))

    def test_finalized_uses_official_number_and_header_total(self):
        invoice = self.invoice(status="FINALIZED", number="FAC/0042/2026", total=Decimal("123.45"),
            list_provisional_total=Decimal("999.99"))
        text = self.render(invoice)
        self.assertIn("FAC/0042/2026", text); self.assertIn("123.45", text)
        self.assertNotIn("999.99", text); self.assertNotIn("Provisional", text)

    def test_render_does_not_mutate_invoice_values(self):
        invoice = self.invoice(); before = deepcopy(vars(invoice))
        self.render(invoice)
        self.assertEqual(vars(invoice), before)
        self.assertIsNone(invoice.number); self.assertIsNone(invoice.total)

    def test_view_preserves_scope_annotations_pagination_and_candidates(self):
        request = RequestFactory().get("/invoices/")
        request.user = Mock(is_authenticated=True)
        scope = Mock(); scope.values.return_value = "authorized-ids"
        scope.filter.return_value.order_by.return_value = []
        queryset = Mock(); queryset.select_related.return_value.annotate.return_value.order_by.return_value = [self.invoice()]
        with patch.object(views, "require_permission") as permission, patch.object(views, "request_scope", return_value=scope), \
             patch.object(views.Invoice.objects, "filter", return_value=queryset) as query, patch.object(views, "render") as render:
            views.invoice_list(request)
        permission.assert_called_once_with(request.user, "view_invoice")
        query.assert_called_once_with(request_id__in="authorized-ids")
        queryset.select_related.assert_called_once_with("request")
        annotations = queryset.select_related.return_value.annotate.call_args.kwargs
        self.assertEqual(annotations["list_provisional_total"].source_expressions[0].name, "lines__line_total")
        priced_filter = annotations["list_priced_line_count"].filter
        total_filter = annotations["list_provisional_total"].filter
        self.assertEqual(dict(getattr(priced_filter, "condition", priced_filter).children),
            {"status": "DRAFT", "lines__unit_price__isnull": False, "lines__line_total__isnull": False})
        self.assertEqual(dict(getattr(total_filter, "condition", total_filter).children), {"status": "DRAFT"})
        self.assertEqual(render.call_args.args[2]["page_obj"].paginator.per_page, 25)
        scope.filter.assert_called_once_with(status="APPROVED", classification="MICROCOM", stock_deducted=True, invoice__isnull=True)

    def test_permission_denial_precedes_query(self):
        request = RequestFactory().get("/invoices/"); request.user = Mock(is_authenticated=True)
        with patch.object(views, "require_permission", side_effect=PermissionDenied), \
             patch.object(views.Invoice.objects, "filter") as query:
            with self.assertRaises(PermissionDenied):
                views.invoice_list(request)
        query.assert_not_called()
