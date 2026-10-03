from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from urllib.parse import quote

from accounts.models import Department
from inventory.models import Material, MaterialCategory
from requests_app.models import (
    Request,
    RequestApproval,
    RequestAuditLog,
    RequestMaterialItem,
    RequestType,
)
from requests_app.forms import RequestForm
from requests_app.services import approve_step, submit_request
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep


TWO_COPY_WARNING = (
    "This request has too many material items for two-copy printing. "
    "Please print one copy."
)


class RequestDepartmentOwnershipTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_department = Department.objects.create(name="Administration", code="ADMIN-OWN")
        self.fiber_department = Department.objects.create(name="Fiber", code="FIBER-OWN")
        self.user = User.objects.create_user(
            username="department-user",
            password="test-password",
            full_name="Department User",
            department=self.admin_department,
        )
        self.admin = User.objects.create_user(
            username="department-admin",
            password="test-password",
            full_name="Department Admin",
            department=self.admin_department,
            is_staff=True,
            is_superuser=True,
        )
        self.approver = User.objects.create_user(
            username="department-approver",
            password="test-password",
            full_name="Department Approver",
            department=self.admin_department,
        )
        self.request_type = RequestType.objects.create(
            name="Ownership Request",
            code="OWNERSHIP",
        )
        self.workflow = ApprovalWorkflow.objects.create(
            name="Administration ownership workflow",
            request_type=self.request_type,
            department=self.admin_department,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=self.workflow,
            step_order=1,
            approver_user=self.approver,
        )
        self.fiber_approver = User.objects.create_user(
            username="fiber-department-approver",
            password="test-password",
            department=self.fiber_department,
        )
        self.fiber_workflow = ApprovalWorkflow.objects.create(
            name="Fiber ownership workflow",
            request_type=self.request_type,
            department=self.fiber_department,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=self.fiber_workflow,
            step_order=1,
            approver_user=self.fiber_approver,
        )

    def create_request(self, owner_department=None, **kwargs):
        return Request.objects.create(
            request_number=kwargs.pop("request_number", "REQ-OWN-1"),
            request_type=self.request_type,
            submitted_by=kwargs.pop("submitted_by", self.user),
            department=kwargs.pop("department", self.admin_department),
            request_for_department=owner_department or self.admin_department,
            description="Department ownership test",
            **kwargs,
        )

    def post_create(self, user, owner_department, request_type=None, amount=None):
        self.client.force_login(user)
        response = self.client.get(reverse("create_request"), HTTP_HOST="127.0.0.1")
        token = response.context["submission_token"]
        data = {
            "submission_token": token,
            "request_type": (request_type or self.request_type).pk,
            "request_for_department": owner_department.pk,
            "description": "Created for another department",
            "date_needed": timezone.localdate().isoformat(),
        }
        if amount is not None:
            data["amount"] = amount
        return self.client.post(
            reverse("create_request"),
            data,
            HTTP_HOST="127.0.0.1",
        )

    def test_normal_user_can_select_another_department(self):
        form = RequestForm(user=self.user)
        self.assertQuerySetEqual(
            form.fields["request_for_department"].queryset,
            [self.admin_department, self.fiber_department],
        )
        self.assertEqual(form["request_for_department"].value(), self.admin_department.pk)
        response = self.post_create(self.user, self.fiber_department)
        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.user)
        self.assertEqual(request_obj.request_for_department, self.fiber_department)
        self.assertEqual(request_obj.approvals.get().approver_user, self.fiber_approver)

    def test_missing_or_invalid_department_is_rejected(self):
        valid_data = {
            "request_type": self.request_type.pk,
            "description": "Department validation test",
        }
        missing_form = RequestForm(data=valid_data, user=self.user)
        self.assertFalse(missing_form.is_valid())
        self.assertIn("request_for_department", missing_form.errors)

        invalid_form = RequestForm(
            data={**valid_data, "request_for_department": 999999},
            user=self.user,
        )
        self.assertFalse(invalid_form.is_valid())
        self.assertIn("request_for_department", invalid_form.errors)

    def test_normal_user_creates_for_own_department(self):
        response = self.post_create(self.user, self.admin_department)
        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.user)
        self.assertEqual(request_obj.request_for_department, self.admin_department)

    def test_admin_creates_for_another_department(self):
        response = self.post_create(self.admin, self.fiber_department)
        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.admin)
        self.assertEqual(request_obj.department, self.admin_department)
        self.assertEqual(request_obj.request_for_department, self.fiber_department)
        self.assertEqual(request_obj.approvals.get().workflow_step.workflow, self.fiber_workflow)

    def test_admin_submits_for_it_and_it_workflow_is_selected(self):
        User = get_user_model()
        it_department = Department.objects.create(name="IT", code="IT-OWN")
        it_approver = User.objects.create_user(
            username="it-department-approver",
            password="test-password",
            department=it_department,
        )
        it_workflow = ApprovalWorkflow.objects.create(
            name="IT ownership workflow",
            request_type=self.request_type,
            department=it_department,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=it_workflow,
            step_order=1,
            approver_user=it_approver,
        )

        response = self.post_create(self.admin, it_department)

        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.admin)
        self.assertEqual(request_obj.department, self.admin_department)
        self.assertEqual(request_obj.request_for_department, it_department)
        self.assertEqual(request_obj.approvals.get().workflow_step.workflow, it_workflow)

    def test_global_workflow_is_selected_when_department_workflow_is_missing(self):
        global_type = RequestType.objects.create(
            name="Global-only Request",
            code="GLOBAL-ONLY",
        )
        global_workflow = ApprovalWorkflow.objects.create(
            name="Global fallback workflow",
            request_type=global_type,
            department=None,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=global_workflow,
            step_order=1,
            approver_user=self.approver,
        )

        response = self.post_create(
            self.admin,
            self.fiber_department,
            request_type=global_type,
        )

        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.admin)
        self.assertEqual(request_obj.approvals.get().workflow_step.workflow, global_workflow)

    def test_department_workflow_wins_when_global_workflow_also_exists(self):
        global_workflow = ApprovalWorkflow.objects.create(
            name="Global fallback workflow",
            request_type=self.request_type,
            department=None,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=global_workflow,
            step_order=1,
            approver_user=self.approver,
        )

        response = self.post_create(self.admin, self.fiber_department)

        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.admin)
        self.assertEqual(request_obj.approvals.get().workflow_step.workflow, self.fiber_workflow)

    def test_amount_limits_are_applied_before_global_fallback(self):
        self.fiber_workflow.min_amount = 100
        self.fiber_workflow.save(update_fields=["min_amount"])
        global_workflow = ApprovalWorkflow.objects.create(
            name="Amount-compatible global workflow",
            request_type=self.request_type,
            department=None,
            max_amount=99,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=global_workflow,
            step_order=1,
            approver_user=self.approver,
        )

        response = self.post_create(self.admin, self.fiber_department, amount="50.00")

        self.assertEqual(response.status_code, 302)
        request_obj = Request.objects.get(submitted_by=self.admin)
        self.assertEqual(request_obj.approvals.get().workflow_step.workflow, global_workflow)

    def test_two_ownership_departments_choose_their_matching_workflows(self):
        User = get_user_model()
        fiber_submitter = User.objects.create_user(
            username="fiber-submitter",
            password="test-password",
            department=self.fiber_department,
        )
        administration_request = self.create_request(
            self.fiber_department,
            request_number="REQ-ROUTE-ADMIN",
        )
        fiber_request = self.create_request(
            self.admin_department,
            request_number="REQ-ROUTE-FIBER",
            submitted_by=fiber_submitter,
            department=self.fiber_department,
        )

        submit_request(administration_request)
        submit_request(fiber_request)

        self.assertEqual(administration_request.approvals.get().approver_user, self.fiber_approver)
        self.assertEqual(fiber_request.approvals.get().approver_user, self.approver)

    def test_department_filters_use_request_owner(self):
        owned_by_fiber = self.create_request(self.fiber_department)
        owned_by_fiber.current_step_order = 1
        owned_by_fiber.save(update_fields=["current_step_order"])
        RequestApproval.objects.create(
            request=owned_by_fiber,
            workflow_step=self.workflow.steps.get(),
            step_order=1,
            approver_user=self.approver,
        )
        self.client.force_login(self.approver)
        response = self.client.get(
            reverse("pending_approvals"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(response, owned_by_fiber.request_number)
        response = self.client.get(
            reverse("pending_approvals"),
            {"department": self.admin_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        self.assertNotContains(response, owned_by_fiber.request_number)

    def test_reports_exports_and_print_include_both_departments(self):
        category = MaterialCategory.objects.create(name="Ownership Materials")
        material = Material.objects.create(
            name="Fiber Cable",
            code="FIBER-CABLE-OWN",
            category=category,
            unit="roll",
            stock_quantity=10,
        )
        request_obj = self.create_request(
            self.fiber_department,
            status="APPROVED",
            finalized_at=timezone.now(),
        )
        RequestMaterialItem.objects.create(request=request_obj, material=material, quantity=1)

        self.client.force_login(self.admin)
        csv_response = self.client.get(
            reverse("export_material_report_csv"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        content = csv_response.content.decode("utf-8")
        self.assertIn("Request For Department", content)
        self.assertIn("Administration", content)
        self.assertIn("Fiber", content)

        print_response = self.client.get(
            reverse("approved_document", args=[request_obj.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(print_response, "Request For Department")
        self.assertContains(print_response, "Fiber")

        excel_response = self.client.get(
            reverse("export_material_report_excel"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        sheet = load_workbook(BytesIO(excel_response.content)).active
        self.assertEqual(sheet["D4"].value, "Request For Department")
        self.assertEqual(sheet["D5"].value, "Fiber")

        bulk_response = self.client.post(
            reverse("bulk_print_material_documents"),
            {"selected_requests": [request_obj.pk]},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(bulk_response, "Request For Department")
        self.assertContains(bulk_response, "Fiber")

    def test_all_list_filters_use_request_for_department(self):
        fiber_request = self.create_request(
            self.fiber_department,
            request_number="REQ-FILTER-FIBER",
        )
        admin_request = self.create_request(
            self.admin_department,
            request_number="REQ-FILTER-ADMIN",
        )

        self.client.force_login(self.user)
        my_response = self.client.get(
            reverse("my_requests"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(my_response, fiber_request.request_number)
        self.assertNotContains(my_response, admin_request.request_number)

        acted_approval = RequestApproval.objects.create(
            request=fiber_request,
            workflow_step=self.workflow.steps.get(),
            step_order=1,
            approver_user=self.approver,
            acted_by=self.approver,
            acted_at=timezone.now(),
            status="APPROVED",
        )
        RequestApproval.objects.create(
            request=admin_request,
            workflow_step=self.workflow.steps.get(),
            step_order=1,
            approver_user=self.approver,
            acted_by=self.approver,
            acted_at=timezone.now(),
            status="APPROVED",
        )
        self.client.force_login(self.approver)
        history_response = self.client.get(
            reverse("approval_history"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(history_response, acted_approval.request.request_number)
        self.assertNotContains(history_response, admin_request.request_number)

        category = MaterialCategory.objects.create(
            name="Filter Materials",
            code="FILTER-MATERIALS",
        )
        material = Material.objects.create(
            name="Filter Cable",
            code="FILTER-CABLE",
            category=category,
            unit="roll",
            stock_quantity=10,
        )
        fiber_request.status = "APPROVED"
        fiber_request.save(update_fields=["status"])
        admin_request.status = "APPROVED"
        admin_request.save(update_fields=["status"])
        RequestMaterialItem.objects.create(request=fiber_request, material=material, quantity=1)
        RequestMaterialItem.objects.create(request=admin_request, material=material, quantity=1)
        self.client.force_login(self.admin)
        report_response = self.client.get(
            reverse("material_reports"),
            {"department": self.fiber_department.pk},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(report_response, fiber_request.request_number)
        self.assertNotContains(report_response, admin_request.request_number)

    def test_material_approval_still_deducts_stock(self):
        self.request_type.requires_materials = True
        self.request_type.save(update_fields=["requires_materials"])
        category = MaterialCategory.objects.create(
            name="Stock Safety Materials",
            code="STOCK-SAFETY",
        )
        material = Material.objects.create(
            name="Stock Safety Cable",
            code="STOCK-SAFETY-CABLE",
            category=category,
            unit="roll",
            stock_quantity=10,
        )
        request_obj = self.create_request(request_number="REQ-STOCK-SAFETY")
        RequestMaterialItem.objects.create(
            request=request_obj,
            material=material,
            quantity=2,
        )
        submit_request(request_obj)

        approve_step(request_obj.approvals.get(), self.approver)

        material.refresh_from_db()
        request_obj.refresh_from_db()
        self.assertEqual(material.stock_quantity, 8)
        self.assertTrue(request_obj.stock_deducted)

    def test_historical_style_request_defaults_owner_and_opens(self):
        request_obj = self.create_request()
        request_obj.request_for_department = None
        request_obj.save()
        self.assertEqual(request_obj.request_for_department, self.admin_department)
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.pk]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Submitted By")
        self.assertContains(response, "Submitted From Department")
        self.assertContains(response, "Request For Department")


class AlternateApproverWorkflowTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Technical",
            code="TECH",
        )

        User = get_user_model()
        self.submitter = User.objects.create_user(
            username="submitter",
            password="pass12345",
            email="submitter@example.com",
            full_name="Submitter User",
            department=self.department,
        )
        self.primary = User.objects.create_user(
            username="primary",
            password="pass12345",
            email="primary@example.com",
            full_name="Primary Approver",
        )
        self.alternate = User.objects.create_user(
            username="alternate",
            password="pass12345",
            email="alternate@example.com",
            full_name="Alternate Approver",
        )

        self.request_type = RequestType.objects.create(
            name="Any Display Name",
            code="ANY",
            is_active=True,
        )
        self.workflow = ApprovalWorkflow.objects.create(
            name="Default approval",
            request_type=self.request_type,
            department=self.department,
            is_active=True,
        )
        self.workflow_step = ApprovalWorkflowStep.objects.create(
            workflow=self.workflow,
            step_order=1,
            approver_user=self.primary,
            alternate_approver_user=self.alternate,
        )

    def make_submitted_request(self):
        request_obj = Request.objects.create(
            request_number=f"REQ-{Request.objects.count() + 1}",
            request_type=self.request_type,
            submitted_by=self.submitter,
            department=self.department,
            description="Needs approval",
            status="PENDING",
        )
        submit_request(request_obj)
        return request_obj

    def get_approval(self, request_obj):
        return RequestApproval.objects.get(request=request_obj)

    def act_on_approval(self, user, approval, action):
        self.client.force_login(user)
        return self.client.post(
            reverse("approval_detail", args=[approval.id]),
            data={
                "action": action,
                "comment": f"{action} comment",
            },
            follow=True,
            HTTP_HOST="127.0.0.1",
        )

    def pending_count_for(self, user):
        self.client.force_login(user)
        response = self.client.get(
            reverse("notification_count"),
            HTTP_HOST="127.0.0.1",
        )
        return response.json()["pending"]

    def assert_action_result(self, request_obj, actor, action, expected_status):
        approval = self.get_approval(request_obj)
        response = self.act_on_approval(actor, approval, action)

        self.assertEqual(response.status_code, 200)

        approval.refresh_from_db()
        request_obj.refresh_from_db()

        self.assertEqual(approval.status, expected_status)
        self.assertEqual(approval.acted_by, actor)
        self.assertIsNotNone(approval.acted_at)
        self.assertEqual(request_obj.status, expected_status)

    def test_primary_approver_can_approve(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.primary, "APPROVE", "APPROVED")

    def test_alternate_approver_can_approve(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.alternate, "APPROVE", "APPROVED")

    def test_primary_approver_can_reject(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.primary, "REJECT", "REJECTED")

    def test_alternate_approver_can_reject(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.alternate, "REJECT", "REJECTED")

    def test_primary_approver_can_return(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.primary, "RETURN", "RETURNED")

    def test_alternate_approver_can_return(self):
        request_obj = self.make_submitted_request()

        self.assert_action_result(request_obj, self.alternate, "RETURN", "RETURNED")

    def test_once_approved_by_primary_alternate_cannot_approve(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.act_on_approval(self.primary, approval, "APPROVE")
        response = self.act_on_approval(self.alternate, approval, "APPROVE")

        approval.refresh_from_db()
        self.assertEqual(approval.status, "APPROVED")
        self.assertEqual(approval.acted_by, self.primary)
        self.assertContains(
            response,
            "This step has already been acted upon.",
            status_code=200,
        )

    def test_once_approved_by_alternate_primary_cannot_approve(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.act_on_approval(self.alternate, approval, "APPROVE")
        response = self.act_on_approval(self.primary, approval, "APPROVE")

        approval.refresh_from_db()
        self.assertEqual(approval.status, "APPROVED")
        self.assertEqual(approval.acted_by, self.alternate)
        self.assertContains(
            response,
            "This step has already been acted upon.",
            status_code=200,
        )

    def test_pending_approvals_disappear_for_other_user_after_action(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.assertEqual(self.pending_count_for(self.primary), 1)
        self.assertEqual(self.pending_count_for(self.alternate), 1)

        self.act_on_approval(self.primary, approval, "APPROVE")

        self.assertEqual(self.pending_count_for(self.primary), 0)
        self.assertEqual(self.pending_count_for(self.alternate), 0)

    def test_notification_counts_work_for_primary_and_alternate(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.assertEqual(self.pending_count_for(self.primary), 1)
        self.assertEqual(self.pending_count_for(self.alternate), 1)

        self.act_on_approval(self.alternate, approval, "REJECT")

        self.assertEqual(self.pending_count_for(self.primary), 0)
        self.assertEqual(self.pending_count_for(self.alternate), 0)

    def test_submit_request_sends_email_to_primary_and_alternate(self):
        self.make_submitted_request()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            set(mail.outbox[0].to),
            {"primary@example.com", "alternate@example.com"},
        )

    def test_primary_approver_name_is_displayed_as_actor(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.act_on_approval(self.primary, approval, "APPROVE")

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Primary Approver")

    def test_alternate_approver_name_is_displayed_as_actor(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.act_on_approval(self.alternate, approval, "APPROVE")

        self.client.force_login(self.alternate)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Alternate Approver")
        self.assertNotContains(response, "Primary Approver")

    def test_request_detail_shows_review_button_to_primary_approver(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)
        detail_url = (
            f"{reverse('request_detail', args=[request_obj.id])}"
            "?next=%2Fapprovals%2Fpending%2F%3Fstatus%3DPENDING"
        )

        self.client.force_login(self.primary)
        response = self.client.get(detail_url, HTTP_HOST="127.0.0.1")

        expected_url = (
            f"{reverse('approval_detail', args=[approval.id])}"
            f"?next={quote(detail_url, safe='/')}"
        )
        self.assertContains(response, "Review / Approve Request")
        self.assertContains(response, expected_url)
        self.assertEqual(response.context["active_approval_for_user"], approval)

    def test_request_detail_shows_review_button_to_alternate_approver(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)

        self.client.force_login(self.alternate)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Review / Approve Request")
        self.assertEqual(response.context["active_approval_for_user"], approval)

    def test_request_detail_hides_review_button_from_requester(self):
        request_obj = self.make_submitted_request()

        self.client.force_login(self.submitter)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, "Review / Approve Request")
        self.assertIsNone(response.context["active_approval_for_user"])

    def test_request_detail_hides_review_button_from_later_step_approver(self):
        later_approver = get_user_model().objects.create_user(
            username="later-approver",
            password="pass12345",
            email="later@example.com",
            full_name="Later Approver",
        )
        ApprovalWorkflowStep.objects.create(
            workflow=self.workflow,
            step_order=2,
            approver_user=later_approver,
        )
        request_obj = self.make_submitted_request()

        self.client.force_login(later_approver)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, "Review / Approve Request")
        self.assertIsNone(response.context["active_approval_for_user"])

    def test_request_detail_hides_review_button_from_unassigned_admin(self):
        request_obj = self.make_submitted_request()
        admin = get_user_model().objects.create_superuser(
            username="admin",
            password="pass12345",
            email="admin@example.com",
            full_name="Admin User",
        )

        self.client.force_login(admin)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, "Review / Approve Request")
        self.assertIsNone(response.context["active_approval_for_user"])

    def test_request_detail_hides_review_button_from_unassigned_stock_manager(self):
        request_obj = self.make_submitted_request()
        stock_manager = get_user_model().objects.create_user(
            username="stock-manager",
            password="pass12345",
            email="stock@example.com",
            full_name="Stock Manager",
            can_manage_stock=True,
        )
        category = MaterialCategory.objects.create(name="Office", code="OFFICE")
        material = Material.objects.create(
            category=category,
            name="Paper",
            code="PAPER",
        )
        RequestMaterialItem.objects.create(
            request=request_obj,
            material=material,
            quantity=1,
        )

        self.client.force_login(stock_manager)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, "Review / Approve Request")
        self.assertIsNone(response.context["active_approval_for_user"])

    def test_request_detail_hides_review_button_after_approval(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)
        self.act_on_approval(self.primary, approval, "APPROVE")

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, "Review / Approve Request")
        self.assertIsNone(response.context["active_approval_for_user"])

    def test_historical_approval_without_actor_falls_back_to_assigned_approver(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)
        approval.status = "APPROVED"
        approval.acted_by = None
        approval.acted_at = timezone.now()
        approval.save()
        request_obj.status = "APPROVED"
        request_obj.current_step_order = None
        request_obj.finalized_at = timezone.now()
        request_obj.save()

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("request_detail", args=[request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, "Primary Approver")

    def test_historical_approval_without_actor_appears_in_assigned_approver_history(self):
        request_obj = self.make_submitted_request()
        approval = self.get_approval(request_obj)
        approval.status = "APPROVED"
        approval.acted_by = None
        approval.acted_at = timezone.now()
        approval.save()
        request_obj.status = "APPROVED"
        request_obj.current_step_order = None
        request_obj.finalized_at = timezone.now()
        request_obj.save()

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("approval_history"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, request_obj.request_number, count=1)

    def test_pending_approvals_shows_request_once_when_user_is_primary_and_alternate(self):
        self.workflow_step.alternate_approver_user = self.primary
        self.workflow_step.save()
        request_obj = self.make_submitted_request()

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("pending_approvals"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, request_obj.request_number, count=1)
        self.assertEqual(self.pending_count_for(self.primary), 1)

    def test_approval_history_shows_request_once_for_multi_step_workflow(self):
        ApprovalWorkflowStep.objects.create(
            workflow=self.workflow,
            step_order=2,
            approver_user=self.primary,
            alternate_approver_user=self.alternate,
        )
        request_obj = self.make_submitted_request()

        first_approval = RequestApproval.objects.get(
            request=request_obj,
            step_order=1,
        )
        self.act_on_approval(self.primary, first_approval, "APPROVE")

        second_approval = RequestApproval.objects.get(
            request=request_obj,
            step_order=2,
        )
        self.act_on_approval(self.primary, second_approval, "APPROVE")

        self.client.force_login(self.primary)
        response = self.client.get(
            reverse("approval_history"),
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, request_obj.request_number, count=1)


class MaterialPrintCopyLimitTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Technical",
            code="TECH",
        )

        User = get_user_model()
        self.submitter = User.objects.create_user(
            username="material_submitter",
            password="pass12345",
            email="material-submit@example.com",
            full_name="Material Submitter",
            department=self.department,
        )
        self.stock_user = User.objects.create_user(
            username="stock_user",
            password="pass12345",
            email="stock@example.com",
            full_name="Stock User",
            can_manage_stock=True,
        )

        self.request_type = RequestType.objects.create(
            name="Material Request",
            code="MAT",
            is_active=True,
            requires_materials=True,
        )
        self.category = MaterialCategory.objects.create(
            name="General",
            code="GEN",
        )

    def make_material_request(self, item_count, number_suffix):
        request_obj = Request.objects.create(
            request_number=f"MAT-{number_suffix}",
            request_type=self.request_type,
            submitted_by=self.submitter,
            department=self.department,
            description="For installation",
            date_needed=timezone.now().date(),
            status="APPROVED",
            finalized_at=timezone.now(),
        )

        for index in range(item_count):
            material = Material.objects.create(
                category=self.category,
                name=f"Material {number_suffix}-{index}",
                code=f"MAT-{number_suffix}-{index}",
                unit="pcs",
                stock_quantity=10,
            )
            RequestMaterialItem.objects.create(
                request=request_obj,
                material=material,
                quantity=1,
            )

        return request_obj

    def assert_material_slip_count(self, response, count):
        content = response.content.decode()
        self.assertEqual(content.count("Material Exit Slip"), count)

    def export_workbook(self, language):
        self.client.force_login(self.stock_user)

        response = self.client.get(
            reverse("export_material_report_excel"),
            HTTP_ACCEPT_LANGUAGE=language,
            HTTP_HOST="127.0.0.1",
        )

        workbook = load_workbook(BytesIO(response.content))
        return response, workbook.active

    def test_material_reports_excel_and_print_controls_are_localized(self):
        self.client.force_login(self.stock_user)

        english_response = self.client.get(
            reverse("material_reports"),
            HTTP_ACCEPT_LANGUAGE="en",
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(english_response, "Export Excel")
        self.assertContains(english_response, "Print selected: 1 copy")
        self.assertContains(english_response, "Print selected: 2 copies")

        french_response = self.client.get(
            reverse("material_reports"),
            HTTP_ACCEPT_LANGUAGE="fr",
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(french_response, "Exporter Excel")
        self.assertContains(french_response, "Imprimer la sélection : 1 exemplaire")
        self.assertContains(french_response, "Imprimer la sélection : 2 exemplaires")

    def test_excel_export_uses_english_filename_and_labels(self):
        response, sheet = self.export_workbook("en")

        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="material_report.xlsx"',
        )
        self.assertEqual(sheet.title, "Material Report")
        self.assertEqual(sheet["A1"].value, "Microcom Material Report")
        self.assertEqual(sheet["A2"].value, "Generated At")
        self.assertEqual(
            [sheet.cell(row=4, column=column).value for column in range(1, 16)],
            [
                "Request Number",
                "Requester",
                "Department",
                "Request For Department",
                "Date Needed",
                "Approved Date",
                "Material",
                "Material Code",
                "Category",
                "Quantity",
                "Unit",
                "Available Stock",
                "Description",
                "Material Issue Note",
                "Approvers",
            ],
        )

    def test_excel_export_uses_french_filename_and_labels(self):
        response, sheet = self.export_workbook("fr")

        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="rapport_materiel.xlsx"',
        )
        self.assertEqual(sheet.title, "Rapport de matériel")
        self.assertEqual(sheet["A1"].value, "Rapport de matériel Microcom")
        self.assertEqual(sheet["A2"].value, "Généré le")
        self.assertEqual(
            [sheet.cell(row=4, column=column).value for column in range(1, 16)],
            [
                "Numéro de demande",
                "Demandeur",
                "Département",
                "Département concerné",
                "Date requise",
                "Date d’approbation",
                "Matériel",
                "Code matériel",
                "Catégorie",
                "Quantité",
                "Unité",
                "Stock disponible",
                "Description",
                "Note de sortie matériel",
                "Approbateurs",
            ],
        )

    def test_single_material_print_forces_one_copy_when_more_than_six_items(self):
        request_obj = self.make_material_request(item_count=7, number_suffix="007")
        self.client.force_login(self.submitter)

        response = self.client.get(
            f"{reverse('approved_document', args=[request_obj.id])}?copies=2",
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, TWO_COPY_WARNING)
        self.assertNotContains(response, 'class="print-sheet two-copies"')
        self.assert_material_slip_count(response, 1)

    def test_single_material_print_allows_two_copies_at_six_items(self):
        request_obj = self.make_material_request(item_count=6, number_suffix="006")
        self.client.force_login(self.submitter)

        response = self.client.get(
            f"{reverse('approved_document', args=[request_obj.id])}?copies=2",
            HTTP_HOST="127.0.0.1",
        )

        self.assertNotContains(response, TWO_COPY_WARNING)
        self.assertContains(response, 'class="print-sheet two-copies"')
        self.assert_material_slip_count(response, 2)

    def test_one_item_two_copy_print_uses_one_fixed_a4_grid(self):
        request_obj = self.make_material_request(item_count=1, number_suffix="001")
        self.client.force_login(self.submitter)

        response = self.client.get(
            f"{reverse('approved_document', args=[request_obj.id])}?copies=2",
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, 'class="print-sheet two-copies"')
        self.assert_material_slip_count(response, 2)
        self.assertContains(
            response,
            "grid-template-rows: minmax(0, 48%) minmax(0, 4%) minmax(0, 48%);",
        )
        self.assertContains(response, "height: 285mm;")
        self.assertContains(response, 'class="cut-line"', count=1)

    def test_bulk_material_print_forces_one_copy_only_for_oversized_requests(self):
        small_request = self.make_material_request(item_count=2, number_suffix="002")
        large_request = self.make_material_request(item_count=7, number_suffix="107")
        self.client.force_login(self.stock_user)

        response = self.client.post(
            f"{reverse('bulk_print_material_documents')}?copies=2",
            data={
                "selected_requests": [small_request.id, large_request.id],
            },
            HTTP_HOST="127.0.0.1",
        )

        self.assertContains(response, TWO_COPY_WARNING)
        self.assert_material_slip_count(response, 3)
        self.assertContains(response, 'class="print-sheet two-copies"', count=1)


class MaterialIssueNoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department = Department.objects.create(name="Field Services", code="FIELD")
        User = get_user_model()
        cls.requester = User.objects.create_user(
            username="note-requester",
            password="pass12345",
            email="note-requester@example.com",
            full_name="Note Requester",
            department=cls.department,
        )
        cls.approver = User.objects.create_user(
            username="note-approver",
            password="pass12345",
            email="note-approver@example.com",
            full_name="Note Approver",
        )
        cls.stock_manager = User.objects.create_user(
            username="note-stock-manager",
            password="pass12345",
            email="note-stock@example.com",
            full_name="Note Stock Manager",
            can_manage_stock=True,
        )
        cls.regular_user = User.objects.create_user(
            username="note-regular",
            password="pass12345",
            email="note-regular@example.com",
            full_name="Note Regular User",
        )
        cls.superuser = User.objects.create_superuser(
            username="note-superuser",
            password="pass12345",
            email="note-admin@example.com",
            full_name="Note Superuser",
        )
        cls.material_type = RequestType.objects.create(
            name="Material Request",
            code="NOTE-MATERIAL",
            requires_materials=True,
        )
        cls.non_material_type = RequestType.objects.create(
            name="Service Request",
            code="NOTE-SERVICE",
            requires_materials=False,
        )
        cls.category = MaterialCategory.objects.create(name="Network", code="NOTE-NET")
        cls.material = Material.objects.create(
            category=cls.category,
            name="Router",
            code="NOTE-ROUTER",
            unit="pcs",
            stock_quantity=5,
        )
        cls.request_obj = Request.objects.create(
            request_number="NOTE-001",
            request_type=cls.material_type,
            submitted_by=cls.requester,
            department=cls.department,
            description="Install customer router",
            status="APPROVED",
            finalized_at=timezone.now(),
            material_issue_note="SN-OLD",
        )
        RequestMaterialItem.objects.create(
            request=cls.request_obj,
            material=cls.material,
            quantity=1,
        )
        workflow = ApprovalWorkflow.objects.create(
            name="Note approval",
            request_type=cls.material_type,
            department=cls.department,
        )
        workflow_step = ApprovalWorkflowStep.objects.create(
            workflow=workflow,
            step_order=1,
            approver_user=cls.approver,
        )
        RequestApproval.objects.create(
            request=cls.request_obj,
            workflow_step=workflow_step,
            step_order=1,
            approver_user=cls.approver,
            acted_by=cls.approver,
            status="APPROVED",
            acted_at=timezone.now(),
        )

    def update_url(self, request_obj=None):
        request_obj = request_obj or self.request_obj
        return reverse("update_material_issue_note", args=[request_obj.id])

    def post_note(self, user, note, request_obj=None):
        self.client.force_login(user)
        return self.client.post(
            self.update_url(request_obj),
            {"material_issue_note": note},
            HTTP_HOST="127.0.0.1",
        )

    def test_stock_manager_can_add_and_edit_note_with_audit_log(self):
        self.request_obj.material_issue_note = ""
        self.request_obj.save(update_fields=["material_issue_note"])

        response = self.post_note(self.stock_manager, "SN-100")
        self.assertRedirects(
            response,
            reverse("request_detail", args=[self.request_obj.id]),
            fetch_redirect_response=False,
        )
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.material_issue_note, "SN-100")

        self.post_note(self.stock_manager, "SN-101; installed")
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.material_issue_note, "SN-101; installed")
        self.assertEqual(
            RequestAuditLog.objects.filter(
                request=self.request_obj,
                action="MATERIAL_ISSUE_NOTE_UPDATED",
                performed_by=self.stock_manager,
            ).count(),
            2,
        )

    def test_superuser_can_edit_note(self):
        self.post_note(self.superuser, "Updated by admin")
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.material_issue_note, "Updated by admin")

    def test_stock_manager_sees_edit_form_and_french_label(self):
        self.client.force_login(self.stock_manager)
        response = self.client.get(
            reverse("request_detail", args=[self.request_obj.id]),
            HTTP_ACCEPT_LANGUAGE="fr",
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(response, "Note de sortie matériel")
        self.assertContains(response, "Enregistrer la note")
        self.assertContains(response, "SN-OLD")

    def test_requester_can_view_note_but_not_edit(self):
        self.client.force_login(self.requester)
        response = self.client.get(
            reverse("request_detail", args=[self.request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(response, "SN-OLD")
        self.assertNotContains(response, "Save Note")
        self.assertEqual(self.post_note(self.requester, "Forbidden").status_code, 403)

    def test_approver_can_view_note_but_not_edit(self):
        self.client.force_login(self.approver)
        response = self.client.get(
            reverse("request_detail", args=[self.request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(response, "SN-OLD")
        self.assertNotContains(response, "Save Note")
        self.assertEqual(self.post_note(self.approver, "Forbidden").status_code, 403)

    def test_non_stock_user_cannot_post_update(self):
        response = self.post_note(self.regular_user, "Forbidden")
        self.assertEqual(response.status_code, 403)
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.material_issue_note, "SN-OLD")

    def test_non_approved_request_cannot_update_note(self):
        self.request_obj.status = "PENDING"
        self.request_obj.save(update_fields=["status"])
        response = self.post_note(self.stock_manager, "Forbidden")
        self.assertEqual(response.status_code, 302)
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.material_issue_note, "SN-OLD")

    def test_non_material_request_cannot_update_note(self):
        request_obj = Request.objects.create(
            request_number="NOTE-002",
            request_type=self.non_material_type,
            submitted_by=self.requester,
            department=self.department,
            description="Service only",
            status="APPROVED",
        )
        response = self.post_note(self.stock_manager, "Forbidden", request_obj)
        self.assertEqual(response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.material_issue_note, "")

    def test_update_endpoint_is_post_only(self):
        self.client.force_login(self.stock_manager)
        response = self.client.get(self.update_url(), HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 405)

    def test_note_appears_in_single_and_bulk_material_slips(self):
        self.client.force_login(self.stock_manager)
        single_response = self.client.get(
            reverse("approved_document", args=[self.request_obj.id]),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(single_response, "Material Issue Note")
        self.assertContains(single_response, "SN-OLD")

        bulk_response = self.client.post(
            reverse("bulk_print_material_documents"),
            {"selected_requests": [self.request_obj.id]},
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(bulk_response, "Material Issue Note")
        self.assertContains(bulk_response, "SN-OLD")

    def test_note_appears_in_material_report_and_excel_export(self):
        self.client.force_login(self.stock_manager)
        report_response = self.client.get(
            reverse("material_reports"),
            HTTP_HOST="127.0.0.1",
        )
        self.assertContains(report_response, "SN-OLD")

        excel_response = self.client.get(
            reverse("export_material_report_excel"),
            HTTP_HOST="127.0.0.1",
        )
        sheet = load_workbook(BytesIO(excel_response.content)).active
        self.assertEqual(sheet["N4"].value, "Material Issue Note")
        self.assertEqual(sheet["N5"].value, "SN-OLD")


class ReturnedMaterialRequestEditTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            name="Operations",
            code="OPS",
        )

        User = get_user_model()
        self.requester = User.objects.create_user(
            username="returned_requester",
            password="pass12345",
            email="returned-requester@example.com",
            full_name="Returned Requester",
            department=self.department,
        )
        self.approver = User.objects.create_user(
            username="returned_approver",
            password="pass12345",
            email="returned-approver@example.com",
            full_name="Returned Approver",
        )

        self.request_type = RequestType.objects.create(
            name="Material Request",
            code="RETURNED-MATERIAL",
            is_active=True,
            requires_materials=True,
        )
        self.workflow = ApprovalWorkflow.objects.create(
            name="Returned material approval",
            request_type=self.request_type,
            department=self.department,
            is_active=True,
        )
        self.workflow_step = ApprovalWorkflowStep.objects.create(
            workflow=self.workflow,
            step_order=1,
            approver_user=self.approver,
        )

        self.category = MaterialCategory.objects.create(
            name="Networking",
            code="NETWORKING",
        )
        self.existing_material = Material.objects.create(
            category=self.category,
            name="Ethernet Cable",
            code="ETH-CABLE",
            unit="roll",
            stock_quantity=10,
        )
        self.new_material = Material.objects.create(
            category=self.category,
            name="Network Switch",
            code="NET-SWITCH",
            unit="pcs",
            stock_quantity=8,
        )

        self.request_obj = Request.objects.create(
            request_number="REQ-RETURNED-MATERIAL",
            request_type=self.request_type,
            submitted_by=self.requester,
            department=self.department,
            description="Network installation",
            date_needed=timezone.localdate(),
            status="RETURNED",
        )
        self.existing_item = RequestMaterialItem.objects.create(
            request=self.request_obj,
            material=self.existing_material,
            quantity=2,
        )
        RequestApproval.objects.create(
            request=self.request_obj,
            workflow_step=self.workflow_step,
            step_order=1,
            approver_user=self.approver,
            status="RETURNED",
        )

        self.client.force_login(self.requester)

    def edit_url(self):
        return reverse("edit_request", args=[self.request_obj.id])

    def request_data(self):
        return {
            "request_type": self.request_type.id,
            "request_for_department": self.department.id,
            "description": "Corrected network installation",
            "date_needed": timezone.localdate().isoformat(),
        }

    def submission_token(self, url):
        response = self.client.get(url, HTTP_HOST="127.0.0.1")
        self.assertEqual(response.status_code, 200)
        return response.context["submission_token"]

    def test_edit_page_uses_shared_searchable_material_picker(self):
        response = self.client.get(
            self.edit_url(),
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="material-category-filter"')
        self.assertContains(response, 'class="material-search-field"')
        self.assertContains(response, 'id="add-material-btn"')
        self.assertContains(response, 'id="empty-material-template"')
        self.assertContains(response, 'name="material_items-TOTAL_FORMS"')
        self.assertContains(response, "Ethernet Cable")
        self.assertContains(response, "ETH-CABLE")
        self.assertContains(response, "Networking")
        self.assertContains(response, "Stock: 10.00 roll")

    def test_create_and_edit_pages_use_safe_material_formset_controls(self):
        for url in (reverse("create_request"), self.edit_url()):
            with self.subTest(url=url):
                response = self.client.get(url, HTTP_HOST="127.0.0.1")
                html = response.content.decode()

                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    '<button type="button" class="btn btn-secondary" id="add-material-btn">',
                    html,
                )
                self.assertIn(
                    '<button type="button" class="remove-material-btn">',
                    html,
                )
                self.assertIn('const initialForms = document.getElementById(', html)
                self.assertIn("deleteInput.checked = true;", html)
                self.assertIn("row.remove();", html)
                self.assertIn("totalForms.value = formIndex + 1;", html)
                self.assertNotIn("addMaterialRow();", html)

    def test_create_accepts_form_index_gap_left_by_removed_unsaved_rows(self):
        data = self.request_data()
        data["submission_token"] = self.submission_token(reverse("create_request"))
        data.update(
            {
                "material_items-TOTAL_FORMS": "3",
                "material_items-INITIAL_FORMS": "0",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-2-material": self.new_material.id,
                "material_items-2-quantity": "3",
            }
        )

        response = self.client.post(
            reverse("create_request"),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(response, reverse("dashboard"))
        created_request = Request.objects.exclude(id=self.request_obj.id).get()
        self.assertEqual(created_request.material_items.count(), 1)
        self.assertEqual(created_request.material_items.get().material, self.new_material)
        self.assertEqual(created_request.material_items.get().quantity, 3)

    def test_resubmit_can_remove_existing_item_and_add_new_item(self):
        data = self.request_data()
        data["action"] = "resubmit"
        data["submission_token"] = self.submission_token(self.edit_url())
        data.update(
            {
                "material_items-TOTAL_FORMS": "3",
                "material_items-INITIAL_FORMS": "1",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-id": self.existing_item.id,
                "material_items-0-material": self.existing_material.id,
                "material_items-0-quantity": "2",
                "material_items-0-DELETE": "on",
                "material_items-2-material": self.new_material.id,
                "material_items-2-quantity": "3",
            }
        )

        response = self.client.post(
            self.edit_url(),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(
            response,
            reverse("request_detail", args=[self.request_obj.id]),
            fetch_redirect_response=False,
        )

        self.request_obj.refresh_from_db()
        self.existing_material.refresh_from_db()
        self.new_material.refresh_from_db()

        self.assertEqual(self.request_obj.status, "IN_REVIEW")
        self.assertEqual(self.request_obj.material_items.count(), 1)
        self.assertEqual(
            self.request_obj.material_items.get().material,
            self.new_material,
        )
        self.assertEqual(self.request_obj.material_items.get().quantity, 3)
        self.assertEqual(self.request_obj.approvals.count(), 1)
        self.assertEqual(self.request_obj.approvals.get().status, "PENDING")
        self.assertEqual(self.existing_material.stock_quantity, 10)
        self.assertEqual(self.new_material.stock_quantity, 8)
        self.assertFalse(self.request_obj.stock_deducted)

    def test_resubmit_rejects_removing_all_material_items(self):
        data = self.request_data()
        data["action"] = "resubmit"
        data["submission_token"] = self.submission_token(self.edit_url())
        data.update(
            {
                "material_items-TOTAL_FORMS": "1",
                "material_items-INITIAL_FORMS": "1",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-id": self.existing_item.id,
                "material_items-0-material": self.existing_material.id,
                "material_items-0-quantity": "2",
                "material_items-0-DELETE": "on",
            }
        )

        response = self.client.post(
            self.edit_url(),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "At least one material is required")
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.status, "RETURNED")
        self.assertEqual(self.request_obj.material_items.count(), 1)

    def test_resubmit_rejects_duplicate_material_rows(self):
        data = self.request_data()
        data["action"] = "resubmit"
        data["submission_token"] = self.submission_token(self.edit_url())
        data.update(
            {
                "material_items-TOTAL_FORMS": "2",
                "material_items-INITIAL_FORMS": "1",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-id": self.existing_item.id,
                "material_items-0-material": self.existing_material.id,
                "material_items-0-quantity": "2",
                "material_items-1-material": self.existing_material.id,
                "material_items-1-quantity": "1",
            }
        )

        response = self.client.post(
            self.edit_url(),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Duplicate material rows are not allowed.")
        self.request_obj.refresh_from_db()
        self.assertEqual(self.request_obj.status, "RETURNED")
        self.assertEqual(self.request_obj.material_items.count(), 1)

    def test_resubmit_rejects_quantity_above_available_stock(self):
        data = self.request_data()
        data["action"] = "resubmit"
        data["submission_token"] = self.submission_token(self.edit_url())
        data.update(
            {
                "material_items-TOTAL_FORMS": "2",
                "material_items-INITIAL_FORMS": "1",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-id": self.existing_item.id,
                "material_items-0-material": self.existing_material.id,
                "material_items-0-quantity": "11",
            }
        )

        response = self.client.post(
            self.edit_url(),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only 10.00 roll available in stock.")
        self.assertContains(
            response,
            f'href="{reverse("request_detail", args=[self.request_obj.id])}"',
        )

        self.request_obj.refresh_from_db()
        self.existing_item.refresh_from_db()
        self.assertEqual(self.request_obj.status, "RETURNED")
        self.assertEqual(self.existing_item.quantity, 2)
        self.assertEqual(self.request_obj.approvals.get().status, "RETURNED")

    def test_reused_create_token_does_not_duplicate_request_items_or_approvals(self):
        data = self.request_data()
        data["action"] = "submit"
        data.update(
            {
                "submission_token": self.submission_token(reverse("create_request")),
                "material_items-TOTAL_FORMS": "1",
                "material_items-INITIAL_FORMS": "0",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-material": self.new_material.id,
                "material_items-0-quantity": "2",
            }
        )

        first_response = self.client.post(
            reverse("create_request"), data=data, HTTP_HOST="127.0.0.1"
        )
        created = Request.objects.exclude(id=self.request_obj.id).get()
        second_response = self.client.post(
            reverse("create_request"), data=data, HTTP_HOST="127.0.0.1"
        )

        self.assertRedirects(first_response, reverse("dashboard"))
        self.assertRedirects(
            second_response,
            reverse("request_detail", args=[created.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(Request.objects.exclude(id=self.request_obj.id).count(), 1)
        self.assertEqual(created.material_items.count(), 1)
        self.assertEqual(created.approvals.count(), 1)

    def test_reused_resubmit_token_only_resubmits_once(self):
        data = self.request_data()
        data["action"] = "resubmit"
        data.update(
            {
                "submission_token": self.submission_token(self.edit_url()),
                "material_items-TOTAL_FORMS": "1",
                "material_items-INITIAL_FORMS": "1",
                "material_items-MIN_NUM_FORMS": "0",
                "material_items-MAX_NUM_FORMS": "1000",
                "material_items-0-id": self.existing_item.id,
                "material_items-0-material": self.existing_material.id,
                "material_items-0-quantity": "2",
            }
        )

        self.client.post(self.edit_url(), data=data, HTTP_HOST="127.0.0.1")
        duplicate_response = self.client.post(
            self.edit_url(), data=data, HTTP_HOST="127.0.0.1"
        )

        self.assertRedirects(
            duplicate_response,
            reverse("request_detail", args=[self.request_obj.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(self.request_obj.approvals.count(), 1)
        self.assertEqual(self.request_obj.material_items.count(), 1)
        self.assertEqual(
            RequestAuditLog.objects.filter(
                request=self.request_obj, action="RESUBMITTED"
            ).count(),
            1,
        )

    def test_user_can_save_draft_without_approval_steps(self):
        data = {
            "action": "save_draft",
            "submission_token": self.submission_token(reverse("create_request")),
            "request_type": self.request_type.id,
            "request_for_department": self.department.id,
            "description": "",
            "date_needed": "",
            "material_items-TOTAL_FORMS": "2",
            "material_items-INITIAL_FORMS": "0",
            "material_items-MIN_NUM_FORMS": "0",
            "material_items-MAX_NUM_FORMS": "1000",
            "material_items-0-material": self.existing_material.id,
            "material_items-0-quantity": "",
        }

        response = self.client.post(
            reverse("create_request"),
            data=data,
            HTTP_HOST="127.0.0.1",
        )

        draft = Request.objects.exclude(id=self.request_obj.id).get()
        self.assertRedirects(
            response,
            reverse("request_detail", args=[draft.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(draft.status, "DRAFT")
        self.assertEqual(draft.approvals.count(), 0)
        self.assertEqual(draft.material_items.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

        self.client.force_login(self.approver)
        pending_response = self.client.get(
            reverse("pending_approvals"),
            HTTP_HOST="127.0.0.1",
        )
        self.assertNotContains(pending_response, draft.request_number)

        self.client.force_login(self.requester)
        my_response = self.client.get(reverse("my_requests"), HTTP_HOST="127.0.0.1")
        self.assertContains(my_response, draft.request_number)
        self.assertContains(my_response, "Draft")

    def test_user_can_edit_and_submit_draft_later(self):
        draft = Request.objects.create(
            request_number="REQ-DRAFT-SUBMIT",
            request_type=self.request_type,
            submitted_by=self.requester,
            department=self.department,
            request_for_department=self.department,
            description="Draft material request",
            status="DRAFT",
        )
        edit_url = reverse("edit_request", args=[draft.id])
        data = {
            **self.request_data(),
            "action": "submit",
            "submission_token": self.submission_token(edit_url),
            "material_items-TOTAL_FORMS": "1",
            "material_items-INITIAL_FORMS": "0",
            "material_items-MIN_NUM_FORMS": "0",
            "material_items-MAX_NUM_FORMS": "1000",
            "material_items-0-material": self.new_material.id,
            "material_items-0-quantity": "2",
        }

        response = self.client.post(edit_url, data=data, HTTP_HOST="127.0.0.1")

        self.assertRedirects(
            response,
            reverse("request_detail", args=[draft.id]),
            fetch_redirect_response=False,
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, "IN_REVIEW")
        self.assertEqual(draft.approvals.count(), 1)
        self.assertEqual(draft.material_items.count(), 1)

    def test_requester_can_cancel_open_request_and_blocks_direct_approval(self):
        request_obj = Request.objects.create(
            request_number="REQ-CANCEL-OPEN",
            request_type=self.request_type,
            submitted_by=self.requester,
            department=self.department,
            request_for_department=self.department,
            description="Open request to cancel",
            status="PENDING",
        )
        RequestMaterialItem.objects.create(
            request=request_obj,
            material=self.existing_material,
            quantity=2,
        )
        submit_request(request_obj)
        approval = request_obj.approvals.get(status="PENDING")
        self.client.force_login(self.requester)

        response = self.client.post(
            reverse("cancel_request", args=[request_obj.id]),
            data={"next": reverse("request_detail", args=[request_obj.id])},
            HTTP_HOST="127.0.0.1",
        )

        self.assertRedirects(
            response,
            reverse("request_detail", args=[request_obj.id]),
            fetch_redirect_response=False,
        )
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "CANCELLED")
        self.assertIsNone(request_obj.current_step_order)
        self.assertTrue(
            RequestAuditLog.objects.filter(
                request=request_obj,
                action="CANCELLED",
                performed_by=self.requester,
            ).exists()
        )
        self.existing_material.refresh_from_db()
        self.assertEqual(self.existing_material.stock_quantity, 10)

        self.client.force_login(self.approver)
        approval_response = self.client.post(
            reverse("approval_detail", args=[approval.id]),
            data={"action": "APPROVE", "comment": ""},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(approval_response.status_code, 302)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "CANCELLED")
        approval.refresh_from_db()
        self.assertEqual(approval.status, "PENDING")

        pending_response = self.client.get(
            reverse("pending_approvals"),
            HTTP_HOST="127.0.0.1",
        )
        self.assertNotContains(pending_response, request_obj.request_number)

    def test_requester_cannot_cancel_approved_request(self):
        request_obj = Request.objects.create(
            request_number="REQ-CANCEL-APPROVED",
            request_type=self.request_type,
            submitted_by=self.requester,
            department=self.department,
            request_for_department=self.department,
            description="Approved request to cancel",
            status="PENDING",
        )
        RequestMaterialItem.objects.create(
            request=request_obj,
            material=self.existing_material,
            quantity=2,
        )
        submit_request(request_obj)
        approval = request_obj.approvals.get(status="PENDING")
        approve_step(approval, self.approver)
        request_obj.refresh_from_db()
        self.client.force_login(self.requester)

        self.client.post(
            reverse("cancel_request", args=[request_obj.id]),
            data={"next": reverse("request_detail", args=[request_obj.id])},
            HTTP_HOST="127.0.0.1",
        )

        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, "APPROVED")

    def test_non_owner_cannot_cancel_but_superuser_can(self):
        User = get_user_model()
        other_user = User.objects.create_user(
            username="cancel_other",
            password="pass12345",
            full_name="Cancel Other",
            department=self.department,
        )
        admin = User.objects.create_user(
            username="cancel_admin",
            password="pass12345",
            full_name="Cancel Admin",
            department=self.department,
            is_superuser=True,
            is_staff=True,
        )
        draft = Request.objects.create(
            request_number="REQ-DRAFT-CANCEL",
            request_type=self.request_type,
            submitted_by=self.requester,
            department=self.department,
            request_for_department=self.department,
            description="Draft to cancel",
            status="DRAFT",
        )

        self.client.force_login(other_user)
        forbidden = self.client.post(
            reverse("cancel_request", args=[draft.id]),
            data={"next": reverse("request_detail", args=[draft.id])},
            HTTP_HOST="127.0.0.1",
        )
        self.assertEqual(forbidden.status_code, 403)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "DRAFT")

        self.client.force_login(admin)
        self.client.post(
            reverse("cancel_request", args=[draft.id]),
            data={"next": reverse("request_detail", args=[draft.id])},
            HTTP_HOST="127.0.0.1",
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, "CANCELLED")


class OptionalPermissionTimeTests(TestCase):
    def setUp(self):
        self.department = Department.objects.create(name="Permissions", code="PERM")
        User = get_user_model()
        self.requester = User.objects.create_user(
            username="optional-time-requester",
            password="pass12345",
            department=self.department,
        )
        self.approver = User.objects.create_user(
            username="optional-time-approver",
            password="pass12345",
        )
        self.request_type = RequestType.objects.create(
            name="General Permission",
            code="OPTIONAL-TIMES",
            is_active=True,
            is_permission_request=True,
        )
        workflow = ApprovalWorkflow.objects.create(
            name="Permission approval",
            request_type=self.request_type,
            department=self.department,
            is_active=True,
        )
        ApprovalWorkflowStep.objects.create(
            workflow=workflow,
            step_order=1,
            approver_user=self.approver,
        )

    def permission_form(self, **times):
        data = {
            "request_type": self.request_type.id,
            "request_for_department": self.department.id,
            "date_needed": timezone.localdate().isoformat(),
            "permission_group": "LEAVE_PERMISSION",
            "permission_subgroup": "BY_FOOT",
            "destination": "Office",
            "exit_reason": "Appointment",
        }
        data.update(times)
        return RequestForm(data=data)

    def test_departure_time_is_optional(self):
        form = self.permission_form(return_time="14:00")
        self.assertTrue(form.is_valid(), form.errors)

    def test_return_time_is_optional(self):
        form = self.permission_form(departure_time="10:00")
        self.assertTrue(form.is_valid(), form.errors)

    def test_both_leave_times_are_optional(self):
        form = self.permission_form()
        self.assertTrue(form.is_valid(), form.errors)

    def test_by_car_arrival_time_and_driver_are_optional(self):
        form = self.permission_form(permission_subgroup="BY_CAR")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("arrival_time", form.errors)
        self.assertNotIn("driver_name", form.errors)

    def test_by_car_request_submits_with_all_travel_fields_blank(self):
        self.client.force_login(self.requester)
        get_response = self.client.get(
            reverse("create_request"), HTTP_HOST="127.0.0.1"
        )
        data = {
            "submission_token": get_response.context["submission_token"],
            "request_type": self.request_type.id,
            "request_for_department": self.department.id,
            "date_needed": timezone.localdate().isoformat(),
            "permission_group": "LEAVE_PERMISSION",
            "permission_subgroup": "BY_CAR",
            "destination": "Office",
            "exit_reason": "Appointment",
        }

        response = self.client.post(
            reverse("create_request"), data=data, HTTP_HOST="127.0.0.1"
        )

        self.assertRedirects(response, reverse("dashboard"))
        request_obj = Request.objects.get(submitted_by=self.requester)
        self.assertIsNone(request_obj.metadata_json["departure_time"])
        self.assertIsNone(request_obj.metadata_json["return_time"])
        self.assertIsNone(request_obj.metadata_json["arrival_time"])
        self.assertFalse(request_obj.metadata_json["driver_name"])
        self.assertEqual(request_obj.approvals.count(), 1)

    def test_by_foot_request_submits_with_departure_and_return_blank(self):
        self.client.force_login(self.requester)
        get_response = self.client.get(
            reverse("create_request"), HTTP_HOST="127.0.0.1"
        )
        data = {
            "submission_token": get_response.context["submission_token"],
            "request_type": self.request_type.id,
            "request_for_department": self.department.id,
            "date_needed": timezone.localdate().isoformat(),
            "permission_group": "LEAVE_PERMISSION",
            "permission_subgroup": "BY_FOOT",
            "destination": "Office",
            "exit_reason": "Appointment",
        }

        response = self.client.post(
            reverse("create_request"), data=data, HTTP_HOST="127.0.0.1"
        )

        self.assertRedirects(response, reverse("dashboard"))
        request_obj = Request.objects.get(submitted_by=self.requester)
        self.assertIsNone(request_obj.metadata_json["departure_time"])
        self.assertIsNone(request_obj.metadata_json["return_time"])
        self.assertEqual(request_obj.approvals.count(), 1)

    def test_travel_fields_are_not_html_required(self):
        form = self.permission_form(permission_subgroup="BY_CAR")
        for field_name in (
            "departure_time",
            "return_time",
            "arrival_time",
            "driver_name",
        ):
            with self.subTest(field=field_name):
                self.assertFalse(form.fields[field_name].required)
                self.assertNotIn("required", str(form[field_name]))


class AdministrationReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.administration = Department.objects.create(code="ADMIN", name="Administration")
        cls.technique = Department.objects.create(code="TECH", name="Technique")
        cls.reporter = User.objects.create_user(username="report-reader", can_view_administration_reports=True)
        cls.submitter = User.objects.create_user(username="alice", full_name="Alice Example", first_name="Alice", last_name="Example", department=cls.technique)
        cls.general = RequestType.objects.create(code="AUTORISATION_GENERAL", name="Autorisation Générale")
        cls.approved = Request.objects.create(request_number="ADMIN-001", request_type=cls.general, submitted_by=cls.submitter,
            department=cls.technique, request_for_department=cls.administration, description="Office renovation", status="APPROVED", finalized_at=timezone.now())

    def setUp(self):
        self.client.force_login(self.reporter)

    def report(self, **params):
        return self.client.get(reverse("administration_reports"), params)

    def create_request(self, **changes):
        data = dict(request_number="OTHER-" + str(Request.objects.count()), request_type=self.general,
                    submitted_by=self.submitter, department=self.technique, request_for_department=self.administration,
                    description="Other request", status="APPROVED")
        data.update(changes)
        return Request.objects.create(**data)

    def test_permission_and_navigation(self):
        self.assertContains(self.report(), reverse("administration_reports"))
        self.client.force_login(self.submitter)
        self.assertEqual(self.report().status_code, 403)
        self.assertEqual(self.client.get(reverse("administration_report_document", args=[self.approved.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("dashboard")), reverse("administration_reports"))
        for flags in ({"is_staff": True}, {"department": self.administration}):
            for key, value in flags.items():
                setattr(self.submitter, key, value)
            self.submitter.save()
            self.assertEqual(self.report().status_code, 403)
        self.submitter.is_superuser = True
        self.submitter.save()
        self.assertEqual(self.report().status_code, 200)

    def test_scope_and_statuses(self):
        excluded = [self.create_request(status=status) for status in
                    ("DRAFT", "PENDING", "IN_REVIEW", "RETURNED", "REJECTED", "CANCELLED")]
        for code, flags in (("MATERIAL", {"requires_materials": True}), ("PERMISSION", {"is_permission_request": True}), ("PAYMENT", {"requires_amount": True})):
            excluded.append(self.create_request(request_type=RequestType.objects.create(code=code, name=code, **flags)))
        response = self.report()
        self.assertEqual(list(response.context["requests"]), [self.approved])
        for obj in excluded:
            with self.subTest(request=obj.request_number):
                self.assertEqual(self.client.get(reverse("administration_report_document", args=[obj.pk])).status_code, 404)
        # Query parameters cannot widen the approved request-type scope.
        self.assertEqual(list(self.report(request_type="PAYMENT", status="DRAFT").context["requests"]), [self.approved])

    def test_document_and_copy_links_reuse_existing_renderer(self):
        url = reverse("administration_report_document", args=[self.approved.pk])
        for copies in ("1", "2", "invalid"):
            response = self.client.get(url, {"copies": copies, "next": "//example.com"})
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "requests_app/approved_document.html")
            self.assertContains(response, url + "?copies=1")
            self.assertContains(response, url + "?copies=2")
            self.assertContains(response, "window.print()")
            self.assertEqual(response.context["back_url"], reverse("administration_reports"))
            self.assertNotContains(response, reverse("approved_document", args=[self.approved.pk]))

    def test_normal_visibility_and_mutation_remain_denied(self):
        self.assertNotContains(self.client.get(reverse("my_requests")), self.approved.request_number)
        for name in ("request_detail", "approved_document"):
            self.assertEqual(self.client.get(reverse(name, args=[self.approved.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("edit_request", args=[self.approved.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("cancel_request", args=[self.approved.pk])).status_code, 403)
        pending = self.create_request(status="PENDING")
        workflow = ApprovalWorkflow.objects.create(name="Report security workflow", request_type=self.general, department=self.administration)
        step = ApprovalWorkflowStep.objects.create(workflow=workflow, step_order=1, approver_user=self.submitter)
        approval = RequestApproval.objects.create(request=pending, workflow_step=step, step_order=1, approver_user=self.submitter, status="PENDING")
        for action in ("approve", "reject", "return"):
            response = self.client.post(reverse("approval_detail", args=[approval.pk]), {"action": action, "comment": "Denied"})
            self.assertEqual(response.status_code, 404)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "PENDING")
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, "APPROVED")

    def test_search_and_filters(self):
        for query in ("admin-001", "alice", "example", "renovation"):
            self.assertEqual(list(self.report(q=query).context["requests"]), [self.approved])
        self.assertEqual(list(self.report(department=self.technique.pk, requester=self.submitter.pk).context["requests"]), [self.approved])
        today = timezone.localdate().isoformat()
        self.assertEqual(list(self.report(date_from=today, date_to=today).context["requests"]), [self.approved])
        for params in ({"department": self.administration.pk}, {"date_from": "2999-01-01"}, {"date_to": "2000-01-01"}, {"date_from": "2026-02-31"}, {"department": "bad"}, {"requester": "bad"}, {"q": "missing"}):
            self.assertContains(self.report(**params), "No approved Administration requests found.")

    def test_pagination_preserves_filters(self):
        for i in range(26):
            self.create_request(description="Office renovation")
        response = self.report(q="Office", department=self.technique.pk, request_for_department=self.administration.pk)
        self.assertEqual(len(response.context["requests"]), 25)
        self.assertContains(response, "q=Office&amp;department=" + str(self.technique.pk))
        self.assertContains(response, "request_for_department=" + str(self.administration.pk))
        self.assertEqual(len(self.report(q="Office", page=2).context["requests"]), 2)

    def test_french(self):
        self.client.cookies["django_language"] = "fr"
        response = self.report(q="missing")
        self.assertContains(response, "Rapport Administration")
        self.assertContains(response, "Aucune demande Administration approuv\u00e9e trouv\u00e9e.")


    def test_configured_request_type_fails_closed(self):
        from django.test import override_settings
        with override_settings(ADMINISTRATION_REPORT_REQUEST_TYPE_CODE="missing"):
            self.assertEqual(list(self.report().context["requests"]), [])
            self.assertEqual(self.client.get(reverse("administration_report_document", args=[self.approved.pk])).status_code, 404)

    def test_all_departments_and_document_access(self):
        finance = Department.objects.create(code="FIN", name="Finance")
        qualified = [self.approved]
        for source, destination in ((self.technique, self.technique), (self.administration, self.technique), (finance, finance)):
            qualified.append(self.create_request(department=source, request_for_department=destination))
        self.assertCountEqual(list(self.report().context["requests"]), qualified)
        for obj in qualified:
            for copies in ("1", "2"):
                with self.subTest(request=obj.pk, copies=copies):
                    response = self.client.get(reverse("administration_report_document", args=[obj.pk]), {"copies": copies})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, "window.print()")
                    self.assertTemplateUsed(response, "requests_app/approved_document.html")
        self.assertCountEqual(list(self.report(request_for_department=self.technique.pk).context["requests"]), qualified[1:3])
        self.assertEqual(list(self.report(department=finance.pk, request_for_department=finance.pk).context["requests"]), [qualified[3]])
        self.assertEqual(list(self.report(department=self.administration.pk, request_for_department=self.administration.pk).context["requests"]), [])
        self.assertEqual(list(self.report(request_for_department="bad").context["requests"]), [])

    def test_membership_depends_only_on_status_and_type_code(self):
        self.general.requires_materials = True
        self.general.is_permission_request = True
        self.general.save()
        self.assertEqual(list(self.report().context["requests"]), [self.approved])
        self.assertEqual(self.client.get(reverse("administration_report_document", args=[self.approved.pk])).status_code, 200)

    def test_anonymous_access_requires_login(self):
        self.client.logout()
        self.assertEqual(self.report().status_code, 302)
        self.assertEqual(self.client.get(reverse("administration_report_document", args=[self.approved.pk])).status_code, 302)


    def test_newest_submission_first_with_filters(self):
        from datetime import timedelta
        now = timezone.now()
        # Insert newest before middle; approval times intentionally disagree.
        newest = self.create_request(description="Ordering check", finalized_at=now - timedelta(days=3))
        middle = self.create_request(description="Ordering check", finalized_at=now - timedelta(days=2))
        oldest = self.approved
        Request.objects.filter(pk=oldest.pk).update(submitted_at=now - timedelta(days=3), description="Ordering check", finalized_at=now)
        Request.objects.filter(pk=middle.pk).update(submitted_at=now - timedelta(days=2))
        Request.objects.filter(pk=newest.pk).update(submitted_at=now - timedelta(days=1))
        expected = [newest.pk, middle.pk, oldest.pk]
        for filters in ({}, {"q": "Ordering check"}, {"department": self.technique.pk},
                        {"request_for_department": self.administration.pk}, {"requester": self.submitter.pk}):
            with self.subTest(filters=filters):
                response = self.report(**filters)
                self.assertEqual([obj.pk for obj in response.context["requests"]], expected)

    def test_submission_order_ties_and_pagination(self):
        from datetime import timedelta
        now = timezone.now()
        Request.objects.filter(pk=self.approved.pk).update(submitted_at=now - timedelta(days=1))
        tied = [self.create_request() for _ in range(26)]
        Request.objects.filter(pk__in=[obj.pk for obj in tied]).update(submitted_at=now)
        expected = sorted([obj.pk for obj in tied], reverse=True) + [self.approved.pk]
        first = self.report(department=self.technique.pk)
        second = self.report(department=self.technique.pk, page=2)
        self.assertEqual([obj.pk for obj in first.context["requests"]], expected[:25])
        self.assertEqual([obj.pk for obj in second.context["requests"]], expected[25:])
