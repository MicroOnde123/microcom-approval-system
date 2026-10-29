"""Deferred real material integration checks; isolated PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from accounts.models import Department
from inventory.models import Material, MaterialCategory
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep
from .models import Request, RequestType, RequestMaterialItem, RequestAttachment, RequestCreationReceipt, RequestReferenceSequence, StockMovement
from .references import create_request_once
from .services import approve_step, return_step
from .test_references_postgresql import allocation_clock
from datetime import datetime, timezone


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MaterialReferencePostgreSQLTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL required")
        self.department = Department.objects.create(code="REFMAT", name="Synthetic")
        self.actor = get_user_model().objects.create_user(username="material-reference", department=self.department,
                                                       email="synthetic@example.invalid")
        self.final = get_user_model().objects.create_user(username="final-reference", department=self.department)
        self.kind = RequestType.objects.create(code="MATERIAL", name="Material", requires_materials=True)
        self.workflow = ApprovalWorkflow.objects.create(name="Synthetic", request_type=self.kind)
        ApprovalWorkflowStep.objects.create(workflow=self.workflow, step_order=1, approver_user=self.actor, is_stock_review=True)
        ApprovalWorkflowStep.objects.create(workflow=self.workflow, step_order=2, approver_user=self.final)
        category = MaterialCategory.objects.create(code="REFMAT", name="Synthetic")
        self.material = Material.objects.create(code="REFMAT", name="Router", category=category, unit="pcs", stock_quantity=23)
        self.moment = datetime(2027, 1, 1, tzinfo=timezone.utc)
        self.client.force_login(self.actor)

    def token(self, action):
        import time
        token = str(uuid4()); session = self.client.session
        session["request_submission_tokens"] = {token: {"action": action, "status": "pending", "created_at": int(time.time())}}
        session.save()
        return token

    def payload(self, token, action="submit", request=None):
        data = {"submission_token": token, "action": action, "request_type": self.kind.pk,
                "request_for_department": self.department.pk, "description": "Synthetic material",
                "material_items-TOTAL_FORMS": "1", "material_items-INITIAL_FORMS": "1" if request else "0",
                "material_items-0-material": self.material.pk, "material_items-0-quantity": "1",
                "material_items-0-note": "Synthetic"}
        if request:
            data["material_items-0-id"] = request.material_items.get().pk
        return data

    def approve(self, request):
        approve_step(request.approvals.get(step_order=1), self.actor, classification="CLIENT")
        approve_step(request.approvals.get(step_order=2), self.final)
        request.refresh_from_db()
        self.material.refresh_from_db()
        self.assertEqual(request.status, "APPROVED")
        self.assertEqual(self.material.stock_quantity, Decimal("22"))
        self.assertEqual(StockMovement.objects.filter(request=request, movement_type="OUT").count(), 1)

    def test_material_http_creation_retry_and_one_deduction(self):
        token = self.token("create"); data = self.payload(token)
        with patch("requests_app.services.send_notification_email") as notify, allocation_clock(self.moment):
            self.assertEqual(self.client.post(reverse("create_request"), data).status_code, 302)
            self.assertEqual(self.client.post(reverse("create_request"), data).status_code, 302)
        self.assertEqual(notify.call_count, 1)
        request = Request.objects.get()
        self.assertEqual(request.request_number, "REQ-MAT-0001/2027")
        self.assertEqual(request.material_items.count(), 1)
        self.assertEqual(request.approvals.count(), 2)
        self.approve(request)
        with self.assertRaises(ValidationError):
            approve_step(request.approvals.get(step_order=2), self.final)
        self.material.refresh_from_db(); self.assertEqual(self.material.stock_quantity, Decimal("22"))

    def test_draft_submission_correction_and_resubmission_keep_reference(self):
        with allocation_clock(self.moment):
            self.client.post(reverse("create_request"), self.payload(self.token("create"), "save_draft"))
        request = Request.objects.get(); number = request.request_number
        self.assertEqual(request.status, "DRAFT"); self.assertEqual(request.approvals.count(), 0)
        token = self.token(f"edit:{request.pk}")
        self.client.post(reverse("edit_request", args=[request.pk]), self.payload(token, request=request))
        request.refresh_from_db(); self.assertEqual(request.status, "IN_REVIEW")
        return_step(request.approvals.get(step_order=1), self.actor, "Synthetic correction")
        token = self.token(f"edit:{request.pk}")
        data = self.payload(token, "resubmit", request); data["description"] = "Corrected synthetic request"
        self.client.post(reverse("edit_request", args=[request.pk]), data)
        request.refresh_from_db()
        self.assertEqual(request.request_number, number)
        self.assertEqual(request.approvals.count(), 2)
        self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)
        self.approve(request)

    def test_concurrent_submitted_retries_have_one_chain_and_callback(self):
        barrier = Barrier(2); token = uuid4()
        def worker(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                request = Request(request_type_id=self.kind.pk, submitted_by=actor, department_id=self.department.pk,
                                  request_for_department_id=self.department.pk, description="Synthetic", status="PENDING")
                barrier.wait(timeout=15)
                with allocation_clock(self.moment):
                    result, _ = create_request_once(request, actor, token=token, digest="a" * 64, submit=True,
                        save_related=lambda req: RequestMaterialItem.objects.create(request=req, material_id=self.material.pk, quantity=1))
                return result.pk
            finally:
                close_old_connections()
        with patch("requests_app.services.send_notification_email") as notify, ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(worker, range(2)))
        self.assertEqual(len(set(ids)), 1); self.assertEqual(notify.call_count, 1)
        request = Request.objects.get(); self.assertEqual(request.approvals.count(), 2)
        self.assertEqual(request.material_items.count(), 1)
        self.assertFalse(StockMovement.objects.exists())

    def test_attachment_exact_retry_and_storage_failure(self):
        import tempfile
        from pathlib import Path
        token = self.token("create"); data = self.payload(token, "save_draft")
        # Only synthetic files in a test-owned TemporaryDirectory, never real media.
        with tempfile.TemporaryDirectory(prefix="microcom-reference-test-") as directory, override_settings(MEDIA_ROOT=directory):
            for _ in range(2):
                upload = SimpleUploadedFile("synthetic.txt", b"synthetic evidence", "text/plain")
                self.assertEqual(self.client.post(reverse("create_request"), {**data, "attachments": upload}).status_code, 302)
            self.assertEqual(RequestAttachment.objects.count(), 1)
            self.assertEqual(len(list(Path(directory).rglob("*.txt"))), 1)
            failed_token = self.token("create"); failed = self.payload(failed_token, "save_draft")
            # Mock the storage boundary; rollback must not lose committed records.
            with patch("django.core.files.storage.FileSystemStorage._save", side_effect=OSError("Synthetic storage failure")):
                self.client.raise_request_exception = False
                response = self.client.post(reverse("create_request"), {**failed,
                    "attachments": SimpleUploadedFile("failure.txt", b"synthetic", "text/plain")})
                self.assertGreaterEqual(response.status_code, 400)
            self.assertEqual(Request.objects.count(), 1)
            self.assertEqual(RequestCreationReceipt.objects.count(), 1)
            self.assertEqual(RequestReferenceSequence.objects.get().last_counter, 1)

    def test_admin_add_is_forbidden_but_existing_access_remains(self):
        self.actor.is_staff = True; self.actor.save()
        self.actor.user_permissions.add(*Permission.objects.filter(content_type__app_label="requests_app",
            codename__in=["add_request", "view_request", "change_request"]))
        self.client.post(reverse("create_request"), self.payload(self.token("create"), "save_draft"))
        request = Request.objects.get()
        self.assertEqual(self.client.get(reverse("admin:requests_app_request_add")).status_code, 403)
        self.assertEqual(self.client.post(reverse("admin:requests_app_request_add"), {}).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:requests_app_request_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:requests_app_request_change", args=[request.pk])).status_code, 200)
