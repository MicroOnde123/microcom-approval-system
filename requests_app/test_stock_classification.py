from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils.translation import activate, deactivate, override

from accounts.models import Department
from inventory.models import Succursale
from workflows.admin import WorkflowStepAdminForm, ApprovalWorkflowStepInline
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep, validate_stock_review_steps
from .approval_forms import ApprovalActionForm
from .models import Request, RequestApproval, RequestAuditLog, RequestMaterialItem, StockMovement
from .services import approve_step, reject_step, return_step, resubmit_request, submit_request
from .test_stock_safety import StockSafetyFixtures
from . import test_stock_safety as stock_safety


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockClassificationTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        activate("en")
        self.addCleanup(deactivate)
        super().setUp()
        self.step = self.workflow.steps.get()
        self.step.is_stock_review = True
        self.step.save()
        self.branch = Succursale.objects.create(code="SYNTH", name="Synthetic succursale")
        self.inactive = Succursale.objects.create(code="INACTIVE", name="Inactive synthetic", is_active=False)

    def review(self, multiple=False):
        if multiple:
            ApprovalWorkflowStep.objects.create(workflow=self.workflow, step_order=2, approver_user=self.other)
        req, item = self.make_request()
        return req, item, req.approvals.get(step_order=1)

    def test_single_stock_reviewer_is_final_and_deducts_exactly_once(self):
        req, item, first = self.review()
        approve_step(first, self.user, classification="CLIENT")
        req.refresh_from_db()
        self.assertEqual(req.classification, "CLIENT")
        self.assertIsNone(req.succursale_id)
        self.assertEqual(req.classified_by_id, self.user.pk)
        self.assertIsNotNone(req.classified_at)
        self.assertEqual(req.status, "APPROVED")
        self.assertTrue(req.stock_deducted)
        self.assertEqual(self.balance(), 90)
        self.assertEqual(req.approvals.count(), 1)
        with self.assertRaises(ValidationError):
            approve_step(first, self.user, classification="CLIENT")
        self.assertEqual(StockMovement.objects.filter(request=req, movement_type="OUT").count(), 1)
        self.assertEqual(req.audit_logs.filter(action="STOCK_CLASSIFIED", performed_by=self.user).count(), 1)

    def test_classified_request_return_preserves_classification_and_existing_retry_behavior(self):
        req, item, first = self.review()
        approve_step(first, self.user, classification="MICROCOM", succursale=self.branch)
        req.refresh_from_db()
        metadata = (req.classification, req.succursale_id, req.classified_by_id, req.classified_at)
        token = self.token(item)
        self.assertTrue(self.restore(3, token, item=item)[1])
        self.assertFalse(self.restore(3, token, item=item)[1])
        self.assertEqual(self.balance(), 93)
        req.refresh_from_db()
        self.assertEqual((req.classification, req.succursale_id, req.classified_by_id, req.classified_at), metadata)

    def test_multi_step_review_classifies_without_deduction_until_final(self):
        req, item, first = self.review(multiple=True)
        approve_step(first, self.user, classification="MICROCOM", succursale=self.branch)
        req.refresh_from_db()
        self.assertEqual((req.status, req.current_step_order), ("IN_REVIEW", 2))
        self.assertFalse(req.stock_deducted)
        self.assertEqual(self.balance(), 100)
        self.assertFalse(StockMovement.objects.filter(request=req).exists())
        self.assertIsNone(self.material.unit_price)
        self.assertIsNone(req.amount)
        approve_step(req.approvals.get(step_order=2), self.other)
        self.assertEqual(self.balance(), 90)
        self.assertEqual(StockMovement.objects.filter(request=req).count(), 1)

    def test_explicit_central_stock_reviewer_is_selected_across_departments(self):
        department = Department.objects.create(name="Other synthetic department", code="CROSS")
        req = Request.objects.create(request_number="SYNTHETIC-CROSS", request_type=self.request_type,
            submitted_by=self.other, department=department, request_for_department=department, description="Synthetic")
        RequestMaterialItem.objects.create(request=req, material=self.material, quantity=2)
        submit_request(req)
        first = req.approvals.get()
        self.assertEqual(first.approver_user_id, self.user.pk)
        self.assertTrue(first.requires_stock_classification)
        approve_step(first, self.user, classification="CLIENT")
        self.assertEqual(self.balance(), 98)

    def test_alternate_reviewer_classifies_and_is_recorded_as_actor(self):
        alternate = get_user_model().objects.create_user(username="synthetic-alternate")
        self.step.alternate_approver_user = alternate
        self.step.save()
        req, item, first = self.review()
        approve_step(first, alternate, classification="MICROCOM", succursale=self.branch)
        req.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(req.classified_by_id, alternate.pk)
        self.assertEqual(first.acted_by_id, alternate.pk)
        self.assertEqual(req.audit_logs.get(action="STOCK_CLASSIFIED").performed_by_id, alternate.pk)

    def test_unassigned_stock_manager_and_forged_approval_url_are_rejected(self):
        req, item, first = self.review()
        self.other.can_manage_stock = True
        self.other.save()
        with self.assertRaises(ValidationError):
            approve_step(first, self.other, classification="CLIENT")
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("approval_detail", args=[first.pk]),
            {"action": "APPROVE", "classification": "CLIENT"}).status_code, 404)
        self.assertEqual(self.balance(), 100)
        req.refresh_from_db()
        self.assertIsNone(req.classification)

    def test_missing_invalid_and_inactive_classification_inputs_write_nothing(self):
        req, item, first = self.review()
        for data in ({}, {"classification": "BAD"}, {"classification": "MICROCOM"},
                     {"classification": "MICROCOM", "succursale": self.inactive},
                     {"classification": "MICROCOM", "succursale": "not-an-id"},
                     {"classification": "CLIENT", "succursale": self.branch}):
            with self.subTest(data=data), self.assertRaises(ValidationError):
                approve_step(first, self.user, **data)
            req.refresh_from_db()
            self.assertIsNone(req.classification)
            self.assertEqual(self.balance(), 100)
            self.assertFalse(req.audit_logs.filter(action="STOCK_CLASSIFIED").exists())

    def test_service_rechecks_succursale_activity_after_form_validation(self):
        req, item, first = self.review()
        form = ApprovalActionForm({"action": "APPROVE", "classification": "MICROCOM", "succursale": self.branch.pk}, approval=first)
        self.assertTrue(form.is_valid(), form.errors)
        Succursale.objects.filter(pk=self.branch.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            approve_step(first, self.user, classification=form.cleaned_data["classification"], succursale=form.cleaned_data["succursale"])
        self.assertEqual(self.balance(), 100)

    def test_reject_and_return_do_not_require_classification_or_valid_branch(self):
        for action, service in (("REJECT", reject_step), ("RETURN", return_step)):
            req, item, first = self.review()
            form = ApprovalActionForm({"action": action, "classification": "BAD", "succursale": "invalid"}, approval=first)
            self.assertTrue(form.is_valid(), form.errors)
            service(first, self.user, "Synthetic review")
            req.refresh_from_db()
            self.assertIsNone(req.classification)
            self.assertEqual(self.balance(), 100)

    def test_review_reject_and_return_posts_ignore_unneeded_classification_fields(self):
        self.client.force_login(self.user)
        for action, status in (("REJECT", "REJECTED"), ("RETURN", "RETURNED")):
            req, item, first = self.review()
            response = self.client.post(reverse("approval_detail", args=[first.pk]),
                {"action": action, "classification": "invalid", "succursale": "invalid"}, HTTP_ACCEPT_LANGUAGE="fr")
            self.assertEqual(response.status_code, 302)
            req.refresh_from_db()
            self.assertEqual(req.status, status)
            self.assertIsNone(req.classification)
            self.assertEqual(self.balance(), 100)

    def test_later_reviewer_cannot_skip_stock_review_even_with_tampered_current_step(self):
        req, item, first = self.review(multiple=True)
        later = req.approvals.get(step_order=2)
        with self.assertRaises(ValidationError):
            approve_step(later, self.other)
        Request.objects.filter(pk=req.pk).update(current_step_order=2)
        with self.assertRaisesMessage(ValidationError, "preceding approval steps"):
            approve_step(later, self.other)
        self.assertEqual(self.balance(), 100)

    def test_later_reviewer_cannot_override_classification(self):
        req, item, first = self.review(multiple=True)
        approve_step(first, self.user, classification="CLIENT")
        later = req.approvals.get(step_order=2)
        with self.assertRaises(ValidationError):
            approve_step(later, self.other, classification="MICROCOM", succursale=self.branch)
        form = ApprovalActionForm({"action": "APPROVE", "classification": "MICROCOM", "succursale": self.branch.pk}, approval=later)
        self.assertFalse(form.is_valid())
        req.refresh_from_db()
        self.assertEqual(req.classification, "CLIENT")
        self.assertEqual(self.balance(), 100)

    def test_legacy_pending_request_is_not_retroactively_marked(self):
        self.assertFalse(self.req.approvals.get().requires_stock_classification)
        self.issue()
        self.req.refresh_from_db()
        self.assertIsNone(self.req.classification)
        self.assertEqual(self.balance(), 90)

    def test_approval_snapshot_survives_later_workflow_configuration_change(self):
        req, item, first = self.review()
        self.step.is_stock_review = False
        self.step.save()
        with self.assertRaises(ValidationError):
            approve_step(first, self.user)
        approve_step(first, self.user, classification="CLIENT")
        self.assertEqual(self.balance(), 90)

    def test_resubmission_retains_previous_values_but_requires_confirmation(self):
        req, item, first = self.review(multiple=True)
        approve_step(first, self.user, classification="MICROCOM", succursale=self.branch)
        req.refresh_from_db()
        previous_actor, previous_time = req.classified_by_id, req.classified_at
        old_ids = list(req.approvals.values_list("pk", flat=True))
        return_step(req.approvals.get(step_order=2), self.other, "Synthetic correction")
        req.refresh_from_db()
        resubmit_request(req, self.other)
        self.assertFalse(RequestApproval.objects.filter(pk__in=old_ids).exists())
        req.refresh_from_db()
        self.assertEqual((req.classification, req.succursale_id, req.classified_by_id, req.classified_at),
                         ("MICROCOM", self.branch.pk, previous_actor, previous_time))
        rebuilt = req.approvals.get(step_order=1)
        with self.assertRaises(ValidationError):
            approve_step(rebuilt, self.user)
        approve_step(rebuilt, self.user, classification="CLIENT")
        req.refresh_from_db()
        self.assertEqual(req.classification, "CLIENT")
        self.assertIsNone(req.succursale_id)
        self.assertGreater(req.classified_at, previous_time)
        self.assertEqual(req.audit_logs.filter(action="STOCK_CLASSIFIED").count(), 2)
        self.assertEqual(self.balance(), 100)
        approve_step(req.approvals.get(step_order=2), self.other)
        self.assertEqual(self.balance(), 90)

    def test_insufficient_stock_rolls_back_classification_and_final_approval(self):
        req, item, first = self.review()
        self.material.stock_quantity = 5
        self.material.save(update_fields=["stock_quantity"])
        with self.assertRaises(ValidationError):
            approve_step(first, self.user, classification="MICROCOM", succursale=self.branch)
        req.refresh_from_db()
        first.refresh_from_db()
        self.assertIsNone(req.classification)
        self.assertIsNone(req.classified_at)
        self.assertEqual(first.status, "PENDING")
        self.assertFalse(req.audit_logs.filter(action="STOCK_CLASSIFIED").exists())
        self.assertEqual(self.balance(), 5)

    def test_audit_failure_rolls_back_metadata(self):
        req, item, first = self.review()
        with patch("requests_app.classification.RequestAuditLog.objects.create", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError):
                approve_step(first, self.user, classification="CLIENT")
        req.refresh_from_db()
        self.assertIsNone(req.classification)
        self.assertEqual(self.balance(), 100)

    def test_database_classification_pairs_and_protected_branch_reference(self):
        for kind, branch in ((None, self.branch), ("MICROCOM", None), ("CLIENT", self.branch), ("BAD", None)):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Request.objects.filter(pk=self.req.pk).update(classification=kind, succursale=branch)
        req, item, first = self.review()
        approve_step(first, self.user, classification="MICROCOM", succursale=self.branch)
        with self.assertRaises(ProtectedError):
            self.branch.delete()

    def test_bilingual_review_form_errors_and_success(self):
        for language, label, message in (("en", "Stock classification", "Select Client or Microcom to approve the stock review."),
                                         ("fr", "Classification du stock", "Sélectionnez Client ou Microcom pour approuver le contrôle du stock.")):
            req, item, first = self.review()
            self.client.force_login(self.user)
            url = reverse("approval_detail", args=[first.pk])
            response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response, label)
            self.assertNotIn("\ufffd", response.content.decode())
            response = self.client.post(url, {"action": "APPROVE"}, HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response, message)
            response = self.client.post(url, {"action": "APPROVE", "classification": "CLIENT"}, HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code, 302)
            req.refresh_from_db()
            self.assertEqual(req.classification, "CLIENT")

    def test_bilingual_branch_validation_and_forbidden_classification(self):
        req, item, first = self.review()
        for language, error in (("en", "Select an active succursale for a Microcom request."),
                                ("fr", "Sélectionnez une succursale active pour une demande Microcom.")):
            with override(language):
                form = ApprovalActionForm({"action": "APPROVE", "classification": "MICROCOM", "succursale": self.inactive.pk}, approval=first)
                self.assertFalse(form.is_valid())
                self.assertIn(error, str(form.errors))

    def test_workflow_configuration_accepts_later_but_rejects_duplicate_and_role_only_review(self):
        later = ApprovalWorkflowStep(workflow=self.workflow, step_order=2, approver_user=self.other, is_stock_review=True)
        with self.assertRaises(ValidationError):
            validate_stock_review_steps([self.step, later])
        self.step.is_stock_review = False
        validate_stock_review_steps([self.step, later])
        later.approver_user = None
        with self.assertRaises(ValidationError):
            later.clean()

    def test_standalone_admin_accepts_designation_after_first_step(self):
        self.step.is_stock_review = False
        self.step.save()
        form = WorkflowStepAdminForm(data={"workflow": self.workflow.pk, "step_order": 2,
            "approver_user": self.user.pk, "is_required": "on", "is_stock_review": "on"})
        self.assertTrue(form.is_valid(), form.errors)

    def test_admin_inline_accepts_single_review_without_inserting_steps(self):
        self.user.is_staff = self.user.is_superuser = True
        request = RequestFactory().get("/admin/")
        request.user = self.user
        inline = ApprovalWorkflowStepInline(ApprovalWorkflow, admin.site)
        formset_class = inline.get_formset(request, self.workflow)
        prefix = formset_class.get_default_prefix()
        formset = formset_class(instance=self.workflow, data={f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-INITIAL_FORMS": 1,
            f"{prefix}-0-id": self.step.pk, f"{prefix}-0-workflow": self.workflow.pk,
            f"{prefix}-0-step_order": 1, f"{prefix}-0-approver_user": self.user.pk,
            f"{prefix}-0-is_stock_review": "on", f"{prefix}-0-is_required": "on"})
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.workflow.steps.count(), 1)

    def test_admin_can_create_a_single_step_stock_workflow_in_one_post(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        prefix = "steps"
        response = self.client.post(reverse("admin:workflows_approvalworkflow_add"), {
            "name": "Synthetic new stock workflow", "request_type": self.request_type.pk,
            "is_active": "on", f"{prefix}-TOTAL_FORMS": 1, f"{prefix}-INITIAL_FORMS": 0,
            f"{prefix}-0-step_order": 1, f"{prefix}-0-approver_user": self.user.pk,
            f"{prefix}-0-is_stock_review": "on", f"{prefix}-0-is_required": "on", "_save": "Save"})
        self.assertEqual(response.status_code, 302)
        workflow = ApprovalWorkflow.objects.get(name="Synthetic new stock workflow")
        self.assertEqual(workflow.steps.count(), 1)
        self.assertTrue(workflow.steps.get().is_stock_review)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class StockClassificationConcurrencyTests(StockSafetyFixtures, TransactionTestCase):
    race = stock_safety.StockConcurrencyTests.race

    def test_competing_classifications_finalize_once_without_overwriting_winner(self):
        step = self.workflow.steps.get()
        step.is_stock_review = True
        step.save()
        req, item = self.make_request()
        first = req.approvals.get()
        branch = Succursale.objects.create(code="RACE", name="Synthetic race")
        results = self.race([
            lambda: approve_step(first, self.user, classification="CLIENT"),
            lambda: approve_step(first, self.user, classification="MICROCOM", succursale=branch)])
        self.assertCountEqual(results, ["accepted", "rejected"])
        req.refresh_from_db()
        self.assertEqual(req.classification, "CLIENT" if results[0] == "accepted" else "MICROCOM")
        self.assertEqual(req.succursale_id, None if results[0] == "accepted" else branch.pk)
        self.assertEqual(req.audit_logs.filter(action="STOCK_CLASSIFIED").count(), 1)
        self.assertEqual(StockMovement.objects.filter(request=req, movement_type="OUT").count(), 1)
        self.assertEqual(self.balance(), 90)
