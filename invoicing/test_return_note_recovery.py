"""E-R4 database-free recovery contracts; all financial operations are mocked."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import errno
import hashlib
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, OperationalError
from django.test import RequestFactory
from django.template.loader import render_to_string
from django.utils.translation import override

from . import return_note_access as access, return_note_views as views, return_note_sessions as sessions
from . import return_note_documents as documents, return_note_services as issuance
from .return_note_orphans import inspect_private_files
from .return_note_recovery import category
from . import test_return_note_documents as document_tests


def envelope(**updates):
    value = {"version": 2, "created_at": time.time(), "actor": 7, "invoice": 11,
        "arguments": {"return_movement_ids": [42], "reason": "Returned materials", "series": "MAIN"},
        "issuance_token": "11111111-1111-4111-8111-111111111111", "confirmation": "PRIVATE-SIGNATURE"}
    value.update(updates)
    return value


class ReturnNoteRecoveryTests(unittest.TestCase):
    def setUp(self):
        from .test_mock_http import isolate_mock_context
        from tempfile import mkdtemp
        from django.test import override_settings
        isolate_mock_context(self)
        evidence = override_settings(RETURN_NOTE_OFFLINE_EVIDENCE_ROOT=Path(mkdtemp(prefix="return-note-recovery-")))
        evidence.enable()
        self.addCleanup(evidence.disable)
        self.user = SimpleNamespace(pk=7, is_authenticated=True, is_staff=True, is_active=True, username="synthetic")
        self.invoice = SimpleNamespace(pk=11, request_id=21, number="FAC-SYN", currency="USD")
        self.factory = RequestFactory()
        self.handle = "a" * 32

    def request(self, entry=None):
        request = self.factory.post("/offline/", {"handle": self.handle, "confirm": "on"})
        request.user = self.user
        request.session = {sessions.SESSION_KEY: {self.handle: entry or envelope()}}
        return request

    def view_context(self):
        stack = ExitStack()
        stack.enter_context(patch.object(access, "ui_enabled", return_value=True))
        stack.enter_context(patch.object(views, "_invoice", return_value=self.invoice))
        stack.enter_context(patch.object(views.messages, "success"))
        return stack

    def test_structured_er2_categories_without_financial_execution(self):
        self.assertEqual(category(issuance._invalid()), "preview_invalid")
        self.assertEqual(category(issuance._unsafe()), "outcome_uncertain")
        self.assertEqual(category(ValidationError("Other validation")), "review_required")

    def test_uncertain_result_offers_same_handle_post_without_exposing_private_data(self):
        request = self.request(); original = deepcopy(request.session)
        with self.view_context(), patch.object(issuance, "issue_material_return_note", side_effect=issuance._unsafe()) as issue, \
             patch.object(sessions, "uuid4") as create_token:
            response = views.issue(request, 11)
        body = response.content.decode()
        self.assertEqual(response.status_code, 409)
        self.assertIn("Retry same confirmation", body); self.assertIn(self.handle, body)
        self.assertIn('method="post"', body)
        self.assertNotIn("PRIVATE-SIGNATURE", body)
        self.assertNotIn(envelope()["issuance_token"], body)
        self.assertNotIn("Start new preview", body)
        self.assertEqual(request.session, original)
        issue.assert_called_once(); create_token.assert_not_called()

    def test_repeated_retry_forwards_identical_original_inputs_and_recovers_committed_note(self):
        request = self.request(); entry = deepcopy(request.session[sessions.SESSION_KEY][self.handle])
        with self.view_context(), patch.object(issuance, "issue_material_return_note",
             side_effect=[issuance._unsafe(), SimpleNamespace(pk=99)]) as issue, patch.object(sessions, "uuid4") as new:
            self.assertEqual(views.issue(request, 11).status_code, 409)
            self.assertEqual(views.issue(request, 11).status_code, 302)
        self.assertEqual(issue.call_args_list[0], issue.call_args_list[1])
        issue.assert_called_with(11, self.user, **entry["arguments"], issuance_token=entry["issuance_token"], confirmation=entry["confirmation"])
        new.assert_not_called()

    def test_expired_confirmation_window_reaches_er2_for_committed_replay_only(self):
        request = self.request(envelope(created_at=time.time()-8000))
        entry, expired = sessions.load(request, 11, self.handle)
        self.assertTrue(expired)
        with self.view_context(), patch.object(issuance, "issue_material_return_note", return_value=SimpleNamespace(pk=99)) as issue:
            self.assertEqual(views.issue(request, 11).status_code, 302)
        issue.assert_called_once()
        # If E-R2 rejects an expired NEW issuance, no same-handle retry/new UUID
        # is fabricated in the view. E-R2 remains the signature-age authority.
        with self.view_context(), patch.object(issuance, "issue_material_return_note", side_effect=issuance._invalid()):
            response = views.issue(request, 11)
        self.assertNotIn(b"Retry same confirmation", response.content)

    def test_expired_session_missing_or_overwritten_handle_never_invokes_issuance(self):
        for raw in [{}, {"b" * 32: envelope()}, None, [], "wrong"]:
            request = self.request(); request.session[sessions.SESSION_KEY] = raw
            with self.subTest(raw=raw), self.view_context(), patch.object(issuance, "issue_material_return_note") as issue:
                response = views.issue(request, 11)
                self.assertEqual(response.status_code, 409); issue.assert_not_called()
                self.assertIn(b"different operation", response.content)

    def test_malformed_shapes_old_envelopes_and_future_timestamps_fail_closed(self):
        invalid = [envelope(version=True), envelope(version=1), envelope(created_at=float("nan")), envelope(created_at=-1),
            envelope(created_at=time.time()+1000), envelope(created_at=True), envelope(actor=True), envelope(invoice="11"),
            envelope(arguments=[]), envelope(arguments={}), envelope(issuance_token="wrong"), envelope(confirmation=None)]
        for ids in [[True], [42, 42], [2**63], ["42"]]:
            row = envelope(); row["arguments"]["return_movement_ids"] = ids; invalid.append(row)
        row = envelope(); row["unexpected"] = "hidden"; invalid.append(row)
        for row in invalid:
            with self.subTest(row=row), self.view_context(), patch.object(issuance, "issue_material_return_note") as issue:
                self.assertFalse(sessions.valid(row))
                self.assertEqual(views.issue(self.request(row), 11).status_code, 409)
                issue.assert_not_called()

    def test_wrong_actor_invoice_and_handle_cannot_be_replayed(self):
        for row in [envelope(actor=8), envelope(invoice=12)]:
            with self.view_context(), patch.object(issuance, "issue_material_return_note") as issue:
                self.assertEqual(views.issue(self.request(row), 11).status_code, 409); issue.assert_not_called()
        with self.assertRaises(ValidationError): sessions.load(self.request(), 11, "../bad")

    def test_bounded_storage_eviction_and_unchanged_session_timeout(self):
        request = self.request(); request.session = {}
        for i in range(33):
            entry = envelope()
            handle = sessions.store(request, 11, entry, entry["arguments"])
            if i == 0: first = handle
        self.assertEqual(len(request.session[sessions.SESSION_KEY]), 32)
        with self.assertRaises(ValidationError): sessions.load(request, 11, first)
        self.assertEqual(settings.SESSION_COOKIE_AGE, 900)

    def test_whole_session_write_conflict_fails_closed_without_guaranteed_tab_persistence(self):
        # Explicit simulation of competing session snapshots, not a DB race test.
        one = self.request(); one.session = {}
        two = self.request(); two.session = deepcopy(one.session)
        a = sessions.store(one, 11, envelope(), envelope()["arguments"])
        sessions.store(two, 11, envelope(), envelope()["arguments"])
        one.session = deepcopy(two.session)  # last writer wins
        with self.assertRaises(ValidationError): sessions.load(one, 11, a)

    def test_pdf_transient_and_nontransient_categories_are_conservative(self):
        transport = OperationalError("private")
        transport.__cause__ = RuntimeError("private"); transport.__cause__.pgcode = "08006"
        for error, expected in [(transport, "pdf_transient"), (OperationalError("private"), "pdf_review_required"),
                                (IntegrityError("private"), "pdf_review_required"),
                                (PermissionError("private"), "pdf_review_required")]:
            with patch.object(documents, "_generate_pdf", side_effect=error), self.assertRaises(ValidationError) as captured:
                documents.generate_pdf(9, self.user, language="fr")
            self.assertEqual(category(captured.exception), expected)
            self.assertNotIn("private", str(captured.exception).lower().replace("private storage", ""))

    def test_pdf_error_preserves_note_language_and_retry_never_calls_issue(self):
        note = SimpleNamespace(pk=9, invoice=SimpleNamespace(request_id=21))
        with patch.object(access, "ui_enabled", return_value=True), patch.object(issuance, "get_material_return_note", return_value=note), \
             patch.object(views, "authorize_return_note"), patch.object(views, "generate_pdf",
                 side_effect=[documents.pdf_error(transient=True), SimpleNamespace(pk=3)]) as generate, \
             patch.object(issuance, "issue_material_return_note") as issue, \
             patch.object(views, "active_language", return_value="fr"), \
             patch.object(views, "download_pdf", return_value=(None, __import__("io").BytesIO(b"%PDF-synthetic"))):
            response = views.pdf(self.request(), 9, "fr")
            retry = views.pdf(self.request(), 9, "fr")
        body = response.content.decode()
        self.assertIn("Return to issued note", body); self.assertIn("Retry PDF", body)
        self.assertIn("/return-notes/9/pdf/fr/", body)
        self.assertNotIn("/return-notes/issue/", body); issue.assert_not_called()
        self.assertEqual(retry.status_code, 200)
        self.assertIn(b"data-pdf-frame", retry.content)
        self.assertEqual(generate.call_args_list[0], generate.call_args_list[1])
        generate.assert_called_with(9, self.user, language="fr")

    def test_nontransient_pdf_failure_offers_admin_review_not_blind_retry(self):
        note = SimpleNamespace(pk=9, invoice=SimpleNamespace(request_id=21))
        with patch.object(access, "ui_enabled", return_value=True), patch.object(issuance, "get_material_return_note", return_value=note), \
             patch.object(views, "authorize_return_note"), patch.object(views, "generate_pdf", side_effect=documents.pdf_error()):
            body = views.pdf(self.request(), 9, "en").content.decode()
        self.assertIn("Return to issued note", body); self.assertNotIn("Retry PDF", body)

    def test_download_failure_retains_authorized_owner_and_language(self):
        note = SimpleNamespace(pk=9, invoice=SimpleNamespace(request_id=21))
        request = self.request(); request.method = "GET"
        with patch.object(access, "ui_enabled", return_value=True), patch.object(issuance, "get_material_return_note", return_value=note), \
             patch.object(views.MaterialReturnNoteArtifact.objects, "get", return_value=SimpleNamespace(note_id=9, language="en")), \
             patch.object(views, "authorize_return_note"), patch.object(views, "download_pdf", side_effect=documents.pdf_error(transient=True)):
            body = views.download(request, 3).content.decode()
        self.assertIn("/return-notes/9/pdf/en/", body)

    def test_pdf_permission_denied_before_generation_and_gate_stays_off(self):
        note = SimpleNamespace(pk=9, invoice=SimpleNamespace(request_id=21))
        with patch.object(access, "ui_enabled", return_value=True), patch.object(issuance, "get_material_return_note", return_value=note), \
             patch.object(views, "authorize_return_note", side_effect=PermissionDenied), patch.object(views, "generate_pdf") as generate:
            with self.assertRaises(PermissionDenied): views.pdf(self.request(), 9, "en")
            generate.assert_not_called()
        self.assertFalse(access.ui_enabled())

    def test_missing_facture_explanation_is_gated_and_permission_scoped(self):
        with patch.object(access, "ui_enabled", return_value=True), patch.object(access, "authorize_return_note"), \
             patch.object(access.Invoice.objects, "filter", return_value=Mock(first=Mock(return_value=None))):
            result = access.navigation(self.user, request_id=21)
        self.assertEqual(result, {"unavailable": True})
        with patch.object(access, "ui_enabled", return_value=True), patch.object(access, "authorize_return_note", side_effect=PermissionDenied):
            self.assertEqual(access.navigation(self.user, request_id=21), {})

    def test_history_displays_immutable_movements_business_time_and_timezone(self):
        note = SimpleNamespace(pk=9, number="BR-SYN", business_timezone="Africa/Kinshasa",
            finalized_at=datetime(2026,10,27,12,30,tzinfo=timezone.utc), total=Decimal("2"), currency="USD")
        lines = [{"return_movement_id": 42+i, "quantity": Decimal("1"), "unit_snapshot": "pcs"} for i in range(7)]
        note.lines = Mock(order_by=Mock(return_value=Mock(values=Mock(return_value=lines))))
        self.invoice.material_return_notes = Mock(filter=Mock(return_value=Mock(order_by=Mock(return_value=Mock(values_list=Mock(return_value=[9]))))))
        request = self.request(); request.method = "GET"
        with self.view_context(), patch.object(views, "navigation", return_value={}), patch.object(issuance, "get_material_return_note", return_value=note):
            body = views.history(request, 11).content.decode()
        self.assertIn("13:30:00", body); self.assertIn("Africa/Kinshasa", body)
        self.assertEqual(note.return_movement_summary, lines[:5]); self.assertEqual(note.additional_movement_count, 2)

    def test_prefinalization_explanation_changes_display_only_not_eligibility(self):
        moment = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
        self.invoice.finalized_at = moment; self.invoice.business_timezone = "Africa/Kinshasa"
        self.invoice.lines = SimpleNamespace(all=lambda: [SimpleNamespace(material_id=3)])
        row = {"return_movement_id": 42, "eligible": False, "reason": "Original service reason"}
        movement = SimpleNamespace(pk=42, material_id=3, created_at=moment)
        with patch.object(issuance, "eligible_return_movements", return_value=[row]), \
             patch.object(views.StockMovement.objects, "filter", return_value=Mock(order_by=Mock(return_value=[movement]))), \
             patch.object(views.DocumentSequence.objects, "filter", return_value=Mock(order_by=Mock(return_value=[]))), \
             patch.object(issuance, "database_now", return_value=moment):
            result = views._selection(self.invoice, self.user)
        self.assertFalse(result["rows"][0]["eligible"])
        self.assertIn("predates or coincides", result["rows"][0]["reason"])
        self.assertFalse(result["has_eligible"])

    def test_material_report_contains_gated_optional_links_without_stock_post_changes(self):
        report = Path(__file__).resolve().parents[1] / "templates/requests_app/material_reports.html"
        source = report.read_text(encoding="utf-8")
        self.assertIn("return_note_nav=req.report_return_note_nav", source)
        self.assertIn("{% url 'return_material_to_stock' item.id %}", source)
        # No nested issuance POST inside the existing bulk-print form.
        links = Path(__file__).resolve().parents[1] / "templates/invoicing/return_notes/links.html"
        self.assertNotIn("<form", links.read_text(encoding="utf-8"))

    def test_recovery_buttons_and_messages_work_in_french(self):
        with override("fr"), self.view_context(), patch.object(issuance, "issue_material_return_note", side_effect=issuance._unsafe()):
            body = views.issue(self.request(), 11).content.decode()
        self.assertIn("Réessayer avec la même confirmation", body)
        self.assertNotIn("PRIVATE-SIGNATURE", body)

    def test_read_only_orphan_inventory_preserves_files_and_marks_non_atomic_snapshot(self):
        root = settings.RETURN_NOTE_OFFLINE_EVIDENCE_ROOT / ("orphan-check-" + uuid4().hex)
        root.mkdir()
        names = ["a"*32+".pdf", "b"*32+".pdf", "c"*32+".pdf"]
        for name in names: (root/name).write_bytes(b"%PDF-synthetic")
        before = {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in root.iterdir()}
        report = inspect_private_files(root, [{"file_reference": names[0], "rendering_status": "READY"},
            {"file_reference": names[1], "rendering_status": "FAILED"}, {"file_reference": "d"*32+".pdf", "rendering_status": "READY"}])
        self.assertEqual(report["provisional_unreferenced"], [names[2]])
        self.assertEqual(report["failed_references"], [names[1]])
        self.assertFalse(report["atomic_snapshot"]); self.assertEqual(report["actions_performed"], [])
        self.assertEqual(before, {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in root.iterdir()})
        with self.assertRaises(ValueError): inspect_private_files(Path("relative"), [])

    def test_render_failures_remain_append_only_and_classified(self):
        fixture = document_tests.ReturnNoteDocumentTests(); fixture.setUp()
        for failure, expected in [(ValueError("secret render detail"), "pdf_review_required"),
                                  (BlockingIOError(errno.EAGAIN, "secret temporary detail"), "pdf_transient")]:
            stack, _, _, create, _ = fixture.pipeline(failure=failure)
            with stack, self.assertRaises(ValidationError) as captured:
                documents.generate_pdf(9, self.user, language="en")
            self.assertEqual(category(captured.exception), expected)
            self.assertEqual(create.call_args.kwargs["rendering_status"], "FAILED")
            self.assertNotIn("secret", str(captured.exception))
