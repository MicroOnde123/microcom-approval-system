from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from urllib.parse import quote

from accounts.models import Department
from inventory.models import Material, MaterialCategory
from requests_app.models import Request, RequestApproval, RequestMaterialItem, RequestType
from requests_app.services import submit_request
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep


TWO_COPY_WARNING = (
    "This request has too many material items for two-copy printing. "
    "Please print one copy."
)


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
