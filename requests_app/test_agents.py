"""Agent lifecycle regressions. Uses synthetic users and disposable test databases."""
import json
from copy import deepcopy
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .agents import validate_people
from .approval_attempts import readable_attempts
from .forms import RequestForm
from .models import Request
from .services import approve_step, resubmit_request, submit_request
from .test_permission_resubmission import PermissionFixtures
from .views import build_permission_metadata


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AgentTests(PermissionFixtures, TestCase):
    def selections(self):
        return [{"kind": "user", "user_id": self.people[0].pk},
                {"kind": "manual", "key": "manual-1", "first_name": "Marie Anne", "surname": "Test"}]

    def site_data(self, people=None):
        return {**self.data(), "permission_group": "SITE_AUTHORIZATION", "site": "Synthetic site",
                "site_selections": json.dumps([{"kind":"manual", "key":"synthetic-site", "name":"Synthetic site"}]),
                "valid_from": "2026-11-09", "valid_to": "2026-11-10",
                "agent_selections": json.dumps(self.selections() if people is None else people)}

    def draft(self):
        form = RequestForm(self.site_data(), user=self.owner, draft=True)
        self.assertTrue(form.is_valid(), form.errors)
        req = form.save(commit=False)
        req.request_number = str(uuid4()); req.submitted_by = self.owner; req.department = self.department
        req.metadata_json = build_permission_metadata(form); req.status = "DRAFT"; req.save()
        return req

    def submitted(self):
        req = self.draft()
        submit_request(req)
        req.refresh_from_db()
        return req

    def test_search_permissions_active_names_and_minimal_response(self):
        url = reverse("agent_user_search")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.owner)
        self.people[0].is_active = False; self.people[0].save()
        response = self.client.get(url, {"q": "Approver"})
        rows = response.json()["results"]
        self.assertNotIn(self.people[0].pk, [p["id"] for p in rows])
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(set(p) == {"id", "name"} for p in rows))
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.owner.department = None; self.owner.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.owner.is_active = False; self.owner.save()
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_search_full_name_and_pagination(self):
        person = self.people[0]
        person.full_name = ""; person.first_name = "Jane Anne"; person.last_name = "Doe"; person.save()
        self.client.force_login(self.owner)
        result = self.client.get(reverse("agent_user_search"), {"q": "Jane Anne Doe"}).json()
        self.assertEqual(result["results"], [{"id": person.pk, "name": "Jane Anne Doe"}])
        get_user_model().objects.bulk_create([get_user_model()(username=f"extra-{n}", full_name=f"Search {n}") for n in range(25)])
        first = self.client.get(reverse("agent_user_search"), {"q": "Search"}).json()
        second = self.client.get(reverse("agent_user_search"), {"q": "Search", "page": 2}).json()
        self.assertEqual(len(first["results"]), 20); self.assertTrue(first["more"])
        self.assertEqual(len(second["results"]), 5); self.assertFalse(second["more"])
        self.assertEqual(self.client.get(reverse("agent_user_search"), {"page":"bad"}).status_code,400)

    def test_order_manual_names_and_ten_limit(self):
        people = self.selections() + [{"kind":"manual", "key":str(n), "first_name":"Same", "surname":"Name"} for n in range(8)]
        rows = validate_people(people)
        self.assertEqual(len(rows),10)
        self.assertEqual([p["order"] for p in rows],list(range(10)))
        self.assertEqual(rows[1]["full_name"],"Marie Anne Test")
        with self.assertRaises(ValidationError): validate_people(people + [{"kind":"user","user_id":self.owner.pk}])

    def test_invalid_duplicates_ids_and_names(self):
        one = self.selections()[0]
        for value in (None, {}, [one,one], [{"kind":"user","user_id":True}],
                      [{"kind":"user","user_id":-1}], [{"kind":"user","user_id":10**30}],
                      [{"kind":"user","user_id":999999}], [{"kind":"user","user_id":"1"}],
                      [{"kind":"manual","key":"x","first_name":" ","surname":"Test"}],
                      [{"kind":"manual","key":"x","first_name":"A\nB","surname":"Test"}],
                      [{"kind":"manual","key":"x","first_name":"a"*256,"surname":"Test"}],
                      [self.selections()[1], self.selections()[1]]):
            with self.subTest(value=value), self.assertRaises(ValidationError): validate_people(value)
        self.people[0].is_active=False; self.people[0].save()
        with self.assertRaises(ValidationError): validate_people([one])

    def test_same_name_people_allowed_without_accounts_or_notifications(self):
        count=get_user_model().objects.count()
        person=self.selections()[1]
        rows=validate_people([person,{**person,"key":"different-person"}])
        self.assertEqual(len(rows),2)
        self.assertEqual(get_user_model().objects.count(),count)

    def test_draft_reopens_with_ids_and_edits_in_order(self):
        req=self.draft(); req.refresh_from_db()
        form=RequestForm(instance=req,user=self.owner,draft=True)
        self.assertEqual(form.fields["agent_selections"].initial[0]["user_id"], self.people[0].pk)
        replacement=[{**self.selections()[1],"first_name":"Updated"}, {"kind":"user","user_id":self.people[2].pk}]
        form=RequestForm(self.site_data(replacement),instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors)
        req.metadata_json=build_permission_metadata(form);req.save();req.refresh_from_db()
        self.assertEqual(req.metadata_json["agent_selections"][0]["full_name"],"Updated Test")
        self.assertEqual(req.metadata_json["agent_selections"][1]["user_id"],self.people[2].pk)
        self.assertNotIn("agent_attempts",req.metadata_json)

    def test_submission_resolves_current_names_and_freezes_document(self):
        req=self.draft()
        person=self.people[0]; person.full_name="Submission Name";person.save()
        submit_request(req); req.refresh_from_db()
        self.assertEqual(req.agent_names,"Submission Name; Marie Anne Test")
        attempt=deepcopy(req.metadata_json["agent_attempts"][0])
        person.full_name="Later Name";person.save()
        self.assertEqual(req.agent_names,"Submission Name; Marie Anne Test")
        for order in (1,2,3): approve_step(req.approvals.get(step_order=order),self.people[order-1])
        person.is_active=False;person.save();req.refresh_from_db()
        self.assertEqual(req.metadata_json["agent_attempts"][0],attempt)
        self.client.force_login(self.owner)
        for name in ("permission_document","request_detail"):
            response=self.client.get(reverse(name,args=[req.pk]))
            self.assertContains(response,"Submission Name")
            self.assertNotContains(response,"Later Name; Marie Anne Test")
        self.owner.can_view_administration_reports=True;self.owner.save()
        self.assertContains(self.client.get(reverse("administration_report_document",args=[req.pk])),"Submission Name")

    def test_inactive_at_submission_rolls_back_without_snapshot(self):
        req=self.draft(); self.people[0].is_active=False;self.people[0].save()
        with self.assertRaises(ValidationError):submit_request(req)
        req.refresh_from_db()
        self.assertEqual(req.status,"DRAFT");self.assertFalse(req.approvals.exists())
        self.assertNotIn("agent_attempts",req.metadata_json)

    def assert_attempt_link(self,req,old_id,old_text):
        req.refresh_from_db()
        old,new=req.metadata_json["agent_attempts"]
        self.assertEqual(old["id"],old_id); self.assertNotEqual(new["id"],old_id)
        self.assertEqual(old["text"],old_text)
        self.assertEqual(new["approval_ids"],list(req.approvals.order_by("step_order").values_list("pk",flat=True)))
        archive=req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        self.assertEqual(old["archive_log_id"],archive.pk)
        self.assertEqual(readable_attempts([archive])[0]["agent_names"],old_text)
        self.assertEqual(req.metadata_json["agent_current_attempt"],new["id"])

    def test_returned_unchanged_resumes_and_history_keeps_snapshot(self):
        req=self.submitted(); old=deepcopy(req.metadata_json["agent_attempts"][0])
        self.returned(req)
        first=req.approvals.get(step_order=1).pk
        result=resubmit_request(req,self.owner)
        self.assertTrue(result["resumed"]);self.assertEqual(result["step"],2)
        self.assertEqual(req.approvals.get(step_order=1).pk,first)
        self.assert_attempt_link(req,old["id"],old["text"])

    def test_returned_corrections_restart_and_preserve_previous_snapshot(self):
        req=self.submitted();old=deepcopy(req.metadata_json["agent_attempts"][0]);self.returned(req)
        data=self.site_data([{**self.selections()[1],"surname":"Corrected"}])
        form=RequestForm(data,instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors)
        req.metadata_json=build_permission_metadata(form);req.save()
        self.assertEqual(req.metadata_json["agent_attempts"][0],old)
        result=resubmit_request(req,self.owner)
        self.assertFalse(result["resumed"])
        self.assert_attempt_link(req,old["id"],old["text"])
        self.assertEqual(req.agent_names,"Marie Anne Corrected")
        self.client.force_login(self.people[0])
        self.assertContains(self.client.get(reverse("approval_detail",args=[req.approvals.get(step_order=1).pk])),"Marie Anne Corrected")
        self.client.force_login(self.owner)
        detail=self.client.get(reverse("request_detail",args=[req.pk]))
        self.assertContains(detail,old["text"])
        self.client.force_login(self.people[1])
        self.assertContains(self.client.get(reverse("approval_history")),old["text"])

    def test_attempt_snapshot_failure_rolls_back_archive_and_route(self):
        from unittest.mock import patch
        req=self.submitted();self.returned(req)
        before=deepcopy(req.metadata_json)
        with patch("requests_app.services.record_attempt",side_effect=RuntimeError("snapshot failed")):
            with self.assertRaises(RuntimeError):resubmit_request(req,self.owner)
        req.refresh_from_db()
        self.assertEqual(req.metadata_json,before)
        self.assertFalse(req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").exists())
        self.assertEqual(req.status,"RETURNED")

    def test_legacy_free_text_unchanged_without_profile_resolution(self):
        req=self.draft();req.metadata_json.pop("agent_selections")
        req.metadata_json["microcom_agents"]="Historical unknown names / exact punctuation";req.save()
        submit_request(req);req.refresh_from_db()
        self.assertEqual(req.agent_names,"Historical unknown names / exact punctuation")
        self.assertIsNone(req.metadata_json["agent_attempts"][0]["people"])
        self.returned(req)
        form=RequestForm({**self.site_data(),"agent_selections":""},instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors)
        req.metadata_json=build_permission_metadata(form);req.save()
        self.assertEqual(req.metadata_json["microcom_agents"],"Historical unknown names / exact punctuation")
        self.assertNotIn("agent_selections",req.metadata_json)
        self.assertTrue(resubmit_request(req,self.owner)["resumed"])

    def test_bilingual_validation_and_picker(self):
        self.client.force_login(self.owner)
        for language,expected,label in (("en","Select at most 10 people.","Other person — Add manually"),
                ("fr","Sélectionnez au maximum 10 personnes.","Autre personne — Ajouter manuellement")):
            with override(language):
                with self.assertRaisesMessage(ValidationError,expected):validate_people(self.selections()*6)
                self.client.cookies["django_language"]=language
                self.assertContains(self.client.get(reverse("create_request")),label)
        form=RequestForm({**self.site_data(),"agent_selections":"[invalid"},user=self.owner,draft=True)
        self.assertFalse(form.is_valid());self.assertIn("agent_selections",form.errors)

    def test_http_draft_save_reopen_edit_submit(self):
        self.client.force_login(self.owner)
        url=reverse("create_request")
        token=self.client.get(url).context["submission_token"]
        response=self.client.post(url,{**self.site_data(),"submission_token":token,"action":"save_draft"})
        self.assertEqual(response.status_code,302)
        req=Request.objects.exclude(pk=self.req.pk).get()
        url=reverse("edit_request",args=[req.pk])
        response=self.client.get(url)
        self.assertContains(response,"Marie Anne")
        token=response.context["submission_token"]
        response=self.client.post(url,{**self.site_data([self.selections()[1]]),"submission_token":token,"action":"save_draft"})
        self.assertEqual(response.status_code,302)
        req.refresh_from_db();self.assertEqual(len(req.metadata_json["agent_selections"]),1)
        token=self.client.get(url).context["submission_token"]
        response=self.client.post(url,{**self.site_data([self.selections()[1]]),"submission_token":token,"action":"submit"})
        self.assertEqual(response.status_code,302)
        req.refresh_from_db();self.assertEqual(req.status,"IN_REVIEW")
        self.assertEqual(req.agent_names,"Marie Anne Test")

    def test_multiple_registered_users_and_form_limit_including_drafts(self):
        people = self.selections() + [{"kind": "user", "user_id": self.people[1].pk}]
        form = RequestForm(self.site_data(people), user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual([row.get("user_id") for row in form.cleaned_data["agent_selections"]],
                         [self.people[0].pk, None, self.people[1].pk])
        excessive = [{"kind": "manual", "key": str(n), "first_name": "Person", "surname": str(n)} for n in range(11)]
        for draft in (True, False):
            form = RequestForm(self.site_data(excessive), user=self.owner, draft=draft)
            self.assertFalse(form.is_valid())
            self.assertIn("Select at most 10 people.", str(form.errors))

    def test_legacy_approved_document_without_any_new_snapshot(self):
        req = self.draft()
        req.metadata_json.pop("agent_selections")
        req.metadata_json["microcom_agents"] = "Unmatched legacy text / preserved"
        req.status = "APPROVED"
        req.save()
        before = deepcopy(req.metadata_json)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("permission_document", args=[req.pk])), before["microcom_agents"])
        req.refresh_from_db()
        self.assertEqual(req.metadata_json, before)
        self.assertNotIn("agent_attempts", req.metadata_json)

    def test_registered_rename_on_resubmission_preserves_prior_names(self):
        req = self.submitted()
        previous = deepcopy(req.metadata_json["agent_attempts"][0])
        self.returned(req)
        self.people[0].full_name = "New submission name"
        self.people[0].save()
        self.assertFalse(resubmit_request(req, self.owner)["resumed"])
        self.assert_attempt_link(req, previous["id"], previous["text"])
        self.assertEqual(req.agent_names, "New submission name; Marie Anne Test")

    def test_manual_names_are_escaped_in_details_and_documents(self):
        req = self.draft()
        req.metadata_json["agent_selections"] = [{"kind": "manual", "key": "escaped",
            "first_name": "<script>alert(1)</script>", "surname": "Person"}]
        req.save()
        submit_request(req)
        for order in (1, 2, 3):
            approve_step(req.approvals.get(step_order=order), self.people[order-1])
        self.client.force_login(self.owner)
        for route in ("request_detail", "permission_document"):
            response = self.client.get(reverse(route, args=[req.pk]))
            self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
            self.assertNotContains(response, "<script>alert(1)</script>")

    def test_changing_to_leave_permission_keeps_history_without_current_agents(self):
        req = self.submitted()
        previous = deepcopy(req.metadata_json["agent_attempts"][0])
        self.returned(req)
        form = RequestForm(self.data(), instance=req, user=self.owner)
        self.assertTrue(form.is_valid(), form.errors)
        req.metadata_json = build_permission_metadata(form)
        req.save()
        self.assertFalse(resubmit_request(req, self.owner)["resumed"])
        req.refresh_from_db()
        self.assertEqual(req.agent_names, "")
        self.assertEqual(req.metadata_json["agent_attempts"][0]["text"], previous["text"])
        self.assertEqual(req.metadata_json["agent_attempts"][0]["archive_log_id"],
                         req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED").pk)
