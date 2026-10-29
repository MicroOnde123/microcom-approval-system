"""Pure formatter, real-template escaping and mocked detail-view tests; no DB."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied
from django.template import Context, Engine
from django.test import RequestFactory
from django.utils.translation import override

from .audit_presentation import format_event
from . import views


class AuditPresentationTests(unittest.TestCase):
    def state(self, quantity="1", price="80.0000", currency="USD", note=""):
        return {"note": note, "lines": [[1, quantity, price, currency]]}

    def test_bilingual_created_values_and_explicit_current_label(self):
        payload = {"currency": "USD", "lines": [{"line": 1, "net": "1", "price": "80.0000"}]}
        for language, title, label in (("en", "Draft created", "Current invoice-line label"),
                ("fr", "Brouillon créé", "Libellé actuel de la ligne de facture")):
            with override(language):
                result = format_event("DRAFT_CREATED", payload, {1: "MikroTik"})
                self.assertEqual(result["title"], title)
                self.assertIn(label, result["items"][0]); self.assertIn("USD", result["items"][0])
                self.assertIn("80,0000" if language == "fr" else "80.0000", result["items"][0])

    def test_unchanged_refresh_is_retained_and_neutral(self):
        for language, wording in (("en", "Refresh completed without recorded quantity or price changes."),
                ("fr", "Actualisation terminée sans changement enregistré de quantité ou de prix.")):
            with override(language):
                result = format_event("DRAFT_REFRESHED", {"before": self.state(), "after": self.state()})
                self.assertEqual(result["description"], wording); self.assertEqual(result["items"], [])

    def test_actual_quantity_price_currency_and_note_differences(self):
        payload = {"before": self.state(price=None, note="old"),
                   "after": self.state(quantity="2", price="0", currency="EUR", note="new")}
        result = format_event("DRAFT_EDITED", payload)
        text = " ".join(result["items"])
        for value in ("Invoice line #1", "1 → 2", "Not priced", "0 EUR", "USD → EUR", "old → new"):
            self.assertIn(value, text)

    def test_null_is_distinct_from_zero(self):
        for price, expected in ((None, "Not priced"), ("0", "0 USD")):
            result = format_event("DRAFT_CREATED", {"currency": "USD", "lines": [{"line": 99, "net": "1", "price": price}]})
            self.assertIn(expected, result["items"][0])

    def test_malformed_and_unknown_payloads_fail_safely(self):
        payloads = [None, [], "raw", {}, {"before": self.state(), "after": {"lines": [[1]]}},
            {"before": self.state(), "after": self.state(price="NaN")},
            {"before": self.state(), "after": self.state(quantity="1e999999")},
            {"before": self.state(), "after": self.state(price=True)}]
        for payload in payloads:
            self.assertEqual(format_event("DRAFT_REFRESHED", payload)["items"], [])
            self.assertIn("unavailable", format_event("DRAFT_REFRESHED", payload)["description"])
        self.assertEqual(format_event("UNKNOWN", {"secret": "never display"})["title"], "Other invoice event")
        self.assertNotIn("never display", str(format_event("UNKNOWN", {"secret": "never display"})))

    def test_added_removed_and_missing_line_references(self):
        payload = {"before": self.state(), "after": {"note": "", "lines": [[2, "3", "4", "USD"]]}}
        text = str(format_event("DRAFT_EDITED", payload))
        self.assertIn("Line added", text); self.assertIn("Line removed", text)
        self.assertIn("Invoice line #2", text)

    def test_finalization_uses_only_recorded_reference_total_and_date(self):
        result = format_event("FINALIZED", {"number": "FAC/0001/2026", "total": "80.00", "currency": "USD", "issue_date": "2026-10-27"})
        self.assertEqual(len(result["items"]), 3)
        self.assertIn("80.00 USD", " ".join(result["items"]))

    def test_payload_immutability(self):
        payload = {"before": self.state(), "after": self.state(price="0")}; before = deepcopy(payload)
        labels = {1: "Label"}; original = labels.copy()
        format_event("DRAFT_EDITED", payload, labels)
        self.assertEqual(payload, before); self.assertEqual(labels, original)

    def test_real_history_template_escapes_text_and_translates_label(self):
        source = Path("templates/invoicing/detail.html").read_text(encoding="utf-8")
        history = source[source.index('<h2>{% trans "Invoice history" %}</h2>'):].replace("{% endblock %}", "")
        template = Engine(libraries={"i18n": "django.templatetags.i18n"}).from_string("{% load i18n %}" + history)
        event = SimpleNamespace(actor="<script>actor</script>", occurred_at=datetime(2026, 10, 27, tzinfo=timezone.utc))
        payload = {"before": self.state(), "after": self.state(note="<script>alert(1)</script>")}
        with override("fr"):
            result = template.render(Context({"audit_history": [{"event": event,
                "presentation": format_event("DRAFT_EDITED", payload, {1: "<b>material</b>"})}]}))
        self.assertIn("Détails de l’audit", result); self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result); self.assertNotIn("<pre>", result)

    def test_detail_batches_lines_and_actors_without_mutating_events(self):
        for count in (1, 30):
            invoice = Mock(status="DRAFT")
            lines = [SimpleNamespace(pk=1, material_code_snapshot="M", description_snapshot="Current label")]
            invoice.lines.order_by.return_value = iter(lines)
            events = [SimpleNamespace(event_type="DRAFT_REFRESHED", details={"before": self.state(), "after": self.state()},
                actor="Actor", occurred_at=None) for _ in range(count)]
            before = deepcopy([vars(event) for event in events])
            invoice.invoiceauditevent_set.select_related.return_value.order_by.return_value = events
            request = RequestFactory().get("/invoices/1/"); request.user = Mock(is_authenticated=True)
            with patch.object(views, "_invoice", return_value=invoice), patch.object(views, "return_note_navigation", return_value={}), \
                    patch.object(views, "render") as render:
                views.invoice_detail(request, 1)
            invoice.lines.order_by.assert_called_once_with("position", "pk")
            invoice.invoiceauditevent_set.select_related.assert_called_once_with("actor")
            self.assertEqual(len(render.call_args.args[2]["audit_history"]), count)
            self.assertEqual([vars(event) for event in events], before)
            invoice.save.assert_not_called()

    def test_detail_authorization_precedes_history_access(self):
        request = RequestFactory().get("/invoices/1/"); request.user = Mock(is_authenticated=True)
        with patch.object(views, "_invoice", side_effect=PermissionDenied), patch.object(views, "render") as render:
            with self.assertRaises(PermissionDenied):
                views.invoice_detail(request, 1)
        render.assert_not_called()
