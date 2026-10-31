"""Focused synthetic regressions; safe with standalone in-memory test settings."""
import json
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils.translation import override

from inventory.models import Succursale
from invoicing.services import _evidence
from workflows.admin import ApprovalWorkflowStepInline, WorkflowStepAdminForm
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep, validate_stock_review_steps
from .approval_forms import ApprovalActionForm
from .models import Request, RequestApproval, StockMovement
from .services import approve_step, return_step, resubmit_request
from .stock_services import deduct_material_stock
from .test_stock_safety import StockSafetyFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockReviewPositionTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.branch = Succursale.objects.create(
            code="POSITION", name="Synthetic branch", physical_address="Synthetic address")

    def chain(self, position=2, count=4):
        self.workflow.is_active = False
        self.workflow.save(update_fields=["is_active"])
        self.workflow = ApprovalWorkflow.objects.create(
            name="Synthetic positioned review", request_type=self.request_type)
        for order in range(1, count + 1):
            ApprovalWorkflowStep.objects.create(
                workflow=self.workflow, step_order=order,
                approver_user=self.user if order == position else self.other,
                is_stock_review=order == position)
        return self.make_request()

    def complete(self, req, position, count):
        for order in range(1, count + 1):
            approval = req.approvals.get(step_order=order)
            data = {"classification": "MICROCOM", "succursale": self.branch} if order == position else {}
            approve_step(approval, self.user if order == position else self.other, **data)
            req.refresh_from_db()
            self.assertEqual(req.status, "APPROVED" if order == count else "IN_REVIEW")
            self.assertEqual(req.current_step_order, None if order == count else order + 1)
            self.assertEqual(req.stock_deducted, order == count)

    def test_review_first_second_and_final_preserves_order_and_deducts_once(self):
        for position in (1, 2, 4):
            with self.subTest(position=position):
                before = self.balance()
                req, item = self.chain(position)
                self.complete(req, position, 4)
                self.assertEqual(self.balance(), before - 10)
                self.assertEqual(req.approvals.get(requires_stock_classification=True).step_order, position)
                self.assertEqual(StockMovement.objects.filter(request=req, movement_type="OUT").count(), 1)
                deduct_material_stock(req, user=self.user)
                with self.assertRaises(ValidationError):
                    approve_step(req.approvals.get(step_order=4), self.user if position == 4 else self.other)
                self.assertEqual(self.balance(), before - 10)
                # Invoicing must accept the designated evidence at any position.
                review, evidence = _evidence(req)
                self.assertEqual(review.step_order, position)
                self.assertEqual(len(evidence), 1)

    def test_step_two_cannot_act_before_step_one_even_if_current_pointer_is_tampered(self):
        req, _ = self.chain()
        review = req.approvals.get(step_order=2)
        with self.assertRaises(ValidationError):
            approve_step(review, self.user, classification="CLIENT")
        Request.objects.filter(pk=req.pk).update(current_step_order=2)
        with self.assertRaisesMessage(ValidationError, "preceding approval steps"):
            approve_step(review, self.user, classification="CLIENT")
        self.assertEqual(self.balance(), 100)

    def test_preceding_step_cannot_classify_and_review_cannot_approve_without_valid_input(self):
        req, _ = self.chain()
        first = req.approvals.get(step_order=1)
        with self.assertRaises(ValidationError):
            approve_step(first, self.other, classification="CLIENT")
        approve_step(first, self.other)
        review = req.approvals.get(step_order=2)
        for data in ({}, {"classification": "INVALID"}, {"classification": "MICROCOM"},
                     {"classification": "CLIENT", "succursale": self.branch}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                approve_step(review, self.user, **data)
        approve_step(review, self.user, classification="CLIENT")
        req.refresh_from_db()
        self.assertIsNone(req.succursale_id)
        self.assertEqual(req.current_step_order, 3)
        self.assertEqual(self.balance(), 100)
        with self.assertRaises(ValidationError):
            approve_step(req.approvals.get(step_order=3), self.other, classification="MICROCOM", succursale=self.branch)

    def test_unassigned_actor_and_missing_classification_http_are_rejected_at_step_two(self):
        req, _ = self.chain()
        approve_step(req.approvals.get(step_order=1), self.other)
        review = req.approvals.get(step_order=2)
        with self.assertRaises(ValidationError):
            approve_step(review, self.other, classification="CLIENT")
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("approval_detail", args=[review.pk]),
                                         {"action": "APPROVE", "classification": "CLIENT"}).status_code, 404)
        self.client.force_login(self.user)
        form = ApprovalActionForm({"action": "APPROVE"}, approval=review)
        self.assertFalse(form.is_valid())
        review.refresh_from_db()
        self.assertEqual(review.status, "PENDING")

    def test_multiple_designations_rejected_by_configuration_and_runtime(self):
        req, _ = self.chain()
        self.workflow.steps.filter(step_order=3).update(is_stock_review=True)
        with self.assertRaises(ValidationError):
            validate_stock_review_steps(self.workflow.steps.all())
        req.approvals.filter(step_order=3).update(requires_stock_classification=True)
        with self.assertRaises(ValidationError):
            approve_step(req.approvals.get(step_order=1), self.other)

    def test_admin_inline_and_standalone_accept_step_two_without_reordering(self):
        req, _ = self.chain()
        review = self.workflow.steps.get(step_order=2)
        form = WorkflowStepAdminForm(instance=review, data={
            "workflow": self.workflow.pk, "step_order": 2, "approver_user": self.user.pk,
            "is_required": "on", "is_stock_review": "on"})
        self.assertTrue(form.is_valid(), form.errors)
        self.user.is_staff = self.user.is_superuser = True
        request = RequestFactory().get("/admin/")
        request.user = self.user
        formset_class = ApprovalWorkflowStepInline(ApprovalWorkflow, admin.site).get_formset(request, self.workflow)
        prefix = formset_class.get_default_prefix()
        data = {f"{prefix}-TOTAL_FORMS": 4, f"{prefix}-INITIAL_FORMS": 4}
        for i, step in enumerate(self.workflow.steps.order_by("step_order")):
            data.update({f"{prefix}-{i}-id": step.pk, f"{prefix}-{i}-workflow": self.workflow.pk,
                         f"{prefix}-{i}-step_order": step.step_order,
                         f"{prefix}-{i}-approver_user": step.approver_user_id,
                         f"{prefix}-{i}-is_required": "on"})
            if step.is_stock_review:
                data[f"{prefix}-{i}-is_stock_review"] = "on"
        formset = formset_class(instance=self.workflow, data=data)
        self.assertTrue(formset.is_valid(), (formset.errors, formset.non_form_errors()))
        formset.save()
        self.assertEqual(list(self.workflow.steps.values_list("step_order", "is_stock_review")),
                         [(1, False), (2, True), (3, False), (4, False)])

    def test_admin_workflow_change_post_saves_step_two_and_rejects_duplicate_designations(self):
        req, _ = self.chain()
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        data = {"name": self.workflow.name, "request_type": self.request_type.pk,
                "is_active": "on", "steps-TOTAL_FORMS": 4, "steps-INITIAL_FORMS": 4, "_save": "Save"}
        original = list(self.workflow.steps.values_list("pk", "step_order", "approver_user_id"))
        for i, step in enumerate(self.workflow.steps.order_by("step_order")):
            data.update({f"steps-{i}-id": step.pk, f"steps-{i}-workflow": self.workflow.pk,
                         f"steps-{i}-step_order": step.step_order,
                         f"steps-{i}-approver_user": step.approver_user_id,
                         f"steps-{i}-is_required": "on"})
        data["steps-1-is_stock_review"] = "on"
        url = reverse("admin:workflows_approvalworkflow_change", args=[self.workflow.pk])
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(list(self.workflow.steps.values_list("pk", "step_order", "approver_user_id")), original)
        data["steps-2-is_stock_review"] = "on"
        response = self.client.post(url, data)
        self.assertContains(response, "Only one stock-review step")
        self.assertEqual(self.workflow.steps.filter(is_stock_review=True).count(), 1)

    def test_resubmit_archives_complete_history_and_requires_fresh_step_two_confirmation(self):
        req, _ = self.chain()
        approve_step(req.approvals.get(step_order=1), self.other, "Initial approval")
        approve_step(req.approvals.get(step_order=2), self.user,
                     "Classification", classification="MICROCOM", succursale=self.branch)
        return_step(req.approvals.get(step_order=3), self.other, "Correct this")
        req.refresh_from_db()
        stale_returned = Request.objects.get(pk=req.pk)
        old = list(req.approvals.order_by("step_order").values())
        resubmit_request(req, self.other)
        archive = json.loads(req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED").comment)
        self.assertEqual([row["id"] for row in archive["approvals"]], [row["id"] for row in old])
        for row, previous in zip(archive["approvals"], old):
            self.assertEqual(set(row), set(previous))
            for field in previous:
                self.assertEqual(row[field], str(previous[field]) if field in {"created_at", "acted_at"} and previous[field] else previous[field])
        req.refresh_from_db()
        with self.assertRaises(ValidationError):
            resubmit_request(req, self.other)
        with self.assertRaises(ValidationError):
            resubmit_request(stale_returned, self.other)
        self.assertEqual(req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").count(), 1)
        approve_step(req.approvals.get(step_order=1), self.other)
        review = req.approvals.get(step_order=2)
        with self.assertRaises(ValidationError):
            approve_step(review, self.user)
        approve_step(review, self.user, classification="CLIENT")
        approve_step(req.approvals.get(step_order=3), self.other)
        approve_step(req.approvals.get(step_order=4), self.other)
        self.assertEqual(self.balance(), 90)
        self.assertEqual(req.audit_logs.filter(action="STOCK_CLASSIFIED").count(), 2)

    def test_failed_resubmit_rolls_back_archive_and_preserves_original_rows(self):
        req, _ = self.chain()
        return_step(req.approvals.get(step_order=1), self.other, "Correct")
        req.refresh_from_db()
        original = list(req.approvals.values_list("pk", flat=True))
        with patch("requests_app.services.submit_request", side_effect=ValidationError("Synthetic failure")):
            with self.assertRaises(ValidationError):
                resubmit_request(req, self.other)
        self.assertCountEqual(req.approvals.values_list("pk", flat=True), original)
        self.assertFalse(req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").exists())

    def test_new_runtime_messages_have_french_translations(self):
        req, _ = self.chain()
        Request.objects.filter(pk=req.pk).update(current_step_order=2)
        with override("fr"), self.assertRaisesMessage(ValidationError, "précédentes"):
            approve_step(req.approvals.get(step_order=2), self.user, classification="CLIENT")

    def test_invoice_classification_confirmation_message_is_translated(self):
        req, _ = self.chain()
        self.complete(req, 2, 4)
        req.classified_by = self.other
        with override("fr"), self.assertRaisesMessage(ValidationError, "désigné"):
            _evidence(req)
