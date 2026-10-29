"""Phase A tests with mocked persistence; run via the offline-only runner."""
import ast
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

from django.core.checks import run_checks, Tags
from django.core.exceptions import ValidationError, PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import QueryDict
from django.test import RequestFactory, override_settings
from django.utils.datastructures import MultiValueDict
from django.utils.translation import override, gettext

from invoicing.configuration import business_date
from . import references as refs
from .models import Request, RequestType


class ReferenceOfflineTests(unittest.TestCase):
    def kind(self, code="MATERIAL", namespace=None):
        return SimpleNamespace(pk=3, code=code, reference_namespace=namespace, save=Mock())

    def test_approved_namespaces_and_display_name_independence(self):
        self.assertEqual(refs.namespace_for(self.kind()), "MAT")
        self.assertEqual(refs.namespace_for(self.kind("AUTORISATION_GENERAL")), "ADM")
        kind = self.kind("SITE_AUTHORIZATION")
        first = refs.namespace_for(kind)
        kind.reference_namespace = first
        kind.code = "RENAMED_CODE"; kind.name = "Renamed display"
        self.assertEqual(refs.namespace_for(kind), first)

    def test_other_namespace_is_stable_and_bounded(self):
        kind = self.kind("VERY_LONG_REQUEST_TYPE_CONFIGURATION")
        value = refs.namespace_for(kind)
        self.assertEqual(value, refs.namespace_for(kind))
        self.assertEqual(len(value), 16)
        self.assertRegex(value, r"^[A-Z][A-Z0-9]+$")

    def test_invalid_and_reserved_namespaces_fail_closed(self):
        for code in ("---", "123", "ADM", "MAT"):
            with self.assertRaises(ValidationError):
                refs.namespace_for(self.kind(code))

    def test_format_padding_and_bigint_limit(self):
        self.assertEqual(refs.format_reference("ADM", 2027, 1), "REQ-ADM-0001/2027")
        self.assertEqual(refs.format_reference("MAT", 2027, 10000), "REQ-MAT-10000/2027")
        self.assertLessEqual(len(refs.format_reference("A" * 16, 9999, refs.MAX_COUNTER)), 50)
        for year, counter in [(0, 1), (10000, 1), (2027, 0), (2027, refs.MAX_COUNTER + 1)]:
            with self.assertRaises(ValidationError):
                refs.format_reference("MAT", year, counter)

    def test_kinshasa_year_boundary(self):
        self.assertEqual(business_date(datetime(2026, 12, 31, 22, 59, 59, tzinfo=timezone.utc), "Africa/Kinshasa").year, 2026)
        self.assertEqual(business_date(datetime(2026, 12, 31, 23, tzinfo=timezone.utc), "Africa/Kinshasa").year, 2027)

    def test_payload_digest_excludes_transport_tokens_only(self):
        post = QueryDict("description=Original&request_type=3&submission_token=a&csrfmiddlewaretoken=x")
        digest = refs.creation_digest(post, MultiValueDict())
        other = post.copy(); other["csrfmiddlewaretoken"] = "new"; other["submission_token"] = "new"
        self.assertEqual(digest, refs.creation_digest(other, MultiValueDict()))
        other["description"] = "Changed"
        self.assertNotEqual(digest, refs.creation_digest(other, MultiValueDict()))

    def test_upload_digest_binds_bytes_and_restores_position(self):
        upload = SimpleUploadedFile("evidence.txt", b"original bytes", "text/plain")
        upload.seek(3)
        original = refs.creation_digest(QueryDict(), MultiValueDict({"attachments": [upload]}))
        self.assertEqual(upload.tell(), 3)
        changed = SimpleUploadedFile("evidence.txt", b"different text", "text/plain")
        self.assertNotEqual(original, refs.creation_digest(QueryDict(), MultiValueDict({"attachments": [changed]})))

    def test_committed_replay_and_conflicting_replay(self):
        actor = SimpleNamespace(pk=5)
        request = SimpleNamespace(pk=7, request_number="REQ-MAT-0001/2027")
        receipt = SimpleNamespace(actor_id=5, payload_digest="a" * 64, request_id=7, request=request)
        with patch.object(refs.RequestCreationReceipt, "objects") as manager:
            manager.select_related.return_value.filter.return_value.first.return_value = receipt
            self.assertIs(refs.committed_creation(uuid4(), actor, "a" * 64), request)
            for bad_actor, digest in [(actor, "b" * 64), (SimpleNamespace(pk=6), "a" * 64)]:
                with self.assertRaises(ValidationError):
                    refs.committed_creation(uuid4(), bad_actor, digest)

    def test_invalid_token_rejected_before_persistence(self):
        with patch.object(refs.RequestCreationReceipt, "objects") as manager:
            with self.assertRaises(ValidationError):
                refs.committed_creation("invalid", SimpleNamespace(pk=5), "a" * 64)
            manager.select_related.assert_not_called()

    def test_replay_skips_all_creation_side_effects(self):
        actor = SimpleNamespace(pk=5)
        request = SimpleNamespace(pk=7)
        receipt = SimpleNamespace(actor_id=5, payload_digest="a" * 64, request_id=7, request=request)
        related = Mock(); files = Mock()
        with patch.object(refs.RequestCreationReceipt, "objects") as manager, patch.object(refs, "_allocate") as allocation:
            manager.get_or_create.return_value = (receipt, False)
            manager.select_for_update.return_value.select_related.return_value.get.return_value = receipt
            result, replay = refs.create_request_once.__wrapped__(Mock(), actor, token=uuid4(), digest="a" * 64,
                save_related=related, submit=True, save_files=files)
        self.assertIs(result, request); self.assertTrue(replay)
        allocation.assert_not_called(); related.assert_not_called(); files.assert_not_called()

    def test_atomic_body_order_and_metadata(self):
        actor = SimpleNamespace(pk=5, is_active=True, department_id=2)
        request = Request(request_type_id=3, submitted_by_id=5, department_id=2)
        receipt = SimpleNamespace(actor_id=5, payload_digest="a" * 64, request_id=None, save=Mock())
        moment = datetime(2027, 1, 1, tzinfo=timezone.utc)
        order = []
        with patch.object(refs.RequestCreationReceipt, "objects") as receipts, \
                patch.object(refs.RequestType, "objects") as kinds, \
                patch.object(refs, "_allocate", return_value=("MAT", 2027, 1, moment)), \
                patch.object(request, "save", side_effect=lambda: order.append("request")), \
                patch("requests_app.services.submit_request", side_effect=lambda *a, **k: order.append("workflow")):
            receipts.get_or_create.return_value = (receipt, True)
            receipts.select_for_update.return_value.select_related.return_value.get.return_value = receipt
            saved, replay = refs.create_request_once.__wrapped__(request, actor, token=uuid4(), digest="a" * 64,
                save_related=lambda req: order.append("lines"), submit=True, save_files=lambda req: order.append("files"))
        self.assertFalse(replay); self.assertIs(saved, request)
        self.assertEqual(order, ["request", "lines", "workflow", "files"])
        self.assertEqual(request.request_number, "REQ-MAT-0001/2027")
        self.assertEqual(request.reference_allocated_at, moment)
        self.assertEqual(request.reference_year, 2027)
        receipt.save.assert_called_once_with(update_fields=["request"])

    def test_allocator_sql_is_atomic_and_uses_database_kinshasa_time(self):
        kind = self.kind(namespace="MAT")
        with patch.object(refs, "connection") as connection:
            connection.vendor = "postgresql"; connection.in_atomic_block = True
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (2027, 1, datetime(2027, 1, 1, tzinfo=timezone.utc))
            namespace, year, counter, _ = refs._allocate(kind)
            sql, parameters = cursor.execute.call_args.args
            self.assertIn("clock_timestamp()", sql)
            self.assertIn("AT TIME ZONE 'Africa/Kinshasa'", sql)
            self.assertIn("ON CONFLICT (request_type_id, year) DO UPDATE", sql)
            self.assertEqual(parameters, [kind.pk, refs.MAX_COUNTER])
            self.assertEqual((namespace, year, counter), ("MAT", 2027, 1))
            cursor.fetchone.return_value = None
            with self.assertRaises(ValidationError):
                refs._allocate(kind)

    def test_namespace_collision_is_reported_before_assignment(self):
        kind = self.kind()
        with patch.object(refs, "connection", vendor="postgresql", in_atomic_block=True), \
                patch.object(refs.RequestType, "objects") as manager:
            manager.exclude.return_value.filter.return_value.exists.return_value = True
            with self.assertRaises(ValidationError):
                refs._allocate(kind)
        kind.save.assert_not_called()

    def test_legacy_model_save_does_not_allocate(self):
        request = Request(pk=1, request_number="REQ-Q43DHY", department_id=1)
        request._state.adding = False
        with patch("django.db.models.Model.save"), patch.object(refs, "_allocate") as allocate:
            request.save()
        allocate.assert_not_called()
        self.assertEqual(request.request_number, "REQ-Q43DHY")
        self.assertIsNone(request.reference_year)

    def test_model_migration_state_matches_without_database(self):
        from django.apps import apps
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.state import ProjectState
        from django.db.migrations.autodetector import MigrationAutodetector
        loader = MigrationLoader(None)
        self.assertFalse(MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph))

    def test_creation_is_the_only_view_allocating_references(self):
        source = Path("requests_app/views.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        callers = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)
                   and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                           and call.func.id == "create_request_once" for call in ast.walk(node))]
        self.assertEqual(callers, ["create_request"])
        self.assertNotIn("get_random_string", source)

    def test_english_french_validation(self):
        message = "Invalid request creation confirmation."
        with override("en"):
            self.assertEqual(gettext(message), message)
        with override("fr"):
            self.assertNotEqual(gettext(message), message)

    def test_database_free_system_checks(self):
        # App/model checks only: no database aliases are supplied.
        errors = run_checks(tags=[Tags.models], databases=[])
        self.assertFalse([error for error in errors if error.is_serious()], errors)

    def test_http_exact_replay_does_not_revalidate_or_create(self):
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4()), "action": "save_draft"})
        request.user = SimpleNamespace(pk=5, department=SimpleNamespace(pk=2), is_authenticated=True)
        request.session = {}  # Lost/overwritten session entry is recoverable from the receipt.
        with patch.object(views, "committed_creation", return_value=SimpleNamespace(pk=7)), \
                patch.object(views.messages, "info"), patch.object(views, "RequestForm") as form, \
                patch.object(views, "create_request_once") as create:
            response = views.create_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/requests/7/", response.url)
        form.assert_not_called(); create.assert_not_called()

    def test_http_conflicting_replay_is_rejected_before_creation(self):
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4())})
        request.user = SimpleNamespace(pk=5, department=SimpleNamespace(pk=2), is_authenticated=True)
        request.session = {}
        with patch.object(views, "committed_creation", side_effect=ValidationError("Synthetic conflict")), \
                patch.object(views.messages, "error"), patch.object(views, "create_request_once") as create:
            response = views.create_request(request)
        self.assertEqual(response.status_code, 302)
        create.assert_not_called()

    def test_expired_uncommitted_form_cannot_create(self):
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4())})
        request.user = SimpleNamespace(pk=5, department=SimpleNamespace(pk=2), is_authenticated=True)
        request.session = {}
        with patch.object(views, "committed_creation", return_value=None), \
                patch.object(views.messages, "error"), patch.object(views, "create_request_once") as create:
            response = views.create_request(request)
        self.assertEqual(response.status_code, 302)
        create.assert_not_called()

    def test_migration_has_no_data_rewrite_or_financial_operations(self):
        import importlib
        from django.db import migrations
        module = importlib.import_module("requests_app.migrations.0018_ordinary_request_references")
        migration = module.Migration
        self.assertIs(migration.operations[-1].reverse_code, module.require_unused_reversal)
        self.assertIs(migration.operations[-2].code, module.install_reference_guards)
        sql = module.REFERENCE_GUARDS
        self.assertNotIn("invoicing_", sql)
        self.assertNotIn("stockmovement", sql)
        self.assertNotIn("UPDATE requests_app_request SET", sql)
        self.assertIn("Stored request reference is immutable", sql)

    def test_explicit_reserved_overrides_are_rejected(self):
        for code, namespace in [("MATERIAL", "OTHER"), ("AUTORISATION_GENERAL", "MAT"),
                                ("OTHER", "ADM"), ("OTHER", "MAT")]:
            with self.subTest(code=code, namespace=namespace), self.assertRaises(ValidationError):
                refs.namespace_for(self.kind(code, namespace))
        self.assertEqual(refs.namespace_for(self.kind("MATERIAL", "MAT")), "MAT")
        self.assertEqual(refs.namespace_for(self.kind("AUTORISATION_GENERAL", "ADM")), "ADM")

    @override_settings(ADMINISTRATION_REPORT_REQUEST_TYPE_CODE="CUSTOM_ADMIN")
    def test_configured_canonical_administration_owner(self):
        self.assertEqual(refs.namespace_for(self.kind("CUSTOM_ADMIN", "ADM")), "ADM")
        with self.assertRaises(ValidationError):
            refs.namespace_for(self.kind("AUTORISATION_GENERAL", "ADM"))

    @override_settings(ADMINISTRATION_REPORT_REQUEST_TYPE_CODE="MATERIAL")
    def test_ambiguous_configuration_is_rejected(self):
        with self.assertRaises(ValidationError):
            refs.namespace_for(self.kind("MATERIAL"))

    def test_model_validation_enforces_ownership_and_immutability(self):
        kind = RequestType(code="OTHER", name="Other", reference_namespace="MAT")
        with self.assertRaises(ValidationError):
            kind.full_clean(validate_unique=False, validate_constraints=False)
        kind = RequestType(pk=1, code="OTHER", name="Other", reference_namespace="CHANGED")
        kind._state.adding = False
        with patch.object(RequestType, "objects") as manager:
            manager.filter.return_value.values_list.return_value.first.return_value = "ORIGINAL"
            with self.assertRaises(ValidationError):
                kind.clean()

    def test_admin_add_denied_existing_permissions_retained(self):
        from django.contrib.admin import AdminSite
        from .admin import RequestAdmin
        admin = RequestAdmin(Request, AdminSite())
        request = RequestFactory().get("/admin/requests_app/request/add/")
        request.user = Mock(is_active=True, is_staff=True)
        request.user.has_perm.return_value = True
        self.assertFalse(admin.has_add_permission(request))
        self.assertTrue(admin.has_view_permission(request))
        self.assertTrue(admin.has_change_permission(request))
        with self.assertRaises(PermissionDenied):
            admin.add_view(request)

    def test_recovery_database_error_retains_submission_and_sanitizes(self):
        from django.db import OperationalError
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4())})
        request.user = SimpleNamespace(pk=5, department=None, is_authenticated=True)
        request.session = {}
        with patch.object(views, "committed_creation", side_effect=OperationalError("SECRET connection details")), \
                patch.object(views, "create_request_once") as create, patch.object(views, "issue_submission_token") as issue:
            response = views.create_request(request)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"SECRET", response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        create.assert_not_called(); issue.assert_not_called()

    def test_replay_survives_removed_department(self):
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4())})
        request.user = SimpleNamespace(pk=5, department=None, is_authenticated=True)
        request.session = {}
        with patch.object(views, "committed_creation", return_value=SimpleNamespace(pk=7)), patch.object(views.messages, "info"):
            response = views.create_request(request)
        self.assertIn("/requests/7/", response.url)

    def test_reversal_preflight_locks_and_allows_only_unused_state(self):
        import importlib
        from django.db.migrations.exceptions import IrreversibleError
        module = importlib.import_module("requests_app.migrations.0018_ordinary_request_references")
        for used_index in (None, 0, 1, 2):
            models = [Mock() for _ in range(3)]
            for index, model in enumerate(models):
                model.objects.using.return_value.exists.return_value = index == used_index
                model.objects.using.return_value.filter.return_value.exists.return_value = index == used_index
            apps = Mock(); apps.get_model.side_effect = models
            editor = MagicMock(); editor.connection.vendor = "postgresql"; editor.connection.in_atomic_block = True
            if used_index is None:
                module.require_unused_reversal(apps, editor)
            else:
                with self.assertRaises(IrreversibleError):
                    module.require_unused_reversal(apps, editor)
            sql = editor.connection.cursor.return_value.__enter__.return_value.execute.call_args.args[0]
            self.assertIn("ACCESS EXCLUSIVE", sql)
            editor.execute.assert_not_called()  # Preflight never drops or rewrites anything.

    def test_guard_installation_quotes_and_freezes_canonical_policy(self):
        import importlib
        module = importlib.import_module("requests_app.migrations.0018_ordinary_request_references")
        editor = Mock(); editor.quote_value.return_value = "'AUTORISATION_GENERAL'"
        module.install_reference_guards(Mock(), editor)
        sql = editor.execute.call_args.args[0]
        self.assertNotIn("__ADMIN_CODE_LITERAL__", sql)
        self.assertIn("BEFORE INSERT OR UPDATE ON requests_app_requesttype", sql)
        self.assertIn("Canonical request namespace ownership", sql)

    def test_reversal_refuses_non_atomic_invocation_before_locks(self):
        import importlib
        from django.db.migrations.exceptions import IrreversibleError
        module = importlib.import_module("requests_app.migrations.0018_ordinary_request_references")
        editor = Mock(); editor.connection.vendor = "postgresql"; editor.connection.in_atomic_block = False
        with self.assertRaises(IrreversibleError):
            module.require_unused_reversal(Mock(), editor)
        editor.connection.cursor.assert_not_called()

    def test_storage_error_has_sanitized_same_form_recovery(self):
        from . import views
        request = RequestFactory().post("/requests/create/", {"submission_token": str(uuid4()), "action": "save_draft"})
        request.user = SimpleNamespace(pk=5, department=SimpleNamespace(pk=2), is_authenticated=True)
        request.session = {}
        instance = SimpleNamespace(request_type=SimpleNamespace(requires_materials=False))
        with patch.object(views, "submission_token_result", return_value=("pending", None, request.POST["submission_token"])), \
                patch.object(views, "committed_creation", return_value=None), \
                patch.object(views, "RequestForm") as form, patch.object(views, "RequestMaterialItemFormSet"), \
                patch.object(views, "build_permission_metadata", return_value={}), \
                patch.object(views, "request_form_context", return_value={"submission_token": request.POST["submission_token"]}), \
                patch.object(views, "create_request_once", side_effect=OSError("SECRET file details")), \
                patch.object(views, "render") as render, patch.object(views, "mark_submission_token_used") as used:
            form.return_value.is_valid.return_value = True
            form.return_value.save.return_value = instance
            views.create_request(request)
        self.assertEqual(render.call_args.kwargs["status"], 503)
        self.assertEqual(render.call_args.args[2]["submission_token"], request.POST["submission_token"])
        self.assertNotIn("SECRET", str(form.return_value.add_error.call_args))
        used.assert_not_called()
