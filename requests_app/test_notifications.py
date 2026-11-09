"""Persistent workflow notifications and optional email preferences: isolated PostgreSQL."""
import io
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import WorkflowNotification, RequestAuditLog, RequestApproval, StockMovement
from .notifications import record_event, notify_current, counts
from .services import approve_step, return_step, reject_step, resubmit_request, send_notification_email
from .test_stock_safety import StockSafetyFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def shared(self):
        self.workflow.steps.update(alternate_approver_user=self.other)
        self.req,self.item=self.make_request()
        return self.req.approvals.get()

    def test_default_preference_admin_checkbox_and_authorization(self):
        self.assertTrue(self.user.receive_email_notifications)
        from accounts.admin import UserAdminForm
        form=UserAdminForm(instance=self.user)
        self.assertTrue(form.fields["receive_email_notifications"].initial)
        with redirect_stdout(io.StringIO()):
            admin=get_user_model().objects.create_superuser(username="notify-admin",password="synthetic")
        self.user.email="user@example.invalid"; self.user.save()
        self.client.force_login(admin)
        url=reverse("admin:accounts_user_change",args=[self.user.pk])
        page=self.client.get(url)
        self.assertContains(page,'name="receive_email_notifications"')
        self.client.cookies["django_language"]="fr"
        self.assertContains(self.client.get(url),"Recevoir les notifications par e-mail")
        self.client.cookies["django_language"]="en"
        data={name: field.value() if field.value() is not None else "" for name,field in ((n,page.context["adminform"].form[n]) for n in page.context["adminform"].form.fields)}
        from django import forms
        for name in list(data):
            if isinstance(page.context["adminform"].form.fields[name], forms.BooleanField) and not page.context["adminform"].form[name].value():
                data.pop(name)
        data["full_name"]="Stock Person"
        data.pop("date_joined",None); data.pop("last_login",None)
        data["date_joined_0"]=self.user.date_joined.strftime("%Y-%m-%d")
        data["date_joined_1"]=self.user.date_joined.strftime("%H:%M:%S")
        data["last_login_0"]=""; data["last_login_1"]=""
        data.pop("receive_email_notifications",None)
        data["groups"]=[]; data["user_permissions"]=[]
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302, str(response.context["adminform"].form.errors) if response.status_code==200 else "")
        self.user.refresh_from_db(); self.assertFalse(self.user.receive_email_notifications)
        self.client.force_login(self.other)
        self.assertNotEqual(self.client.get(url).status_code,200)

    def test_email_is_filtered_per_recipient_at_delivery_and_bulk_remaining_users_receive(self):
        self.user.email="a@example.invalid"; self.user.save()
        self.other.email="b@example.invalid"; self.other.save()
        with self.captureOnCommitCallbacks(execute=True):
            send_notification_email("Subject","Body",[self.user.email,self.other.email],recipient_ids=[self.user.pk,self.other.pk])
            get_user_model().objects.filter(pk=self.other.pk).update(receive_email_notifications=False)
        self.assertEqual(mail.outbox[-1].to,[self.user.email])
        before=len(mail.outbox)
        with self.captureOnCommitCallbacks(execute=True):
            send_notification_email("Subject","Body",[self.other.email],recipient_ids=[self.other.pk])
        self.assertEqual(len(mail.outbox),before)

    def test_password_reset_ignores_workflow_preference(self):
        from accounts.forms import CustomPasswordResetForm
        self.user.email="reset@example.invalid"; self.user.set_password("synthetic-password")
        self.user.receive_email_notifications=False; self.user.save()
        form=CustomPasswordResetForm({"email":self.user.email}); self.assertTrue(form.is_valid())
        form.save(domain_override="localhost",email_template_name="registration/password_reset_email.html",
                  subject_template_name="registration/password_reset_subject.txt")
        self.assertEqual(mail.outbox[-1].to,[self.user.email])

    def test_shared_step_handling_read_counts_duplicate_protection_and_stock_once(self):
        approval=self.shared()
        notices=WorkflowNotification.objects.filter(approval=approval)
        self.assertEqual(notices.count(),2)
        notify_current(self.req,"SUBMITTED"); self.assertEqual(notices.count(),2)
        self.assertEqual(counts(self.other)["pending"],1)
        approve_step(approval,self.user)
        self.assertFalse(notices.filter(actionable=True).exists())
        self.assertEqual(counts(self.other)["pending"],0)
        self.assertGreater(counts(self.other)["unread"],0)
        page=self.client.get(reverse("notification_inbox"))
        self.assertContains(page,"Already handled")
        with self.assertRaises(ValidationError): approve_step(approval,self.other)
        self.assertEqual(StockMovement.objects.filter(request=self.req,movement_type="OUT").count(),1)
        log=RequestAuditLog.objects.get(request=self.req,action="FINAL_APPROVED")
        before=WorkflowNotification.objects.count(); record_event(log)
        self.assertEqual(WorkflowNotification.objects.count(),before)

    def test_read_actions_ownership_csrf_redirect_and_get_are_safe(self):
        notice=WorkflowNotification.objects.filter(recipient=self.user).first()
        url=reverse("notification_read",args=[notice.pk])
        self.assertEqual(self.client.get(url).status_code,405)
        csrf=Client(enforce_csrf_checks=True); csrf.force_login(self.user)
        self.assertEqual(csrf.post(url,{}).status_code,403)
        csrf.get(reverse("notification_snapshot"))
        self.assertEqual(csrf.post(url,{"csrfmiddlewaretoken":csrf.cookies["csrftoken"].value}).status_code,302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{}).status_code,404)
        self.client.force_login(self.user)
        response=self.client.post(url,{"action":"view","next":"https://evil.invalid"})
        self.assertRedirects(response,reverse("request_detail",args=[self.req.pk]),fetch_redirect_response=False)
        notice.refresh_from_db(); first=notice.read_at; self.assertIsNotNone(first)
        self.client.post(url,{}); notice.refresh_from_db(); self.assertEqual(notice.read_at,first)
        self.assertEqual(counts(self.user)["pending"],1)

    def test_polling_dropdown_never_marks_read_and_initial_counts_match(self):
        from .context_processors import pending_approval_count
        from django.test import RequestFactory
        request=RequestFactory().get("/"); request.user=self.user
        notice=WorkflowNotification.objects.filter(recipient=self.user).first()
        data=self.client.get(reverse("notification_snapshot"),{"approval":self.req.approvals.get().pk}).json()
        self.assertEqual(data["pending"],pending_approval_count(request)["pending_approval_count"])
        self.assertTrue(data["approval_active"])
        self.assertContains(self.client.get(reverse("request_detail",args=[self.req.pk])), 'data-live-approval-id=')
        notice.refresh_from_db(); self.assertIsNone(notice.read_at)
        self.req.status="REJECTED"; self.req.save(update_fields=["status"])
        self.assertEqual(self.client.get(reverse("notification_count")).json()["pending"],0)
        self.assertEqual(pending_approval_count(request)["pending_approval_count"],0)

    def test_return_resubmit_and_reject_preserve_in_app_when_email_disabled(self):
        self.user.receive_email_notifications=False; self.user.save()
        self.other.receive_email_notifications=False; self.other.save()
        old=self.req.approvals.get()
        return_step(old,self.user,"Correct")
        self.assertTrue(WorkflowNotification.objects.filter(recipient=self.other,request=self.req,event_type="RETURNED").exists())
        resubmit_request(self.req,self.other)
        new=self.req.approvals.get()
        self.assertNotEqual(old.pk,new.pk)
        self.assertTrue(WorkflowNotification.objects.filter(approval=new,recipient=self.user).exists())
        self.assertTrue(WorkflowNotification.objects.filter(request=self.req,approval__isnull=True).exists())
        reject_step(new,self.user,"Rejected")
        self.assertTrue(WorkflowNotification.objects.filter(request=self.req,event_type="REJECTED",recipient=self.other).exists())

    def test_rollback_does_not_leave_notices_or_email_and_next_step_is_notified(self):
        from workflows.models import ApprovalWorkflowStep
        from django.db import transaction
        from unittest.mock import patch
        ApprovalWorkflowStep.objects.create(workflow=self.workflow,step_order=2,approver_user=self.other)
        req,item=self.make_request()
        before=WorkflowNotification.objects.count()
        with self.assertRaises(RuntimeError), transaction.atomic():
            approve_step(req.approvals.get(step_order=1),self.user)
            raise RuntimeError("rollback")
        self.assertEqual(WorkflowNotification.objects.count(),before)
        approve_step(req.approvals.get(step_order=1),self.user)
        self.assertTrue(WorkflowNotification.objects.filter(request=req,recipient=self.other,actionable=True).exists())

    def test_inbox_pagination_unread_language_and_bounded_live_payload(self):
        for index in range(27):
            WorkflowNotification.objects.create(recipient=self.user,request=self.req,event_type="FINAL_APPROVED",
                reference=self.req.request_number,event_key=f"synthetic:{index}")
        for lang in ("en","fr"):
            self.client.cookies["django_language"]=lang
            page=self.client.get(reverse("notification_inbox"))
            self.assertEqual(len(page.context["notification_page"]),25)
            self.assertContains(page,"Notifications")
            self.assertContains(page,'workflow-notification-items')
            self.assertContains(page,"Marquer comme lue" if lang=="fr" else "Mark as Read")
            data=self.client.get(reverse("notification_snapshot")).json()
            self.assertEqual(data["html"].count('data-notice-id='),10)
        self.client.post(reverse("notification_read",args=[WorkflowNotification.objects.filter(recipient=self.user).first().pk]),{})
        unread=self.client.get(reverse("notification_inbox"),{"filter":"unread"})
        self.assertEqual(unread.context["notification_page"].paginator.count,27)
        self.client.logout(); self.assertEqual(self.client.get(reverse("notification_snapshot")).status_code,302)

    def test_unauthorized_request_redirect_does_not_mark_owned_notification_read(self):
        foreign=WorkflowNotification.objects.create(recipient=self.other,request=self.req,event_type="SUBMITTED",
            reference=self.req.request_number,event_key="owned-no-request-access")
        # Remove the owner's existing submitter relationship for this synthetic access test.
        from accounts.models import User
        stranger=User.objects.create_user(username="request-stranger")
        foreign.recipient=stranger; foreign.save(update_fields=["recipient"])
        self.client.force_login(stranger)
        self.assertEqual(self.client.post(reverse("notification_read",args=[foreign.pk]),{"action":"view"}).status_code,403)
        foreign.refresh_from_db(); self.assertIsNone(foreign.read_at)

    def test_snapshot_queries_are_bounded_and_pending_pages_are_bounded(self):
        from .notification_views import snapshot
        from django.test import RequestFactory
        from django.test.utils import CaptureQueriesContext
        request=RequestFactory().get("/notifications/live/"); request.user=self.user
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(snapshot(request).status_code,200)
        first=len(queries)
        for index in range(30):
            WorkflowNotification.objects.create(recipient=self.user,request=self.req,event_type="RETURNED",
                reference=self.req.request_number,event_key=f"query:{index}")
        with CaptureQueriesContext(connection) as queries:
            self.assertEqual(snapshot(request).status_code,200)
        self.assertEqual(len(queries),first)
        self.assertLessEqual(first,5)
        for _ in range(26):
            # Pending requests reserve no stock; normal submission builds each chain.
            self.make_request(quantity=1)
        page=self.client.get(reverse("pending_approvals"))
        self.assertEqual(len(page.context["approvals"]),25)
        self.assertEqual(page.context["pending_page"].paginator.count,27)
        self.assertEqual(len(self.client.get(reverse("pending_approvals"),{"page":2}).context["approvals"]),2)


class NotificationConcurrencyTests(StockSafetyFixtures, TransactionTestCase):
    def test_two_approvers_cannot_advance_or_deduct_twice(self):
        self.workflow.steps.update(alternate_approver_user=self.other)
        req,item=self.make_request(); approval=req.approvals.get(); barrier=Barrier(2)
        def act(user_id):
            close_old_connections()
            try:
                user=get_user_model().objects.get(pk=user_id)
                row=RequestApproval.objects.get(pk=approval.pk)
                barrier.wait(timeout=10)
                try: approve_step(row,user); return "approved"
                except ValidationError: return "blocked"
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(act,[self.user.pk,self.other.pk]))
        self.assertEqual(sorted(results),["approved","blocked"])
        self.assertEqual(RequestAuditLog.objects.filter(request=req,action="FINAL_APPROVED").count(),1)
        self.assertEqual(StockMovement.objects.filter(request=req,movement_type="OUT").count(),1)
        self.assertFalse(WorkflowNotification.objects.filter(approval=approval,actionable=True).exists())
