from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Department
from requests_app.models import Request, RequestApproval, RequestType
from requests_app.services import submit_request
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep


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
