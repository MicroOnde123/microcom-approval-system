"""Validated filters and all-page batch selection, with no DB connections."""
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import unittest

from django.core.exceptions import ValidationError, PermissionDenied
from django.test import RequestFactory
from django.core.paginator import Paginator
from django.template import Context, Engine, Library
from django.utils.translation import override, gettext

from .filters import InvoiceFilterForm, apply_invoice_filters
from . import printing, views


class InvoiceFilterPrintingTests(unittest.TestCase):
    def filters(self, **changes):
        values = {"q": "KSH", "date_from": "2026-01-01", "date_to": "2026-12-31", "status": ""}
        values.update(changes); return values

    def test_listing_dates_optional_printing_dates_required(self):
        self.assertTrue(InvoiceFilterForm({}).is_valid())
        for values in ({}, {"date_from": "2026-01-01"}, {"date_to": "2026-12-31"}):
            form = InvoiceFilterForm(values, require_dates=True)
            self.assertFalse(form.is_valid())
        form = InvoiceFilterForm(self.filters(), require_dates=True)
        self.assertTrue(form.is_valid()); self.assertEqual(form.cleaned_data["date_from"], date(2026, 1, 1))

    def test_bad_dates_ranges_status_and_overlong_search_rejected(self):
        for changes in ({"date_from": "2026-02-30"}, {"date_to": "not-a-date"},
                {"date_from": "2027-01-01"}, {"status": "UNKNOWN"}, {"q": "X" * 201}):
            self.assertFalse(InvoiceFilterForm(self.filters(**changes)).is_valid())

    def test_all_draft_finalized_status_choices(self):
        for status in ("", "DRAFT", "FINALIZED"):
            self.assertTrue(InvoiceFilterForm({"status": status}).is_valid())
        with override("fr"):
            self.assertEqual(str(InvoiceFilterForm().fields["status"].choices[0][1]), "Tous")

    def test_shared_filter_narrows_scope_using_issue_dates_and_search(self):
        queryset = Mock(); queryset.filter.return_value = queryset
        result = apply_invoice_filters(queryset, {"q": "KSH", "date_from": date(2026, 1, 1),
            "date_to": date(2026, 12, 31), "status": "FINALIZED"})
        self.assertIs(result, queryset)
        calls = queryset.filter.call_args_list
        self.assertEqual(calls[1].kwargs, {"issue_date__gte": date(2026, 1, 1)})
        self.assertEqual(calls[2].kwargs, {"issue_date__lte": date(2026, 12, 31)})
        self.assertEqual(calls[3].kwargs, {"status": "FINALIZED"})
        search = str(calls[0].args[0])
        for field in ("number__icontains", "request_reference_snapshot__icontains", "request__request_number__icontains",
                "succursale_snapshot__code__icontains", "succursale_snapshot__name__icontains", "succursale__name__icontains"):
            self.assertIn(field, search)

    def test_postgresql_filter_sql_compiles_without_a_connection(self):
        from django.db.backends.postgresql.base import DatabaseWrapper
        from .models import Invoice
        backend = DatabaseWrapper({"ENGINE": "django.db.backends.postgresql", "NAME": "", "OPTIONS": {}, "TIME_ZONE": None})
        backend.__dict__["pg_version"] = 180006
        form = InvoiceFilterForm(self.filters(), require_dates=True)
        self.assertTrue(form.is_valid())
        queryset = apply_invoice_filters(Invoice.objects.filter(request_id__in=[1]), form.cleaned_data).filter(status="FINALIZED")
        sql, params = queryset.query.get_compiler(connection=backend).as_sql()
        self.assertIn('"issue_date" >=', sql); self.assertIn('"issue_date" <=', sql)
        self.assertIn('"succursale_snapshot"', sql)
        self.assertNotIn('"date_needed"', sql)
        self.assertIn("FINALIZED", params)
        self.assertIsNone(backend.connection)

    def selection(self, ids, data=None):
        user = Mock(); scope = Mock(); scope.values.return_value = "authorized-requests"
        queryset = MagicMock()
        queryset.filter.return_value = queryset
        queryset.order_by.return_value.values_list.return_value.__getitem__.return_value = ids
        with patch.object(printing, "require_permission") as permission, patch.object(printing, "request_scope", return_value=scope), \
                patch.object(printing.Invoice.objects, "filter", return_value=queryset) as query, \
                patch.object(printing, "prepare_bulk_print", return_value=b"synthetic") as prepare:
            result = printing.prepare_filtered_print(data or self.filters(), user, language="fr")
        return result, user, queryset, query, prepare, permission

    def test_all_matching_rows_selected_not_client_ids_count_or_page(self):
        # Deliberately includes ids beyond a notional first page. The selector
        # never receives a paginator or trusts the page/count/selected IDs.
        ids = list(range(1, 19))
        result, user, queryset, query, prepare, permission = self.selection(ids,
            self.filters(page="2", selected_invoices=["999"], count="1"))
        self.assertEqual(result, b"synthetic")
        permission.assert_called_once_with(user, "view_invoice")
        query.assert_called_once_with(request_id__in="authorized-requests")
        queryset.filter.assert_any_call(status="FINALIZED")
        queryset.order_by.assert_called_once_with("issue_date", "number", "pk")
        queryset.order_by.return_value.values_list.return_value.__getitem__.assert_called_once_with(slice(None, 21))
        prepare.assert_called_once_with(ids, user, language="fr")

    def test_oversized_match_set_rejected_before_any_generation(self):
        queryset = MagicMock(); queryset.filter.return_value = queryset
        queryset.order_by.return_value.values_list.return_value.__getitem__.return_value = list(range(1, 22))
        with patch.object(printing, "require_permission"), patch.object(printing, "request_scope"), \
                patch.object(printing.Invoice.objects, "filter", return_value=queryset), patch.object(printing, "prepare_bulk_print") as prepare:
            with self.assertRaisesRegex(ValidationError, "Narrow the date range"):
                printing.prepare_filtered_print(self.filters(), Mock(), language="en")
        prepare.assert_not_called()

    def test_no_matches_has_clear_bilingual_message(self):
        for language, expected in (("en", "No finalized invoices match these filters."),
                ("fr", "Aucune facture finalisée ne correspond à ces filtres.")):
            with override(language), self.assertRaises(ValidationError) as caught:
                self.selection([])
            self.assertEqual(caught.exception.messages, [expected])

    def test_invalid_dates_rejected_before_invoice_query(self):
        with patch.object(printing, "require_permission"), patch.object(printing.Invoice.objects, "filter") as query:
            with self.assertRaises(ValidationError):
                printing.prepare_filtered_print({}, Mock(), language="en")
        query.assert_not_called()

    def test_permission_failure_precedes_filter_and_record_access(self):
        with patch.object(printing, "require_permission", side_effect=PermissionDenied), \
                patch.object(printing.Invoice.objects, "filter") as query:
            with self.assertRaises(PermissionDenied):
                printing.prepare_filtered_print(self.filters(), Mock(), language="en")
        query.assert_not_called()

    def test_invalid_list_filters_fail_closed_and_pagination_keeps_filters(self):
        for invalid in (False, True):
            request = RequestFactory().get("/invoices/", self.filters(page="2", extra="ignored", date_from="bad" if invalid else "2026-01-01"))
            request.user = Mock(is_authenticated=True)
            queryset = Mock(); queryset.none.return_value = queryset
            queryset.filter.return_value = queryset
            queryset.select_related.return_value.annotate.return_value.order_by.return_value = []
            with patch.object(views, "require_permission"), patch.object(views, "request_scope") as scope, \
                    patch.object(views.Invoice.objects, "filter", return_value=queryset), patch.object(views, "render") as render:
                scope.return_value.filter.return_value.order_by.return_value = []
                views.invoice_list(request)
            context = render.call_args.args[2]
            self.assertEqual(context["page_obj"].paginator.per_page, 25)
            self.assertIn("q=KSH", context["active_querystring"])
            self.assertNotIn("page=", context["active_querystring"]); self.assertNotIn("extra=", context["active_querystring"])
            self.assertEqual(context["filter_form"].is_valid(), not invalid)
            if invalid:
                queryset.none.assert_called_once()

    def test_ui_uses_report_conventions_without_selection_checkboxes(self):
        source = Path("templates/invoicing/list.html").read_text(encoding="utf-8")
        for fragment in ('method="get"', 'class="form-grid"', 'class="data-table"', 'Print Filtered Invoices', 'active_querystring'):
            self.assertIn(fragment, source)
        self.assertNotIn('type="checkbox"', source)
        self.assertNotIn('selected_invoices', source)
        for language, expected in (("en", "Print Filtered Invoices"), ("fr", "Imprimer les factures filtrées")):
            with override(language):
                self.assertEqual(gettext("Print Filtered Invoices"), expected)

    def test_real_filter_form_renders_dates_errors_and_bilingual_action(self):
        source = Path("templates/invoicing/list.html").read_text(encoding="utf-8")
        library = Library()
        @library.simple_tag(name="url")
        def inert_url(*args, **kwargs):
            return "/synthetic/"
        engine = Engine(loaders=[("django.template.loaders.locmem.Loader",
            {"base.html": "{% block content %}{% endblock %}"})], libraries={"i18n": "django.templatetags.i18n"})
        engine.template_builtins.append(library)
        template = engine.from_string(source)
        for language, label in (("en", "Print Filtered Invoices"), ("fr", "Imprimer les factures filtrées")):
            with override(language):
                form = InvoiceFilterForm(self.filters(q='<script>alert(1)</script>'))
                self.assertTrue(form.is_valid())
                content = template.render(Context({"filter_form": form, "page_obj": Paginator([], 25).page(1),
                    "active_filters": self.filters(), "invoice_print_limit": 20}))
                self.assertIn(label, content); self.assertIn('type="date"', content)
                self.assertIn('value="2026-01-01"', content)
                self.assertNotIn("<script>", content)
                self.assertIn("&lt;script&gt;", content)
