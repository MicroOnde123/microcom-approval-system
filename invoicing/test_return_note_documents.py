"""Mocked artifact transactions and private synthetic files; no database I/O."""
from contextlib import ExitStack, nullcontext
from datetime import date
from decimal import Decimal
import hashlib
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError
from . import return_note_access as access, return_note_documents as documents
from .permissions import authorize_return_note
from .test_return_note_pdf import snapshot, ROOT


def issued_note():
    source = snapshot()
    line = SimpleNamespace(return_movement_id=42, material_code_snapshot="SYN-CABLE",
        description_snapshot=source["lines"][0]["description"], unit_snapshot="pcs", quantity=Decimal("1"),
        unit_price_snapshot=Decimal("2"), line_total=Decimal("2"))
    original = {**source["original"], "version": 1, "currency": "USD", "request_reference": source["request_reference"]}
    return SimpleNamespace(pk=9, invoice_id=11, invoice=SimpleNamespace(request_id=21), status="FINALIZED",
        snapshot_version=1, rounding_policy="RETURN_CUMULATIVE_HALF_UP_2_V1", number=source["number"],
        issue_date=date(2026, 10, 27), currency="USD", company_snapshot=source["company"],
        succursale_snapshot=source["branch"], branding_snapshot=source["branding"], original_invoice_snapshot=original,
        request_reference_snapshot=source["request_reference"], total=Decimal("2.00"),
        cumulative_returned_value=Decimal("2.00"), adjusted_net_value=Decimal("4.00"),
        amount_words_fr=source["amount_words_fr"], operation=SimpleNamespace(reason=source["reason"]),
        lines=SimpleNamespace(order_by=lambda *args: [line]))


class ReturnNoteDocumentTests(unittest.TestCase):
    def setUp(self):
        root = getattr(settings, "RETURN_NOTE_OFFLINE_EVIDENCE_ROOT", ROOT / "local_artifacts/checkpoint_er3_evidence")
        root.mkdir(exist_ok=True)
        # Path.mkdir inherits the workspace ACL. Python's Windows mkdtemp uses
        # a restrictive 0700 ACL incompatible with this restricted test token.
        # Never alter an existing directory's permissions to make a test pass.
        self.root = root / ("private-files-" + uuid4().hex)
        self.root.mkdir()
        self.note = issued_note(); self.user = SimpleNamespace(pk=7, is_authenticated=True)

    def pipeline(self, *, existing=None, content=b"%PDF-synthetic", failure=None):
        stack = ExitStack()
        stack.enter_context(patch.object(access, "ui_enabled", return_value=True))
        stack.enter_context(patch.object(documents, "connection", SimpleNamespace(in_atomic_block=False, get_autocommit=lambda: True)))
        stack.enter_context(patch.object(documents.transaction, "atomic", side_effect=lambda **kwargs: nullcontext()))
        retrieve = stack.enter_context(patch.object(documents, "get_material_return_note", return_value=self.note))
        authorize = stack.enter_context(patch.object(documents, "authorize_return_note", return_value=self.user))
        stack.enter_context(patch.object(documents.MaterialReturnNote.objects, "select_for_update", return_value=Mock(get=Mock(return_value=self.note))))
        stack.enter_context(patch.object(documents.MaterialReturnNoteArtifact.objects, "filter", return_value=Mock(order_by=Mock(return_value=existing or []))))
        create = stack.enter_context(patch.object(documents.MaterialReturnNoteArtifact.objects, "create",
            side_effect=lambda **fields: SimpleNamespace(pk=5, note_id=9, **fields)))
        renderer = stack.enter_context(patch.object(documents, "render_pdf", return_value=content, side_effect=failure))
        stack.enter_context(patch.object(documents, "_private_root", return_value=self.root))
        return stack, retrieve, authorize, create, renderer

    def test_detached_snapshot_uses_only_frozen_fields(self):
        result = documents._snapshot(self.note)
        self.assertEqual(result["original"]["number"], self.note.original_invoice_snapshot["number"])
        self.assertEqual(result["lines"][0]["price"], "2.0000")
        result["company"]["company_name"] = "changed presentation"
        self.assertNotEqual(result["company"], self.note.company_snapshot)

    def test_incomplete_or_nonfinal_snapshots_fail_closed(self):
        for field, value in [("status", "DRAFT"), ("company_snapshot", {}), ("original_invoice_snapshot", {}), ("total", None)]:
            note = issued_note(); setattr(note, field, value)
            with self.subTest(field=field), self.assertRaises(ValidationError): documents._snapshot(note)

    def test_artifact_owner_checksum_language_and_document_permission(self):
        stack, retrieve, authorize, create, renderer = self.pipeline()
        with stack:
            artifact = documents.generate_pdf(9, self.user, language="fr")
            self.assertEqual(documents._artifact_bytes(artifact), b"%PDF-synthetic")
        self.assertEqual(artifact.note.pk, 9); self.assertEqual(artifact.language, "fr")
        self.assertEqual(artifact.rendering_status, "READY")
        self.assertEqual(artifact.checksum, hashlib.sha256(b"%PDF-synthetic").hexdigest())
        authorize.assert_called_with(self.user, 21, document=True)
        self.assertEqual(retrieve.call_count, 2); create.assert_called_once(); renderer.assert_called_once()

    def test_good_cached_pdf_reused_without_new_attempt(self):
        filename = "a" * 32 + ".pdf"; folder = self.root / "return-notes"; folder.mkdir()
        content = b"%PDF-cache"; (folder / filename).write_bytes(content)
        artifact = SimpleNamespace(file_reference=filename, rendering_status="READY", checksum=hashlib.sha256(content).hexdigest())
        stack, _, _, create, renderer = self.pipeline(existing=[artifact])
        with stack: self.assertIs(documents.generate_pdf(9, self.user, language="en"), artifact)
        create.assert_not_called(); renderer.assert_not_called()

    def test_corrupt_cached_artifact_creates_new_attempt(self):
        bad = SimpleNamespace(file_reference="b" * 32 + ".pdf", rendering_status="READY", checksum="wrong")
        stack, _, _, create, _ = self.pipeline(existing=[bad])
        with stack: self.assertEqual(documents.generate_pdf(9, self.user, language="en").rendering_status, "READY")
        create.assert_called_once()

    def test_failed_render_is_append_only_failed_attempt_without_exception_details(self):
        stack, _, _, create, _ = self.pipeline(failure=ValueError("SECRET internal/path"))
        with stack, self.assertRaises(ValidationError) as error: documents.generate_pdf(9, self.user, language="en")
        self.assertNotIn("SECRET", str(error.exception))
        self.assertEqual(create.call_args.kwargs["rendering_status"], "FAILED")

    def test_path_traversal_failed_status_checksum_and_nonpdf_block_download(self):
        with patch.object(documents, "_private_root", return_value=self.root):
            for reference in ["../invoice.pdf", "file.pdf", "C:/secret.pdf", None]:
                with self.assertRaises(ValidationError): documents._path(reference)
            folder = self.root / "return-notes"; folder.mkdir()
            path = folder / ("c" * 32 + ".pdf"); path.write_bytes(b"not PDF")
            for status, checksum in [("FAILED", "wrong"), ("READY", hashlib.sha256(b"not PDF").hexdigest())]:
                artifact = SimpleNamespace(file_reference=path.name, rendering_status=status, checksum=checksum)
                with self.assertRaises(ValidationError): documents._artifact_bytes(artifact)

    def test_download_checks_document_permission_before_opening_file(self):
        artifact = SimpleNamespace(note_id=9)
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(documents.MaterialReturnNoteArtifact.objects, "get", return_value=artifact), \
             patch.object(documents, "get_material_return_note", return_value=self.note), \
             patch.object(documents, "authorize_return_note", side_effect=PermissionDenied), \
             patch.object(documents, "_artifact_bytes") as read:
            with self.assertRaises(PermissionDenied): documents.download_pdf(1, self.user)
            read.assert_not_called()

    def test_explicit_document_permission_is_additional_to_existing_view_permissions(self):
        actor = SimpleNamespace(is_active=True, is_staff=True, has_perm=Mock(side_effect=lambda permission: not permission.endswith("view_materialreturnnote_document")))
        model = Mock(objects=Mock(filter=Mock(return_value=Mock(first=Mock(return_value=actor)))))
        scope = Mock(filter=Mock(return_value=Mock(exists=Mock(return_value=True))))
        with patch("django.contrib.auth.get_user_model", return_value=model), patch("invoicing.permissions.request_scope", return_value=scope):
            self.assertIs(authorize_return_note(self.user, 21), actor)
            with self.assertRaises(PermissionDenied): authorize_return_note(self.user, 21, document=True)
        self.assertIn(("invoicing.view_materialreturnnote_document",), [call.args for call in actor.has_perm.call_args_list])

    def test_generation_rejects_ambient_transaction_before_retrieval(self):
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(documents, "connection", SimpleNamespace(in_atomic_block=True)), \
             patch.object(documents, "get_material_return_note") as retrieve:
            with self.assertRaises(ValidationError): documents.generate_pdf(9, self.user, language="en")
            retrieve.assert_not_called()

    def test_database_failure_is_sanitized_without_disclosing_internal_details(self):
        with patch.object(access, "ui_enabled", return_value=True), \
             patch.object(documents.MaterialReturnNoteArtifact.objects, "get", side_effect=DatabaseError("SECRET query/path")):
            with self.assertRaises(ValidationError) as error: documents.download_pdf(1, self.user)
        self.assertNotIn("SECRET", str(error.exception))
        with patch.object(documents, "_generate_pdf", side_effect=DatabaseError("SECRET query/path")):
            with self.assertRaises(ValidationError) as error: documents.generate_pdf(9, self.user, language="en")
        self.assertNotIn("SECRET", str(error.exception))
