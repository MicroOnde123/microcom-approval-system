"""Mocked E-R3 HTTP contracts only; no real permissions, sessions or database."""
from contextlib import ExitStack
from decimal import Decimal
import io
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import resolve, reverse
from django.utils.translation import override

from . import return_note_access as access, return_note_views as views
from .return_note_forms import ReturnNoteSelectionForm


class ReturnNoteViewTests(unittest.TestCase):
    def setUp(self):
        from .test_mock_http import isolate_mock_context
        isolate_mock_context(self)
        self.factory = RequestFactory()
        self.user = SimpleNamespace(pk=7, is_authenticated=True, is_staff=True, is_active=True,
                                    username="synthetic-staff", can_manage_stock=False)
        self.invoice = SimpleNamespace(pk=11, request_id=21, status="FINALIZED", number="FAC-SYN-001", currency="USD")

    def request(self, method="get", data=None):
        request = getattr(self.factory, method)("/offline/", data or {})
        request.user = self.user; request.session = {}
        return request

    def test_default_gate_blocks_all_seven_routes_before_any_lookup(self):
        routes = [("return_note_select", {"invoice_id": 11}, "get"),
                  ("return_note_preview", {"invoice_id": 11}, "post"),
                  ("return_note_issue", {"invoice_id": 11}, "post"),
                  ("return_note_history", {"invoice_id": 11}, "get"),
                  ("return_note_detail", {"note_id": 2}, "get"),
                  ("return_note_pdf", {"note_id": 2, "language": "en"}, "post"),
                  ("return_note_download", {"artifact_id": 3}, "get"),
                  ("return_note_print", {"note_id": 2}, "post")]
        with patch.object(views, "_invoice") as lookup, patch.object(views.issuance, "get_material_return_note") as retrieve:
            for name, kwargs, method in routes:
                match = resolve(reverse("invoicing:" + name, kwargs=kwargs))
                with self.subTest(route=name), self.assertRaises(Http404): match.func(self.request(method), **match.kwargs)
            lookup.assert_not_called(); retrieve.assert_not_called()
        self.assertFalse(access.ui_enabled())

    def test_default_gate_blocks_document_service_and_navigation_without_queries(self):
        from . import return_note_documents as documents
        with patch.object(access.Invoice.objects, "filter") as query:
            self.assertEqual(access.navigation(self.user, request_id=21), {})
            query.assert_not_called()
        with patch.object(documents, "get_material_return_note") as retrieve:
            with self.assertRaises(Http404): documents.generate_pdf(1, self.user, language="en")
            with self.assertRaises(Http404): documents.download_pdf(1, self.user)
            retrieve.assert_not_called()

    def test_login_and_post_only_methods(self):
        with patch.object(access, "ui_enabled", return_value=True):
            request = self.request(); request.user = AnonymousUser()
            self.assertEqual(views.select(request, 11).status_code, 302)
            for function, kwargs in [(views.preview, {"invoice_id": 11}), (views.issue, {"invoice_id": 11}),
                                      (views.pdf, {"note_id": 1, "language": "en"})]:
                self.assertEqual(function(self.request(), **kwargs).status_code, 405)

    def test_preview_stores_private_payload_and_exposes_only_opaque_handle(self):
        request = self.request("post", {"movements": ["42"], "reason": "Unused", "series": "MAIN"})
        form = ReturnNoteSelectionForm(request.POST, rows=[{"return_movement_id": 42, "eligible": True}],
                                       sequences=[SimpleNamespace(series="MAIN")])
        result = {"lines": [], "total": "2.00", "currency": "USD", "cumulative_returned_value": "2.00",
                  "adjusted_net_value": "4.00", "original_invoice_snapshot": {"number": "FAC-SYN-001"},
                  "business_date": "2026-10-27", "issuance_token": "11111111-1111-4111-8111-111111111111",
                  "confirmation": "SECRET-SIGNED-PAYLOAD", "state_digest": "SECRET-DIGEST"}
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", return_value=self.invoice), \
             patch.object(views, "_selection", return_value={"form": form}), \
             patch.object(views.issuance, "preview_material_return_note", return_value=result) as preview:
            response = views.preview(request, 11)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for secret in [result["confirmation"], result["issuance_token"], result["state_digest"]]: self.assertNotIn(secret, body)
        handle, entry = next(iter(request.session[views.SESSION_KEY].items()))
        self.assertEqual(len(handle), 32); self.assertIn(handle, body)
        self.assertEqual(entry["confirmation"], result["confirmation"])
        preview.assert_called_once_with(11, self.user, return_movement_ids=[42], reason="Unused", series="MAIN")
        self.assertIn("no-store", response["Cache-Control"])

    def test_issue_uses_saved_arguments_not_forged_client_values_and_retains_replay(self):
        handle = "a" * 32
        request = self.request("post", {"handle": handle, "confirm": "on", "reason": "FORGED", "total": "999", "movements": ["99"]})
        entry = {"version": 2, "created_at": time.time(), "actor": 7, "invoice": 11,
                 "arguments": {"return_movement_ids": [42], "reason": "Original", "series": "MAIN"},
                 "issuance_token": "11111111-1111-4111-8111-111111111111", "confirmation": "saved-signature"}
        request.session[views.SESSION_KEY] = {handle: entry}
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", return_value=self.invoice), \
             patch.object(views.issuance, "issue_material_return_note", return_value=SimpleNamespace(pk=9)) as issue, \
             patch.object(views.messages, "success"):
            for _ in range(2): self.assertEqual(views.issue(request, 11).status_code, 302)
        self.assertEqual(issue.call_count, 2)
        issue.assert_called_with(11, self.user, **entry["arguments"], issuance_token=entry["issuance_token"], confirmation="saved-signature")
        self.assertEqual(request.session[views.SESSION_KEY][handle], entry)

    def test_missing_or_cross_user_handle_and_unconfirmed_submission_never_issue(self):
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", return_value=self.invoice), \
             patch.object(views.issuance, "issue_material_return_note") as issue:
            for data in [{}, {"handle": "a" * 32}, {"handle": "a" * 32, "confirm": "on"}]:
                request = self.request("post", data)
                if data.get("confirm"):
                    request.session[views.SESSION_KEY] = {"a" * 32: {"actor": 999, "invoice": 11}}
                self.assertIn(views.issue(request, 11).status_code, [400, 409])
            issue.assert_not_called()

    def test_stale_expired_service_error_never_reissues_or_exposes_secrets(self):
        request = self.request("post", {"handle": "b" * 32, "confirm": "on"})
        request.session[views.SESSION_KEY] = {"b" * 32: {"version": 2, "created_at": time.time(), "actor": 7, "invoice": 11,
            "arguments": {"return_movement_ids": [42], "reason": "Reason", "series": "MAIN"},
            "issuance_token": "11111111-1111-4111-8111-111111111111", "confirmation": "hidden-confirmation"}}
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", return_value=self.invoice), \
             patch.object(views.issuance, "issue_material_return_note", side_effect=ValidationError("Preview expired")) as issue:
            response = views.issue(request, 11)
        self.assertEqual(response.status_code, 409); self.assertEqual(issue.call_count, 1)
        self.assertNotIn(b"hidden-token", response.content); self.assertNotIn(b"hidden-confirmation", response.content)

    def test_multiple_tabs_and_signed_cookie_sessions(self):
        request = self.request()
        a = views._store(request, 11, {"issuance_token": "11111111-1111-4111-8111-111111111111", "confirmation": "sa"},
                         {"return_movement_ids": [42], "reason": "First", "series": "MAIN"})
        b = views._store(request, 11, {"issuance_token": "22222222-2222-4222-8222-222222222222", "confirmation": "sb"},
                         {"return_movement_ids": [43], "reason": "Second", "series": "MAIN"})
        self.assertNotEqual(a, b); self.assertEqual(len(request.session[views.SESSION_KEY]), 2)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 900)
        with override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies"), self.assertRaises(ValidationError):
            views._store(request, 11, {"issuance_token": "x", "confirmation": "secret"}, {})

    def test_scope_denial_and_revoked_service_authorization_propagate(self):
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", side_effect=PermissionDenied):
            with self.assertRaises(PermissionDenied): views.select(self.request(), 11)
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views.issuance, "get_material_return_note", side_effect=PermissionDenied):
            with self.assertRaises(PermissionDenied): views.detail(self.request(), 2)

    def test_document_permission_download_headers_and_storage_error_sanitization(self):
        artifact = SimpleNamespace(pk=2, note_id=3, language="fr")
        note = SimpleNamespace(pk=3, invoice=SimpleNamespace(request_id=21))
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(views.MaterialReturnNoteArtifact.objects, "get", return_value=artifact), \
             patch.object(views.issuance, "get_material_return_note", return_value=note), \
             patch.object(views, "authorize_return_note"), \
             patch.object(views, "download_pdf", return_value=(artifact, io.BytesIO(b"%PDF-synthetic"))):
            response = views.download(self.request(), 2)
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn("private, no-store", response["Cache-Control"])
            self.assertIn("return-note-3-fr.pdf", response["Content-Disposition"])
            response.close()
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(views.issuance, "get_material_return_note", return_value=note), \
             patch.object(views, "authorize_return_note"), \
             patch.object(views, "generate_pdf", side_effect=ImproperlyConfigured("SECRET/PATH")):
            response = views.pdf(self.request("post"), 3, "en")
        self.assertEqual(response.status_code, 409); self.assertNotIn(b"SECRET/PATH", response.content)

    def test_no_eligible_returns_and_bilingual_messages(self):
        for language, text in [("en", "No eligible undocumented returns"), ("fr", "Aucun retour admissible")]:
            context = {"invoice": self.invoice, "rows": [], "has_eligible": False, "has_sequences": False,
                       "form": ReturnNoteSelectionForm(rows=[], sequences=[])}
            with override(language), patch.object(access, "ui_enabled", return_value=True), \
                 patch.object(views, "_invoice", return_value=self.invoice), patch.object(views, "_selection", return_value=context):
                response = views.select(self.request(), 11)
                self.assertIn(text, response.content.decode())
                self.assertIn(b"disabled", response.content)

    def test_disabled_links_are_empty_on_old_pages(self):
        from .templatetags.return_note_navigation import return_note_links
        self.assertEqual(return_note_links(self.user, 21), {})
        self.assertEqual(render_to_string("invoicing/return_notes/links.html", {"return_note_nav": {}}).strip(), "")

    def test_navigation_does_not_grant_issue_to_read_only_user(self):
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(access, "authorize_return_note", side_effect=[self.user, PermissionDenied]):
            links = access.navigation(self.user, invoice=self.invoice)
        self.assertTrue(links["can_read"]); self.assertFalse(links["can_issue"])

    def test_selection_rejects_ineligible_duplicate_ids_and_client_prices(self):
        form = ReturnNoteSelectionForm({"movements": ["42", "42"], "reason": "Reason", "series": "MAIN"},
            rows=[{"return_movement_id": 42, "eligible": True}], sequences=[SimpleNamespace(series="MAIN")])
        self.assertFalse(form.is_valid())
        self.assertNotIn("price", form.fields); self.assertNotIn("currency", form.fields)
        self.assertNotIn("total", form.fields); self.assertNotIn("quantity", form.fields)

    def test_csrf_middleware_rejects_untrusted_post_without_invoking_issue(self):
        from django.middleware.csrf import CsrfViewMiddleware
        from django.http import HttpResponse
        request = self.request("post", {"handle": "a" * 32, "confirm": "on"})
        response = CsrfViewMiddleware(lambda request: HttpResponse()).process_view(request, views.issue, (), {"invoice_id": 11})
        self.assertEqual(response.status_code, 403)

    def test_history_retrieves_each_paginated_document_through_er2(self):
        note = SimpleNamespace(pk=9, number="BR-SYN/0007", issue_date=None, total=Decimal("2"), currency="USD")
        note.business_timezone = "Africa/Kinshasa"; note.finalized_at = None
        note.lines = Mock(order_by=Mock(return_value=Mock(values=Mock(return_value=[]))))
        self.invoice.material_return_notes = Mock(filter=Mock(return_value=Mock(order_by=Mock(return_value=Mock(values_list=Mock(return_value=[9]))))))
        with patch.object(access, "ui_enabled", return_value=True), patch.object(views, "_invoice", return_value=self.invoice), \
             patch.object(views, "navigation", return_value={}), \
             patch.object(views.issuance, "get_material_return_note", return_value=note) as retrieve:
            response = views.history(self.request(), 11)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"BR-SYN/0007", response.content)
        retrieve.assert_called_once_with(9, self.user)
