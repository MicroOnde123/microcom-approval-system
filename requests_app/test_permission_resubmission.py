"""Synthetic General Permission lifecycle and PostgreSQL serialization tests."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from html.parser import HTMLParser
import weakref
from unittest import skipUnless
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.db import close_old_connections, connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from accounts.models import Department
from workflows.models import ApprovalWorkflow, ApprovalWorkflowStep
from .forms import RequestForm
from .models import Request, RequestApproval, RequestAttachment, RequestAuditLog, RequestType, StockMovement
from .resubmission import BASELINE_ACTION, BASELINE_SALT
from .services import approve_step, reject_step, resubmit_request, return_step, submit_request
from .views import build_permission_metadata
from .approval_attempts import archived_attempt_page


class LiveResultsParser(HTMLParser):
    """Inspect the exact HTML fragment replaced by auto_filters.js."""
    voids = {"input", "img", "br", "hr", "meta", "link", "source", "area", "wbr", "col", "embed", "param", "track", "base"}

    def __init__(self):
        super().__init__()
        self.stack, self.text, self.links = [], [], []
        self.region_depth = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in self.voids:
            self.stack.append(tag)
        if attrs.get("id") == "live-filter-results": self.region_depth = len(self.stack)
        if self.region_depth and tag == "a": self.links.append(attrs.get("href", ""))

    def handle_endtag(self, tag):
        if tag in self.stack:
            while self.stack.pop() != tag:
                pass
        if self.region_depth and len(self.stack) < self.region_depth: self.region_depth = None

    def handle_data(self, data):
        if self.region_depth: self.text.append(data)


class ArchivedPaginationTests(SimpleTestCase):
    def test_streaming_pagination_keeps_bounded_records_and_exact_last_page(self):
        class Log:
            live = weakref.WeakSet()
            peak = 0

            def __init__(self, pk):
                self.pk = pk
                self.comment = json.dumps({"version": 1, "approvals": [{"step_order": 2, "status": "RETURNED",
                    "comment": "Preserved", "acted_by_id": 7, "approver_user_id": 7,
                    "acted_at": "2026-11-04T12:00:00+00:00"}], "people": {"7": "Recorded actor"}})
                self.live.add(self)
                type(self).peak = max(type(self).peak, len(self.live))

        class User:
            pk = 7

        for requested, expected_number, expected_ids in (("2", 2, list(range(25, 50))),
                ("9999", 41, [1000]), ("-1", 41, [1000]), ("bad", 1, list(range(25)))):
            page = archived_attempt_page((Log(pk) for pk in range(1001)), User(), {}, requested)
            self.assertEqual(page.paginator.count, 1001)
            self.assertEqual(page.number, expected_number)
            self.assertEqual([attempt["log"].pk for attempt in page], expected_ids)
            self.assertEqual(page.object_list[0]["decisions"][0]["actor"], "Recorded actor")
            del page
        self.assertLessEqual(Log.peak, 55)


class PermissionFixtures:
    def setUp(self):
        super().setUp()
        self.department = Department.objects.create(name="Synthetic permission", code="PERM")
        self.owner = get_user_model().objects.create_user(username="owner", department=self.department)
        self.people = [get_user_model().objects.create_user(username=f"approver-{n}", full_name=f"Approver {n}",
            department=self.department) for n in range(4)]
        for person in [self.owner, *self.people]:
            person.email = person.username + "@example.test"
            person.save(update_fields=["email"])
        self.kind = RequestType.objects.create(code="AUTORISATION_GENERAL", name="General Permission", is_permission_request=True)
        self.workflow = ApprovalWorkflow.objects.create(name="Synthetic permission", request_type=self.kind)
        for index in range(3):
            ApprovalWorkflowStep.objects.create(workflow=self.workflow, step_order=index + 1,
                approver_user=self.people[index], alternate_approver_user=self.people[3] if index == 1 else None)
        self.req = self.make_request()

    def data(self):
        return {"request_type": self.kind.pk, "request_for_department": self.department.pk,
                "date_needed": "2026-11-04", "permission_group": "LEAVE_PERMISSION",
                "permission_subgroup": "BY_FOOT", "destination": "Office", "exit_reason": "Visit office"}

    def make_request(self, **changes):
        form = RequestForm({**self.data(), **changes}, user=self.owner)
        assert form.is_valid(), form.errors
        req = form.save(commit=False)
        req.request_number = str(uuid4())
        req.submitted_by = self.owner
        req.department = self.department
        req.metadata_json = build_permission_metadata(form)
        req.save()
        submit_request(req)
        return req

    def returned(self, req=None, alternate=False):
        req = req or self.req
        approve_step(req.approvals.get(step_order=1), self.people[0], "First decision")
        return_step(req.approvals.get(step_order=2), self.people[3] if alternate else self.people[1], "Please verify")
        req.refresh_from_db()
        return req


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PermissionResubmissionTests(PermissionFixtures, TestCase):
    def test_draft_reason_remains_editable_and_is_frozen_in_submission_baseline(self):
        draft = Request.objects.create(request_number=str(uuid4()), request_type=self.kind,
            submitted_by=self.owner, department=self.department, request_for_department=self.department,
            description="Original draft description", metadata_json=self.req.metadata_json.copy(), status="DRAFT")
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[draft.pk])
        response = self.client.get(url)
        self.assertFalse(response.context["form"].fields["exit_reason"].disabled)
        token = response.context["submission_token"]
        saved = self.client.post(url, {**self.data(), "exit_reason": "Updated draft justification",
            "action": "save_draft", "submission_token": token})
        self.assertEqual(saved.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.metadata_json["exit_reason"], "Updated draft justification")
        self.assertFalse(draft.audit_logs.filter(action=BASELINE_ACTION).exists())
        token = self.client.get(url).context["submission_token"]
        submitted = self.client.post(url, {**self.data(), "exit_reason": "Final authorization justification",
            "action": "submit", "submission_token": token})
        self.assertEqual(submitted.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.status, "IN_REVIEW")
        baseline = signing.loads(draft.audit_logs.get(action=BASELINE_ACTION).comment, salt=BASELINE_SALT)
        self.assertEqual(baseline["information"]["metadata_json"]["exit_reason"], "Final authorization justification")

    def test_post_submission_reason_is_server_disabled_for_all_non_draft_states(self):
        reason = self.req.metadata_json["exit_reason"]
        for status in ("PENDING", "IN_REVIEW", "RETURNED", "APPROVED", "REJECTED", "CANCELLED"):
            Request.objects.filter(pk=self.req.pk).update(status=status)
            for save_only in (False, True):
                instance = Request.objects.get(pk=self.req.pk)
                form = RequestForm({**self.data(), "exit_reason": "Forged replacement", "description": "Allowed correction"}, instance=instance,
                    user=self.owner, draft=save_only, initial={"exit_reason": "Untrusted initial"})
                self.assertTrue(form.fields["exit_reason"].disabled)
                self.assertTrue(form.is_valid(), form.errors)
                self.assertEqual(form.cleaned_data["exit_reason"], reason)
                self.assertEqual(build_permission_metadata(form)["exit_reason"], reason)
                if status == "RETURNED":
                    self.assertEqual(form.cleaned_data["description"], "Allowed correction")

    def test_tampered_returned_reason_is_ignored_on_save_and_resubmit(self):
        self.returned()
        original_reason = self.req.metadata_json["exit_reason"]
        original_baseline = self.req.audit_logs.get(action=BASELINE_ACTION).comment
        first = self.req.approvals.filter(step_order=1).values().get()
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        for action in ("save_changes", "resubmit"):
            token = self.client.get(url).context["submission_token"]
            response = self.client.post(url, {**self.data(), "exit_reason": "Tampered authorization",
                "description": "Permitted description correction", "action": action, "submission_token": token})
            self.assertEqual(response.status_code, 302)
            self.req.refresh_from_db()
            self.assertEqual(self.req.metadata_json["exit_reason"], original_reason)
            self.assertEqual(self.req.description, "Permitted description correction")
        self.assertEqual(self.req.current_step_order, 2)
        self.assertEqual(self.req.approvals.filter(step_order=1).values().get(), first)
        baselines = list(self.req.audit_logs.filter(action=BASELINE_ACTION).order_by("pk"))
        self.assertEqual(baselines[0].comment, original_baseline)
        self.assertTrue(all(signing.loads(log.comment, salt=BASELINE_SALT)["information"]["metadata_json"]["exit_reason"]
                            == original_reason for log in baselines))
        event = self.req.audit_logs.get(action="PERMISSION_DESCRIPTION_CHANGED")
        self.assertEqual(json.loads(event.comment)["updated"], "Permitted description correction")
        self.assertEqual(event.performed_by, self.owner)

    def test_returned_description_label_and_readonly_reason_render_in_en_fr(self):
        self.returned()
        self.client.force_login(self.owner)
        for language in ("en", "fr"):
            self.client.cookies["django_language"] = language
            response = self.client.get(reverse("edit_request", args=[self.req.pk]))
            form = response.context["form"]
            self.assertEqual(str(form.fields["description"].label), "Description")
            self.assertFalse(form.fields["description"].disabled)
            self.assertTrue(form.fields["exit_reason"].disabled)
            self.assertContains(response, "Le motif initial" if language == "fr" else "The original authorization justification")
            self.assertNotContains(response, "Description / Motif" if language == "fr" else "Description / Reason")
            self.assertContains(response, 'id="id_exit_reason_helptext"')
            self.assertEqual(str(form.fields["exit_reason"].label), "Motif" if language == "fr" else "Reason / Motif")

    def test_material_form_does_not_inherit_reason_freezing_or_description_mode(self):
        kind = RequestType.objects.create(code="MATERIAL", name="Material", requires_materials=True)
        material_request = Request.objects.create(request_number=str(uuid4()), request_type=kind,
            submitted_by=self.owner, department=self.department, status="RETURNED", description="Material request")
        form = RequestForm(instance=material_request, user=self.owner)
        self.assertFalse(form.general_permission)
        self.assertFalse(form.fields["exit_reason"].disabled)
        self.assertIsNone(form.permission_description_type_id)

    def test_description_only_http_changes_resume_and_preserve_readable_audit_en_fr(self):
        for language in ("en", "fr"):
            req = self.returned(self.make_request())
            original = req.description
            metadata = req.metadata_json.copy()
            first = req.approvals.filter(step_order=1).values().get()
            baseline = req.audit_logs.get(action=BASELINE_ACTION)
            self.client.force_login(self.owner)
            self.client.cookies["django_language"] = language
            url = reverse("edit_request", args=[req.pk])
            form_page = self.client.get(url)
            self.assertEqual(form_page.context["form"].permission_description_type_id, self.kind.pk)
            token = form_page.context["submission_token"]
            updated = "Corrected description " + language
            response = self.client.post(url, {**self.data(), "description": updated,
                "action": "resubmit", "submission_token": token})
            self.assertEqual(response.status_code, 302)
            req.refresh_from_db()
            self.assertEqual(req.current_step_order, 2)
            self.assertEqual(req.metadata_json, metadata)
            self.assertEqual(req.description, updated)
            self.assertEqual(req.approvals.filter(step_order=1).values().get(), first)
            event = req.audit_logs.get(action="PERMISSION_DESCRIPTION_CHANGED")
            self.assertEqual(json.loads(event.comment), {"version": 1, "previous": original, "updated": updated})
            self.assertEqual(event.performed_by, self.owner)
            self.assertGreaterEqual(event.created_at, baseline.created_at)
            baselines = list(req.audit_logs.filter(action=BASELINE_ACTION).order_by("pk"))
            self.assertEqual([signing.loads(log.comment, salt=BASELINE_SALT)["information"]["description"]
                              for log in baselines], [original, updated])
            self.assertEqual(baselines[0].comment, baseline.comment)
            detail = self.client.get(reverse("request_detail", args=[req.pk]))
            self.assertContains(detail, "Description modifiée de" if language == "fr" else "Description changed from")
            self.client.force_login(self.people[1])
            approval = self.client.get(reverse("approval_detail", args=[req.approvals.get(step_order=2).pk]))
            self.assertContains(approval, updated)

    def test_description_plus_another_relevant_change_still_restarts(self):
        for changes in ({"date_needed": "2026-11-06"}, {"destination": "Another office"}):
            req = self.returned(self.make_request())
            self.client.force_login(self.owner)
            url = reverse("edit_request", args=[req.pk])
            token = self.client.get(url).context["submission_token"]
            response = self.client.post(url, {**self.data(), "description": "Only this field is neutral",
                **changes, "action": "resubmit", "submission_token": token})
            self.assertEqual(response.status_code, 302)
            req.refresh_from_db()
            self.assertEqual(req.current_step_order, 1)
            self.assertEqual(req.approvals.get(step_order=1).status, "PENDING")
            self.assertEqual(json.loads(req.audit_logs.get(action="RESUBMITTED").comment)["reason"], "information")

    def test_intermediate_description_saves_audit_each_change_without_replacing_baseline(self):
        self.returned()
        original = self.req.description
        baseline = self.req.audit_logs.get(action=BASELINE_ACTION).comment
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        for description in ("First correction", "Second correction"):
            token = self.client.get(url).context["submission_token"]
            response = self.client.post(url, {**self.data(), "description": description,
                "action": "save_changes", "submission_token": token})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(self.req.audit_logs.get(action=BASELINE_ACTION).comment, baseline)
        changes = list(self.req.audit_logs.filter(action="PERMISSION_DESCRIPTION_CHANGED").order_by("pk"))
        self.assertEqual([json.loads(event.comment)["previous"] for event in changes], [original, "First correction"])
        self.assertEqual([json.loads(event.comment)["updated"] for event in changes], ["First correction", "Second correction"])
        self.assertTrue(all(event.performed_by_id == self.owner.pk and event.created_at for event in changes))
        token = self.client.get(url).context["submission_token"]
        # An omitted description must not replace the saved correction with exit_reason.
        self.client.post(url, {**self.data(), "action": "resubmit", "submission_token": token})
        self.req.refresh_from_db()
        self.assertEqual(self.req.current_step_order, 2)
        self.assertEqual(self.req.description, "Second correction")
        self.assertEqual(self.req.audit_logs.filter(action="PERMISSION_DESCRIPTION_CHANGED").count(), 2)

    def test_unchanged_explicit_description_resumes_without_change_event(self):
        self.returned()
        first = self.req.approvals.filter(step_order=1).values().get()
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        token = self.client.get(url).context["submission_token"]
        self.client.post(url, {**self.data(), "description": self.req.description,
            "action": "resubmit", "submission_token": token})
        self.req.refresh_from_db()
        self.assertEqual(self.req.current_step_order, 2)
        self.assertEqual(self.req.approvals.filter(step_order=1).values().get(), first)
        self.assertFalse(self.req.audit_logs.filter(action="PERMISSION_DESCRIPTION_CHANGED").exists())

    def test_existing_bon_access_administration_document_route_is_preserved(self):
        for order in (1, 2, 3):
            approve_step(self.req.approvals.get(step_order=order), self.people[order - 1])
        self.owner.can_view_administration_reports = True
        self.owner.save(update_fields=["can_view_administration_reports"])
        self.client.force_login(self.owner)
        self.client.cookies["django_language"] = "fr"
        response = self.client.get(reverse("administration_report_document", args=[self.req.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "requests_app/permission_document.html")
        self.assertEqual(response.context["back_url"], reverse("administration_reports"))

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
    def test_http_initial_attachment_is_in_single_baseline_and_unchanged_request_resumes(self):
        self.client.force_login(self.owner)
        create_url = reverse("create_request")
        token = self.client.get(create_url).context["submission_token"]
        response = self.client.post(create_url, {**self.data(), "action": "submit", "submission_token": token,
            "attachments": SimpleUploadedFile("initial.txt", b"Approved evidence")})
        self.assertEqual(response.status_code, 302)
        req = Request.objects.exclude(pk=self.req.pk).get()
        self.assertEqual(req.attachments.count(), 1)
        self.assertEqual(req.audit_logs.filter(action=BASELINE_ACTION).count(), 1)
        baseline = signing.loads(req.audit_logs.get(action=BASELINE_ACTION).comment, salt=BASELINE_SALT)
        self.assertEqual(baseline["information"]["attachments"][0]["id"], req.attachments.get().pk)
        self.assertTrue(baseline["reliable"])
        # Replay creation with the same content must not add an attachment/baseline.
        self.client.post(create_url, {**self.data(), "action": "submit", "submission_token": token,
            "attachments": SimpleUploadedFile("initial.txt", b"Approved evidence")})
        self.assertEqual(req.attachments.count(), 1)
        self.assertEqual(req.audit_logs.filter(action=BASELINE_ACTION).count(), 1)
        self.returned(req)
        first = req.approvals.get(step_order=1)
        edit_url = reverse("edit_request", args=[req.pk])
        edit_token = self.client.get(edit_url).context["submission_token"]
        response = self.client.post(edit_url, {**self.data(), "action": "resubmit", "submission_token": edit_token})
        self.assertEqual(response.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.current_step_order, 2)
        self.assertEqual(req.approvals.get(step_order=1).pk, first.pk)
        self.assertEqual(req.approvals.get(step_order=1).acted_at, first.acted_at)

    def test_empty_replacement_is_rejected_before_archive_or_chain_deletion(self):
        self.returned()
        self.workflow.is_active = False; self.workflow.save()
        ApprovalWorkflow.objects.create(name="Empty replacement", request_type=self.kind)
        before_rows = list(self.req.approvals.order_by("pk").values())
        before_logs = list(self.req.audit_logs.order_by("pk").values())
        for language, message in (("en", "No approval steps are configured."), ("fr", "Aucune étape d’approbation")):
            with override(language), patch("requests_app.services.log_action") as audit:
                with self.assertRaisesMessage(ValidationError, message):
                    resubmit_request(self.req, self.owner)
                audit.assert_not_called()
            self.req.refresh_from_db()
            self.assertEqual(self.req.status, "RETURNED")
            self.assertEqual(list(self.req.approvals.order_by("pk").values()), before_rows)
            self.assertEqual(list(self.req.audit_logs.order_by("pk").values()), before_logs)
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        token = self.client.get(url).context["submission_token"]
        self.client.cookies["django_language"] = "fr"
        response = self.client.post(url, {**self.data(), "action": "resubmit", "submission_token": token})
        self.assertContains(response, "Aucune étape d’approbation")
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "RETURNED")

    def test_invalid_assignment_is_rejected_before_chain_replacement(self):
        self.returned()
        self.workflow.steps.filter(step_order=2).update(approver_user=None, approver_role=None)
        rows = list(self.req.approvals.order_by("pk").values())
        with self.assertRaises(ValidationError): resubmit_request(self.req, self.owner)
        self.assertEqual(list(self.req.approvals.order_by("pk").values()), rows)
        self.assertFalse(self.req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").exists())

    def test_archived_attempts_are_inside_live_region_and_filtered_ajax_responses(self):
        self.returned(alternate=True)
        resubmit_request(self.req, self.owner)
        self.client.force_login(self.people[3])
        url = reverse("approval_history")
        for query, expected in (({}, True), ({"action": "RETURNED"}, True),
                                ({"action": "APPROVED"}, False), ({"q": "no-match"}, False),
                                ({"date_from": "2099-01-01"}, False)):
            response = self.client.get(url, query, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            region = LiveResultsParser()
            region.feed(response.content.decode())
            self.assertEqual("Please verify" in "".join(region.text), expected)
            self.assertEqual("Previous approval attempts" in "".join(region.text), expected)
        archive = self.req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        RequestAuditLog.objects.bulk_create([RequestAuditLog(request=self.req, action=archive.action,
            comment=archive.comment) for _ in range(25)])
        response = self.client.get(url, {"action": "RETURNED", "attempt_page": "2"})
        region = LiveResultsParser(); region.feed(response.content.decode())
        self.assertTrue(any("action=RETURNED" in link and "attempt_page=1" in link for link in region.links))
        self.assertEqual(response.context["attempt_page"].number, 2)

    def test_database_decimal_scale_does_not_invalidate_unchanged_amount(self):
        req = self.returned(self.make_request(amount="12"))
        self.assertTrue(resubmit_request(req, self.owner)["resumed"])

    def test_unchanged_resumes_and_preserves_prior_decision_and_reference(self):
        req = self.returned()
        old = list(req.approvals.order_by("step_order").values())
        first = old[0]
        stale = req.approvals.get(step_order=2)
        reference = req.request_number
        outcome = resubmit_request(req, self.owner)
        self.assertEqual(outcome, {"resumed": True, "reason": "unchanged", "step": 2})
        req.refresh_from_db()
        self.assertEqual(req.current_step_order, 2)
        self.assertEqual(req.approvals.filter(step_order=1).values().get(), first)
        self.assertNotEqual(req.approvals.get(step_order=2).pk, stale.pk)
        archive = json.loads(req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED").comment)
        self.assertEqual(archive["approvals"][1]["comment"], "Please verify")
        self.assertEqual(archive["approvals"][1]["acted_by_id"], self.people[1].pk)
        self.assertEqual(archive["approvals"][1]["acted_at"], str(old[1]["acted_at"]))
        with self.assertRaises(ValidationError): approve_step(stale, self.people[1])
        with self.assertRaises(ValidationError): approve_step(req.approvals.get(step_order=3), self.people[2])
        approve_step(req.approvals.get(step_order=2), self.people[1], "Corrected")
        approve_step(req.approvals.get(step_order=3), self.people[2], "Final")
        req.refresh_from_db()
        self.assertEqual(req.status, "APPROVED")
        self.assertEqual(req.request_number, reference)
        self.assertFalse(StockMovement.objects.filter(request=req).exists())

    def test_alternate_return_resumes_same_step_and_keeps_both_assignments(self):
        self.returned(alternate=True)
        resubmit_request(self.req, self.owner)
        step = self.req.approvals.get(step_order=2)
        self.assertEqual(step.approver_user, self.people[1])
        self.assertEqual(step.alternate_approver_user, self.people[3])
        approve_step(step, self.people[3])
        step.refresh_from_db()
        self.assertEqual(step.acted_by, self.people[3])

    def test_relevant_request_fields_each_force_restart(self):
        changes = {"amount": "12.00", "date_needed": date(2026, 11, 5),
                   "request_for_department_id": Department.objects.create(code="OTHER", name="Other").pk,
                   "metadata_json": {"permission_group": "SITE_AUTHORIZATION", "site": "New site"}}
        for field, value in changes.items():
            with self.subTest(field=field):
                req = self.returned(self.make_request())
                Request.objects.filter(pk=req.pk).update(**{field: value})
                outcome = resubmit_request(req, self.owner)
                self.assertFalse(outcome["resumed"])
                self.assertEqual(outcome["reason"], "information")
                self.assertEqual(req.approvals.get(step_order=1).status, "PENDING")

    def test_workflow_and_assignment_changes_force_restart(self):
        for field, value in (("approver_user_id", self.people[3].pk), ("alternate_approver_user_id", self.people[0].pk), ("is_required", False)):
            req = self.returned(self.make_request())
            step = self.workflow.steps.get(step_order=2)
            original = getattr(step, field)
            setattr(step, field, value); step.save()
            outcome = resubmit_request(req, self.owner)
            self.assertEqual(outcome["reason"], "workflow")
            self.assertFalse(outcome["resumed"])
            setattr(step, field, original); step.save()

    def test_missing_malformed_and_unreliable_baselines_restart(self):
        for variant in ("missing", "malformed", "unreliable", "malformed-signed"):
            req = self.returned(self.make_request())
            log = req.audit_logs.get(action=BASELINE_ACTION)
            if variant == "missing": log.delete()
            elif variant == "malformed": log.comment = "broken"; log.save()
            else:
                payload = signing.loads(log.comment, salt=BASELINE_SALT)
                if variant == "unreliable": payload["reliable"] = False
                else: payload.pop("roster")
                log.comment = signing.dumps(payload, salt=BASELINE_SALT); log.save()
            outcome = resubmit_request(req, self.owner)
            self.assertEqual(outcome["reason"], "evidence")
            self.assertFalse(outcome["resumed"])

    def test_missing_approval_chain_still_records_localized_restart_reason(self):
        self.returned()
        self.req.approvals.all().delete()
        outcome = resubmit_request(self.req, self.owner)
        self.assertEqual(outcome["reason"], "evidence")
        event = self.req.audit_logs.get(action="RESUBMITTED")
        self.assertEqual(json.loads(event.comment)["reason"], "evidence")
        self.client.force_login(self.owner)
        self.client.cookies["django_language"] = "fr"
        self.assertContains(self.client.get(reverse("request_detail", args=[self.req.pk])), "Les preuves des approbations")

    def test_duplicate_steps_and_missing_decision_evidence_fail_closed(self):
        self.returned()
        first = self.req.approvals.get(step_order=1)
        first.acted_by = None; first.save()
        self.assertFalse(resubmit_request(self.req, self.owner)["resumed"])
        req = self.returned(self.make_request())
        step = self.workflow.steps.get(step_order=1)
        RequestApproval.objects.create(request=req, workflow_step=step, step_order=1, approver_user=self.people[0])
        self.assertFalse(resubmit_request(req, self.owner)["resumed"])

    def test_multiple_attempts_preserve_every_return_and_earlier_approval(self):
        self.returned()
        first_pk = self.req.approvals.get(step_order=1).pk
        resubmit_request(self.req, self.owner)
        return_step(self.req.approvals.get(step_order=2), self.people[3], "Second correction")
        resubmit_request(self.req, self.owner)
        self.assertEqual(self.req.approvals.get(step_order=1).pk, first_pk)
        self.assertEqual(self.req.audit_logs.filter(action="RESUBMITTED").count(), 2)
        archives = [json.loads(log.comment) for log in self.req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").order_by("pk")]
        self.assertEqual([data["approvals"][1]["comment"] for data in archives], ["Please verify", "Second correction"])

    def test_owner_active_authorization_and_sequential_duplicate(self):
        self.returned()
        with self.assertRaises(ValidationError): resubmit_request(self.req, self.people[0])
        self.owner.is_active = False; self.owner.save()
        with self.assertRaises(ValidationError): resubmit_request(self.req, self.owner)
        self.owner.is_active = True; self.owner.save()
        resubmit_request(self.req, self.owner)
        with self.assertRaises(ValidationError): resubmit_request(self.req, self.owner)
        self.assertEqual(self.req.audit_logs.filter(action="RESUBMITTED").count(), 1)

    def test_new_service_errors_and_resume_reason_translate_after_language_switch(self):
        self.returned()
        for language, expected in (("en", "Only the active request owner"), ("fr", "Seul l’auteur actif"), ("en", "Only the active request owner")):
            with override(language), self.assertRaisesMessage(ValidationError, expected):
                resubmit_request(self.req, self.people[0])
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        token = self.client.get(url).context["submission_token"]
        self.client.post(reverse("set_language"), {"language": "fr", "next": url})
        response = self.client.post(url, {**self.data(), "action": "resubmit", "submission_token": token}, follow=True)
        self.assertContains(response, "Les approbations précédentes restent valides.")

    def test_inactive_approver_cannot_act(self):
        person = self.people[0]
        get_user_model().objects.filter(pk=person.pk).update(is_active=False)
        for action in (approve_step, reject_step, return_step):
            with self.assertRaises(ValidationError): action(self.req.approvals.get(step_order=1), person)

    def test_notifications_wait_for_commit_and_use_resumed_step_recipients(self):
        self.returned()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with transaction.atomic():
                resubmit_request(self.req, self.owner)
                self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(set(mail.outbox[0].to), {self.people[1].email, self.people[3].email})

    def test_return_and_approval_notifications_keep_recipients(self):
        with self.captureOnCommitCallbacks(execute=True):
            approve_step(self.req.approvals.get(step_order=1), self.people[0])
        self.assertEqual(set(mail.outbox[-1].to), {self.people[1].email, self.people[3].email})
        with self.captureOnCommitCallbacks(execute=True):
            return_step(self.req.approvals.get(step_order=2), self.people[3])
        self.assertEqual(mail.outbox[-1].to, [self.owner.email])

    def test_failure_rolls_back_history_chain_and_notifications(self):
        self.returned()
        before = list(self.req.approvals.order_by("pk").values())
        with self.captureOnCommitCallbacks(execute=True):
            with patch("requests_app.services.record_baseline", side_effect=ValidationError("Synthetic failure")):
                with self.assertRaises(ValidationError): resubmit_request(self.req, self.owner)
        self.assertEqual(list(self.req.approvals.order_by("pk").values()), before)
        self.assertFalse(self.req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_outer_rollback_discards_already_queued_resubmission_mail(self):
        self.returned()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    resubmit_request(self.req, self.owner)
                    raise RuntimeError("Synthetic rollback after scheduling notification")
        self.assertEqual(callbacks, [])
        self.assertEqual(len(mail.outbox), 0)
        self.req.refresh_from_db()
        self.assertEqual(self.req.status, "RETURNED")

    def test_new_workflow_selection_restarts_and_records_reason(self):
        self.returned()
        self.workflow.is_active = False; self.workflow.save()
        workflow = ApprovalWorkflow.objects.create(name="New configured workflow", request_type=self.kind)
        ApprovalWorkflowStep.objects.create(workflow=workflow, step_order=1, approver_user=self.people[2])
        outcome = resubmit_request(self.req, self.owner)
        self.assertEqual(outcome["reason"], "workflow")
        self.assertEqual(self.req.approvals.get().workflow_step.workflow, workflow)

    def test_type_change_cannot_use_permission_resume(self):
        self.returned()
        kind = RequestType.objects.create(name="Other", code="OTHER")
        workflow = ApprovalWorkflow.objects.create(name="Other workflow", request_type=kind)
        ApprovalWorkflowStep.objects.create(workflow=workflow, step_order=1, approver_user=self.people[0])
        Request.objects.filter(pk=self.req.pk).update(request_type=kind)
        outcome = resubmit_request(self.req, self.owner)
        self.assertEqual(outcome["reason"], "information")
        self.assertFalse(outcome["resumed"])

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
    def test_unchanged_attachment_can_resume_but_missing_file_cannot(self):
        self.returned()
        attachment = RequestAttachment.objects.create(request=self.req, uploaded_by=self.owner,
            file=SimpleUploadedFile("stable.txt", b"unchanged"), original_name="stable.txt")
        resubmit_request(self.req, self.owner)  # Establish this changed scope with fresh approvals.
        self.returned()
        self.assertTrue(resubmit_request(self.req, self.owner)["resumed"])
        return_step(self.req.approvals.get(step_order=2), self.people[1])
        attachment.file.storage.delete(attachment.file.name)
        outcome = resubmit_request(self.req, self.owner)
        self.assertEqual(outcome["reason"], "evidence")

    def test_role_resolution_change_restarts(self):
        from accounts.models import Role
        role = Role.objects.create(name="Synthetic reviewer", code="PERM")
        person = self.people[1]
        person.role = role; person.save()
        self.workflow.steps.filter(step_order=2).update(approver_user=None, approver_role=role)
        req = self.returned(self.make_request())
        person.role = None; person.save()
        replacement = self.people[3]
        replacement.role = role; replacement.save()
        outcome = resubmit_request(req, self.owner)
        self.assertEqual(outcome["reason"], "workflow")
        self.assertEqual(req.approvals.get(step_order=2).approver_user, replacement)

    def test_archived_history_filters_pagination_and_escape_user_comments(self):
        self.returned(alternate=True)
        row = self.req.approvals.get(step_order=2)
        row.comment = '<script>alert("x")</script>'; row.save()
        resubmit_request(self.req, self.owner)
        self.client.force_login(self.people[3])
        url = reverse("approval_history")
        response = self.client.get(url, {"action": "RETURNED", "q": self.req.request_number})
        self.assertEqual(response.context["attempt_page"].paginator.count, 1)
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        self.assertEqual(self.client.get(url, {"action": "APPROVED"}).context["attempt_page"].paginator.count, 0)
        self.assertEqual(self.client.get(url, {"date_from": "2099-01-01"}).context["attempt_page"].paginator.count, 0)
        archive = self.req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        RequestAuditLog.objects.bulk_create([RequestAuditLog(request=self.req, action=archive.action, comment=archive.comment) for _ in range(25)])
        response = self.client.get(url, {"attempt_page": "2"})
        self.assertEqual(response.context["attempt_page"].paginator.count, 26)
        self.assertEqual(len(response.context["attempt_page"]), 1)

    def test_malformed_archives_do_not_break_detail_or_history(self):
        self.returned()
        RequestAuditLog.objects.create(request=self.req, action="APPROVAL_HISTORY_ARCHIVED", comment='{"version":1,"approvals":[{"status":{},"acted_by_id":[]}]}')
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("approval_history")).status_code, 200)

    @override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}})
    def test_attachments_and_mutated_contents_force_restart(self):
        with transaction.atomic():
            self.returned()
            attachment = RequestAttachment.objects.create(request=self.req, uploaded_by=self.owner,
                file=SimpleUploadedFile("evidence.txt", b"first"), original_name="evidence.txt")
            self.assertEqual(resubmit_request(self.req, self.owner)["reason"], "information")
            return_step(self.req.approvals.get(step_order=1), self.people[0])
            name = attachment.file.name
            attachment.file.storage.delete(name)
            attachment.file.storage.save(name, ContentFile(b"changed"))
            self.assertEqual(resubmit_request(self.req, self.owner)["reason"], "information")

    def test_http_intermediate_save_preserves_baseline_and_restart_reason(self):
        self.returned()
        baseline = self.req.audit_logs.get(action=BASELINE_ACTION).comment
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        page = self.client.get(url)
        token = page.context["submission_token"]
        saved = self.client.post(url, {**self.data(), "destination": "Changed scope", "action": "save_changes", "submission_token": token})
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(self.req.audit_logs.get(action=BASELINE_ACTION).comment, baseline)
        token = self.client.get(url).context["submission_token"]
        self.client.cookies["django_language"] = "fr"
        response = self.client.post(url, {**self.data(), "destination": "Changed scope", "action": "resubmit", "submission_token": token}, follow=True)
        self.assertContains(response, "Les informations pertinentes")
        self.req.refresh_from_db()
        self.assertEqual(self.req.current_step_order, 1)

    def test_http_unchanged_save_resume_and_duplicate_preserve_values(self):
        self.returned()
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        token = self.client.get(url).context["submission_token"]
        self.client.post(url, {**self.data(), "action": "save_changes", "submission_token": token})
        token = self.client.get(url).context["submission_token"]
        payload = {**self.data(), "action": "resubmit", "submission_token": token}
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.client.post(url, payload)
        self.req.refresh_from_db()
        self.assertEqual(self.req.current_step_order, 2)
        self.assertEqual(self.req.audit_logs.filter(action="RESUBMITTED").count(), 1)

    def test_http_failed_transition_rolls_back_edited_fields(self):
        self.returned()
        self.client.force_login(self.owner)
        url = reverse("edit_request", args=[self.req.pk])
        token = self.client.get(url).context["submission_token"]
        before = self.req.description
        with patch("requests_app.views.resubmit_request", side_effect=ValidationError("Synthetic failure")):
            response = self.client.post(url, {**self.data(), "description": "Changed description", "exit_reason": "Changed", "action": "resubmit", "submission_token": token})
        self.assertEqual(response.status_code, 200)
        self.req.refresh_from_db()
        self.assertEqual(self.req.description, before)
        self.assertEqual(self.req.status, "RETURNED")
        self.assertFalse(self.req.audit_logs.filter(action="PERMISSION_DESCRIPTION_CHANGED").exists())

    def test_readable_history_en_fr_and_old_approver_access(self):
        self.returned(alternate=True)
        resubmit_request(self.req, self.owner)
        for language, label in (("en", "Previous approval attempts"), ("fr", "Tentatives d’approbation précédentes")):
            self.client.cookies["django_language"] = language
            self.client.force_login(self.people[3])
            detail = self.client.get(reverse("request_detail", args=[self.req.pk]))
            self.assertContains(detail, label)
            self.assertContains(detail, "Please verify")
            self.assertContains(detail, "Approver 3")
            history = self.client.get(reverse("approval_history"))
            self.assertContains(history, label)
            self.assertContains(history, "Please verify")
        # A workflow reassignment must not erase the original actor's read access.
        return_step(self.req.approvals.get(step_order=2), self.people[1])
        self.workflow.steps.filter(step_order=2).update(alternate_approver_user=None)
        resubmit_request(self.req, self.owner)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 200)
        outsider = get_user_model().objects.create_user(username="outsider")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("request_detail", args=[self.req.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("approval_history")), "Please verify")


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL row locks")
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PermissionConcurrencyTests(PermissionFixtures, TransactionTestCase):
    def run_parallel(self, functions):
        barrier = Barrier(len(functions))
        def work(fn):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                fn()
                return "ok"
            except ValidationError:
                return "rejected"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(work, functions))

    def test_concurrent_resubmissions_create_one_attempt(self):
        self.returned()
        results = self.run_parallel([lambda: resubmit_request(self.req, self.owner)] * 2)
        self.assertCountEqual(results, ["ok", "rejected"])
        self.assertEqual(self.req.audit_logs.filter(action="RESUBMITTED").count(), 1)
        self.assertEqual(self.req.approvals.count(), 3)
        self.req.refresh_from_db()
        self.assertEqual(self.req.current_step_order, 2)

    def test_concurrent_primary_and_alternate_act_only_once(self):
        self.returned()
        resubmit_request(self.req, self.owner)
        step = self.req.approvals.get(step_order=2)
        results = self.run_parallel([lambda: approve_step(step, self.people[1]), lambda: return_step(step, self.people[3])])
        self.assertCountEqual(results, ["ok", "rejected"])
        self.assertEqual(self.req.audit_logs.filter(action__in=["APPROVED_STEP", "RETURNED"]).count(), 3)
