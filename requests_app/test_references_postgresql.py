"""DEFERRED: run only on an explicitly verified isolated disposable PostgreSQL DB.

Never run this module against the application's Supabase development database.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections, transaction, IntegrityError
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import Department
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep
from .models import Request, RequestType, RequestReferenceSequence, RequestCreationReceipt, RequestAuditLog, StockMovement
from .references import create_request_once, committed_creation, MAX_COUNTER


@contextmanager
def allocation_clock(moment):
    """Test-only clock substitution inside real PostgreSQL allocation SQL."""
    def execute(execute, sql, params, many, context):
        if "WITH instant AS MATERIALIZED (SELECT clock_timestamp()" in sql:
            sql = sql.replace("clock_timestamp()", "%s::timestamptz", 1)
            params = [moment, *params]
        return execute(sql, params, many, context)
    with connection.execute_wrapper(execute):
        yield


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RequestReferencePostgreSQLTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL required")
        self.department = Department.objects.create(code="REFTEST", name="Synthetic")
        self.actor = get_user_model().objects.create_user(username="reference-test", department=self.department)
        self.kind = RequestType.objects.create(code="MATERIAL", name="Synthetic material")
        self.moment = datetime(2026, 10, 28, tzinfo=timezone.utc)

    def instance(self, kind=None, actor=None):
        actor = actor or self.actor
        return Request(request_type=kind or self.kind, submitted_by=actor, department_id=actor.department_id,
                       request_for_department_id=actor.department_id, description="Synthetic", status="DRAFT")

    def create(self, token=None, digest="a" * 64, kind=None, related=None, submit=False):
        return create_request_once(self.instance(kind), self.actor, token=token or uuid4(), digest=digest,
                                   save_related=related or (lambda req: None), submit=submit)

    def test_first_use_rollover_and_independent_types(self):
        admin = RequestType.objects.create(code="AUTORISATION_GENERAL", name="Synthetic administration")
        with allocation_clock(datetime(2026, 12, 31, 22, 59, 59, tzinfo=timezone.utc)):
            first, _ = self.create()
        with allocation_clock(datetime(2026, 12, 31, 23, tzinfo=timezone.utc)):
            second, _ = self.create()
            other, _ = self.create(kind=admin)
        self.assertEqual(first.request_number, "REQ-MAT-0001/2026")
        self.assertEqual(second.request_number, "REQ-MAT-0001/2027")
        self.assertEqual(other.request_number, "REQ-ADM-0001/2027")
        self.assertEqual(RequestReferenceSequence.objects.count(), 3)

    def test_concurrent_first_use_allocates_unique_numbers(self):
        barrier = Barrier(4)
        def worker(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                kind = RequestType.objects.get(pk=self.kind.pk)
                barrier.wait(timeout=15)
                with allocation_clock(self.moment):
                    request, _ = create_request_once(self.instance(kind, actor), actor, token=uuid4(), digest="a" * 64,
                        save_related=lambda req: None, submit=False)
                return request.request_number
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=4) as pool:
            numbers = list(pool.map(worker, range(4)))
        self.assertEqual(set(numbers), {f"REQ-MAT-{counter:04d}/2026" for counter in range(1, 5)})
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 4)

    def test_concurrent_same_token_creates_once(self):
        barrier = Barrier(2); token = uuid4()
        def worker(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                kind = RequestType.objects.get(pk=self.kind.pk)
                barrier.wait(timeout=15)
                with allocation_clock(self.moment):
                    request, replay = create_request_once(self.instance(kind, actor), actor, token=token, digest="a" * 64,
                        save_related=lambda req: None, submit=False)
                return request.pk, replay
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(sum(replay for _, replay in results), 1)
        self.assertEqual(Request.objects.count(), 1)
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)

    def test_rollback_leaves_no_counter_namespace_receipt_or_request(self):
        token = uuid4()
        def fail(request):
            raise ValidationError("Synthetic failure")
        with allocation_clock(self.moment), self.assertRaises(ValidationError):
            self.create(token=token, related=fail)
        self.assertFalse(Request.objects.exists())
        self.assertFalse(RequestCreationReceipt.objects.exists())
        self.assertFalse(RequestReferenceSequence.objects.exists())
        self.kind.refresh_from_db()
        self.assertIsNone(self.kind.reference_namespace)
        with allocation_clock(self.moment):
            request, _ = self.create(token=token)
        self.assertEqual(request.reference_counter, 1)

    def test_exact_replay_conflict_and_actor_binding(self):
        token = uuid4()
        with allocation_clock(self.moment):
            first, _ = self.create(token)
            again, replay = self.create(token)
        self.assertEqual(first.pk, again.pk); self.assertTrue(replay)
        with self.assertRaises(ValidationError):
            self.create(token, digest="b" * 64)
        other = get_user_model().objects.create_user(username="other-reference-test", department=self.department)
        with self.assertRaises(ValidationError):
            committed_creation(token, other, "a" * 64)
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)

    def test_format_expansion_and_exhaustion(self):
        self.kind.reference_namespace = "MAT"; self.kind.save()
        sequence = RequestReferenceSequence.objects.create(request_type=self.kind, year=2026, last_counter=9999)
        with allocation_clock(self.moment):
            request, _ = self.create()
        self.assertEqual(request.request_number, "REQ-MAT-10000/2026")
        sequence.last_counter = MAX_COUNTER; sequence.save()
        with allocation_clock(self.moment), self.assertRaises(ValidationError):
            self.create()
        sequence.refresh_from_db(); self.assertEqual(sequence.last_counter, MAX_COUNTER)

    def test_frozen_namespace_and_legacy_reference_preservation(self):
        legacy = self.instance(); legacy.request_number = "REQ-Q43DHY"; legacy.save()
        with allocation_clock(self.moment):
            first, _ = self.create()
        self.kind.refresh_from_db()
        self.kind.name = "Renamed"; self.kind.save()
        with allocation_clock(self.moment):
            second, _ = self.create()
        self.assertEqual(second.request_number, "REQ-MAT-0002/2026")
        legacy.refresh_from_db(); self.assertEqual(legacy.request_number, "REQ-Q43DHY")
        self.assertIsNone(legacy.reference_counter)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Request.objects.filter(pk=first.pk).update(request_number="forbidden")
        with self.assertRaises(IntegrityError), transaction.atomic():
            RequestType.objects.filter(pk=self.kind.pk).update(reference_namespace="CHANGED")

    def test_reserved_ownership_cannot_be_overridden_in_sql(self):
        for code, namespace in [("OTHER", "ADM"), ("OTHER", "MAT"),
                                ("AUTORISATION_GENERAL", "OTHER"), ("CUSTOM", "MAT")]:
            with self.subTest(code=code, namespace=namespace), self.assertRaises(IntegrityError), transaction.atomic():
                RequestType.objects.create(code=code, name="Synthetic", reference_namespace=namespace)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RequestType.objects.filter(pk=self.kind.pk).update(reference_namespace="OTHER")
        with allocation_clock(self.moment):
            self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            RequestType.objects.filter(pk=self.kind.pk).update(code="RENAMED_CANONICAL")

    def test_derived_namespace_collision_rolls_back_without_consuming(self):
        first = RequestType.objects.create(code="A_B", name="First")
        second = RequestType.objects.create(code="AB", name="Second")
        with allocation_clock(self.moment):
            self.create(kind=first)
            with self.assertRaises(ValidationError):
                self.create(kind=second)
        self.assertFalse(RequestReferenceSequence.objects.filter(request_type=second).exists())
        second.refresh_from_db(); self.assertIsNone(second.reference_namespace)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RequestType.objects.filter(pk=first.pk).update(reference_namespace="REPLACED")

    def test_concurrent_derived_namespace_collision_fails_closed(self):
        kinds = [RequestType.objects.create(code=code, name="Synthetic") for code in ("AB_CD", "ABCD")]
        barrier = Barrier(2)
        def worker(kind_id):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                kind = RequestType.objects.get(pk=kind_id)
                barrier.wait(timeout=15)
                try:
                    with allocation_clock(self.moment):
                        create_request_once(self.instance(kind, actor), actor, token=uuid4(), digest="a" * 64,
                                            save_related=lambda req: None, submit=False)
                    return True
                except (ValidationError, IntegrityError):
                    return False
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            successes = list(pool.map(worker, [kind.pk for kind in kinds]))
        self.assertEqual(sum(successes), 1)
        self.assertEqual(Request.objects.count(), 1)
        self.assertEqual(RequestCreationReceipt.objects.count(), 1)
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)

    def test_receipt_counter_and_metadata_guards(self):
        with allocation_clock(self.moment):
            request, _ = self.create()
        for operation in [
            lambda: RequestCreationReceipt.objects.filter(request=request).update(payload_digest="b" * 64),
            lambda: RequestCreationReceipt.objects.filter(request=request).delete(),
            lambda: RequestReferenceSequence.objects.filter(request_type=self.kind).update(last_counter=0),
            lambda: RequestReferenceSequence.objects.filter(request_type=self.kind).delete(),
            lambda: Request.objects.filter(pk=request.pk).update(reference_counter=2),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                operation()

    def test_unused_migration_round_trip_and_used_reversal_rejected(self):
        from django.db.migrations.executor import MigrationExecutor
        from django.db.migrations.exceptions import IrreversibleError
        current = [("requests_app", "0018_ordinary_request_references")]
        previous = [("requests_app", "0017_request_classification_request_classified_at_and_more")]
        try:
            MigrationExecutor(connection).migrate(previous)
        finally:
            MigrationExecutor(connection).migrate(current)
        with allocation_clock(self.moment):
            request, _ = self.create()
        with self.assertRaises(IrreversibleError):
            MigrationExecutor(connection).migrate(previous)
        # A rejected reversal must leave every safeguard and evidence row intact.
        self.assertTrue(RequestCreationReceipt.objects.filter(request=request).exists())
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)
        self.assertIn(current[0], MigrationExecutor(connection).loader.applied_migrations)

    def test_submit_failure_rolls_back_and_success_creates_one_workflow(self):
        with allocation_clock(self.moment), self.assertRaises(ValidationError):
            self.create(submit=True)
        self.assertFalse(RequestReferenceSequence.objects.exists())
        workflow = ApprovalWorkflow.objects.create(name="Synthetic", request_type=self.kind)
        ApprovalWorkflowStep.objects.create(workflow=workflow, step_order=1, approver_user=self.actor)
        token = uuid4()
        with allocation_clock(self.moment):
            request, _ = self.create(token, submit=True)
            self.create(token, submit=True)
        self.assertEqual(request.approvals.count(), 1)
        self.assertEqual(RequestAuditLog.objects.filter(request=request, action="SUBMITTED").count(), 1)
        self.assertFalse(StockMovement.objects.exists())

    def test_existing_http_form_and_lost_session_replay(self):
        self.client.force_login(self.actor)
        session = self.client.session; token = str(uuid4())
        import time
        session["request_submission_tokens"] = {token: {"action": "create", "status": "pending", "created_at": int(time.time())}}
        session.save()
        payload = {"submission_token": token, "action": "save_draft", "request_type": self.kind.pk,
                   "request_for_department": self.department.pk, "description": "Synthetic"}
        with allocation_clock(self.moment):
            response = self.client.post(reverse("create_request"), payload)
        self.assertEqual(response.status_code, 302)
        session = self.client.session; session.pop("request_submission_tokens", None); session.save()
        again = self.client.post(reverse("create_request"), payload)
        self.assertEqual(again.status_code, 302)
        self.assertEqual(again.url, response.url)
        self.assertEqual(Request.objects.count(), 1)
        payload["description"] = "Conflicting"
        self.client.post(reverse("create_request"), payload)
        self.assertEqual(Request.objects.count(), 1)
