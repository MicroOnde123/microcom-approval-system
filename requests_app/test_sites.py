"""Central directory and shared authorization-attempt regression coverage."""
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import Event
from copy import deepcopy
from uuid import uuid4
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils.translation import override
from core.models import Site

from .forms import RequestForm
from .models import Request
from .site_selection import validate_sites
from .services import submit_request, resubmit_request, approve_step
from .approval_attempts import readable_attempts
from .test_permission_resubmission import PermissionFixtures
from .views import build_permission_metadata
from . import test_permission_resubmission as permission_tests


class SiteTests(PermissionFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.site = Site.objects.create(name="Directory Alpha")

    def selected(self):
        return [{"kind":"site", "site_id":self.site.pk}, {"kind":"manual", "key":"remote", "name":"Remote site"}]

    def payload(self, sites=None):
        return {**self.data(), "permission_group":"SITE_AUTHORIZATION", "valid_from":"2026-11-09",
                "valid_to":"2026-11-10", "site_selections":json.dumps(self.selected() if sites is None else sites),
                "agent_selections":json.dumps([{"kind":"user", "user_id":self.people[0].pk}])}

    def draft(self):
        form = RequestForm(self.payload(), user=self.owner, draft=True)
        self.assertTrue(form.is_valid(), form.errors)
        req = form.save(commit=False)
        req.request_number = str(uuid4()); req.submitted_by = self.owner; req.department = self.department
        req.status = "DRAFT"; req.metadata_json = build_permission_metadata(form); req.save()
        return req

    def submitted(self):
        req = self.draft(); submit_request(req); req.refresh_from_db(); return req

    def test_directory_model_validation_and_admin_permissions(self):
        for name in (" ", "a\nb", "x"*256):
            with self.subTest(name=name), self.assertRaises(ValidationError): Site(name=name).full_clean()
        self.client.force_login(self.owner)
        self.assertNotEqual(self.client.get(reverse("admin:core_site_add")).status_code, 200)
        self.owner.is_staff = True; self.owner.save()
        self.assertEqual(self.client.get(reverse("admin:core_site_add")).status_code, 403)
        self.owner.user_permissions.add(*Permission.objects.filter(content_type__app_label="core", codename__in=["add_site","change_site","view_site"]))
        self.assertEqual(self.client.post(reverse("admin:core_site_add"), {"name":" Admin Site ","is_active":"on","_save":"Save"}).status_code,302)
        site=Site.objects.get(name="Admin Site")
        response=self.client.post(reverse("admin:core_site_change",args=[site.pk]),{"name":"Renamed site","_save":"Save"})
        self.assertEqual(response.status_code,302);site.refresh_from_db();self.assertFalse(site.is_active)
        response=self.client.get(reverse("admin:core_site_changelist"),{"q":"Renamed","is_active__exact":"0"})
        self.assertContains(response,"Renamed site")
        self.assertFalse(admin.site._registry[Site].has_delete_permission(response.wsgi_request,site))
        self.assertEqual(self.client.post(reverse("admin:core_site_change",args=[site.pk]),{"name":"Renamed site","is_active":"on","_save":"Save"}).status_code,302)
        site.refresh_from_db();self.assertTrue(site.is_active)

    def test_search_permissions_active_filter_and_pagination(self):
        url=reverse("site_search")
        self.assertEqual(self.client.get(url).status_code,302)
        self.client.force_login(self.owner)
        Site.objects.create(name="Directory inactive",is_active=False)
        Site.objects.bulk_create([Site(name=f"Directory {n:02}") for n in range(24)])
        first=self.client.get(url,{"q":"directory"});second=self.client.get(url,{"q":"directory","page":2})
        self.assertEqual(len(first.json()["results"]),20);self.assertTrue(first.json()["more"])
        self.assertEqual(len(second.json()["results"]),5);self.assertFalse(second.json()["more"])
        self.assertTrue(all(set(row)=={"id","name"} for row in first.json()["results"]))
        self.assertNotIn("inactive",str(first.json())+str(second.json()))
        self.assertEqual(first["Cache-Control"],"private, no-store")
        self.assertEqual(self.client.get(url,{"page":"bad"}).status_code,400)
        self.assertEqual(self.client.post(url,{}).status_code,405)
        self.owner.department=None;self.owner.save()
        self.assertEqual(self.client.get(url).status_code,403)
        self.owner.is_active=False;self.owner.save()
        self.assertNotEqual(self.client.get(url).status_code,200)

    def test_combined_five_limit_and_six_rejected_in_forms_and_service(self):
        rows=self.selected()+[{"kind":"manual","key":str(n),"name":f"Extra {n}"} for n in range(3)]
        self.assertEqual([row["order"] for row in validate_sites(rows)],list(range(5)))
        for draft in (True,False):
            form=RequestForm(self.payload(rows),user=self.owner,draft=draft)
            self.assertTrue(form.is_valid(),form.errors)
            form=RequestForm(self.payload(rows+[{"kind":"manual","key":"six","name":"Sixth"}]),user=self.owner,draft=draft)
            self.assertFalse(form.is_valid());self.assertIn("site_selections",form.errors)
        req=self.draft();req.metadata_json["site_selections"]=rows+[{"kind":"manual","key":"six","name":"Sixth"}];req.save()
        with self.assertRaises(ValidationError):submit_request(req)
        req.refresh_from_db();self.assertEqual(req.status,"DRAFT");self.assertFalse(req.approvals.exists())

    def test_multiple_directory_sites_and_empty_submission(self):
        others=[Site.objects.create(name=f"Directory {n}") for n in range(4)]
        rows=[{"kind":"site","site_id":site.pk} for site in [self.site,*others]]
        self.assertEqual([row["site_id"] for row in validate_sites(rows)],[self.site.pk,*[site.pk for site in others]])
        form=RequestForm(self.payload([]),user=self.owner)
        self.assertFalse(form.is_valid());self.assertIn("site_selections",form.errors)
        req=self.draft();req.metadata_json.pop("site_selections");req.metadata_json["site"]="";req.save()
        with self.assertRaises(ValidationError):submit_request(req)

    def test_invalid_json_and_forged_snapshot_names_are_rejected_or_resolved(self):
        form=RequestForm({**self.payload(),"site_selections":"[invalid"},user=self.owner,draft=True)
        self.assertFalse(form.is_valid());self.assertIn("site_selections",form.errors)
        form=RequestForm(self.payload([{**self.selected()[0],"name":"Forged directory name"}]),user=self.owner)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(form.cleaned_data["site_selections"][0]["name"],"Directory Alpha")

    def test_duplicate_and_tampered_ids_manual_keys_and_names(self):
        one=self.selected()[0]
        invalid=(None,{},[one,one],[None],[{"kind":"site","site_id":True}], [{"kind":"site","site_id":"1"}],
            [{"kind":"site","site_id":10**30}],[{"kind":"site","site_id":999999}],
            [{"kind":"manual","key":"k","name":" "}],[{"kind":"manual","key":"k","name":"x"*256}],
            [{"kind":"manual","key":"k","name":"a\nb"}],[self.selected()[1],self.selected()[1]])
        for rows in invalid:
            with self.subTest(rows=rows),self.assertRaises(ValidationError):validate_sites(rows)
        # Identical names are legitimate when entries have distinct identities.
        self.assertEqual(len(validate_sites([self.selected()[1],{**self.selected()[1],"key":"other"}])),2)

    def test_inactive_selection_draft_and_submission_rejected(self):
        req=self.draft();self.site.is_active=False;self.site.save()
        form=RequestForm(self.payload(),instance=req,user=self.owner,draft=True)
        self.assertFalse(form.is_valid())
        with self.assertRaises(ValidationError):submit_request(req)
        req.refresh_from_db();self.assertNotIn("agent_attempts",req.metadata_json)

    def test_manual_entries_never_create_directory_records(self):
        count=Site.objects.count()
        form=RequestForm(self.payload([{"kind":"manual","key":"m","name":"New unlisted site"}]),user=self.owner)
        self.assertTrue(form.is_valid(),form.errors);self.assertEqual(Site.objects.count(),count)

    def test_draft_restoration_order_edit_and_remove(self):
        req=self.draft();form=RequestForm(instance=req,user=self.owner,draft=True)
        self.assertEqual(form.fields["site_selections"].initial[0]["site_id"],self.site.pk)
        rows=[{**self.selected()[1],"name":"Edited manual site"}]
        form=RequestForm(self.payload(rows),instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors);req.metadata_json=build_permission_metadata(form);req.save();req.refresh_from_db()
        self.assertEqual(req.site_names,["Edited manual site"]);self.assertNotIn("agent_attempts",req.metadata_json)

    def test_submission_resolves_names_and_records_one_shared_attempt(self):
        req=self.draft();self.site.name="Current submission name";self.site.save()
        req.metadata_json["site_selections"][0]["name"]="Forged browser snapshot";req.save()
        submit_request(req);req.refresh_from_db()
        self.assertEqual(req.site_names,["Current submission name","Remote site"])
        self.assertEqual(len(req.metadata_json["agent_attempts"]),1)
        attempt=req.metadata_json["agent_attempts"][0]
        self.assertEqual(attempt["id"],req.metadata_json["agent_current_attempt"])
        self.assertEqual(attempt["sites"][0]["site_id"],self.site.pk)
        self.assertEqual(attempt["people"][0]["user_id"],self.people[0].pk)
        self.assertNotIn("site_attempts",req.metadata_json)

    def test_approved_documents_keep_names_after_rename_and_deactivation(self):
        req=self.submitted();previous=deepcopy(req.metadata_json["agent_attempts"])
        self.site.name="Future directory name";self.site.is_active=False;self.site.save()
        for order in (1,2,3):approve_step(req.approvals.get(step_order=order),self.people[order-1])
        self.client.force_login(self.owner)
        for route in ("request_detail","permission_document"):
            response=self.client.get(reverse(route,args=[req.pk]));self.assertContains(response,"Directory Alpha");self.assertContains(response,"Remote site");self.assertNotContains(response,"Future directory name")
        self.owner.can_view_administration_reports=True;self.owner.save()
        self.assertContains(self.client.get(reverse("administration_report_document",args=[req.pk])),"Directory Alpha")
        req.refresh_from_db();self.assertEqual(req.metadata_json["agent_attempts"],previous)

    def check_resubmission(self,changed):
        req=self.submitted();old=deepcopy(req.metadata_json["agent_attempts"][0]);self.returned(req)
        if changed:
            form=RequestForm(self.payload([{**self.selected()[1],"name":"Correction"}]),instance=req,user=self.owner,draft=True)
            self.assertTrue(form.is_valid(),form.errors);req.metadata_json=build_permission_metadata(form);req.save()
        result=resubmit_request(req,self.owner);self.assertEqual(result["resumed"],not changed)
        req.refresh_from_db();attempts=req.metadata_json["agent_attempts"]
        self.assertEqual(len(attempts),2);self.assertNotEqual(attempts[0]["id"],attempts[1]["id"])
        self.assertEqual(attempts[0]["sites"],old["sites"])
        archive=req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        self.assertEqual(attempts[0]["archive_log_id"],archive.pk)
        self.assertEqual(readable_attempts([archive])[0]["site_names"],["Directory Alpha","Remote site"])
        self.assertEqual(attempts[1]["approval_ids"],list(req.approvals.order_by("step_order").values_list("pk",flat=True)))
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("request_detail",args=[req.pk])),"Directory Alpha")
        self.client.force_login(self.people[1])
        self.assertContains(self.client.get(reverse("approval_history")),"Directory Alpha")

    def test_unchanged_sites_resume_and_preserve_history(self):self.check_resubmission(False)
    def test_corrected_sites_restart_and_preserve_history(self):self.check_resubmission(True)

    def test_rename_on_resubmission_is_approval_relevant(self):
        req=self.submitted();self.returned(req);self.site.name="Renamed before resubmission";self.site.save()
        self.assertFalse(resubmit_request(req,self.owner)["resumed"])
        req.refresh_from_db();self.assertEqual(req.metadata_json["agent_attempts"][0]["sites"][0]["name"],"Directory Alpha")
        self.assertEqual(req.site_names[0],"Renamed before resubmission")

    def test_snapshot_failure_rolls_back_sites_agents_and_approval_history(self):
        req=self.submitted();self.returned(req);before=deepcopy(req.metadata_json)
        with patch("requests_app.services.record_attempt",side_effect=RuntimeError("snapshot failed")):
            with self.assertRaises(RuntimeError):resubmit_request(req,self.owner)
        req.refresh_from_db();self.assertEqual(req.metadata_json,before)
        self.assertFalse(req.audit_logs.filter(action="APPROVAL_HISTORY_ARCHIVED").exists())

    def test_legacy_approved_free_text_needs_no_conversion_or_resubmission(self):
        req=self.draft();req.metadata_json.pop("site_selections");req.metadata_json["site"]="Legacy / site; exact text"
        req.status="APPROVED";req.save();before=deepcopy(req.metadata_json)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("permission_document",args=[req.pk])),"Legacy / site; exact text")
        req.refresh_from_db();self.assertEqual(req.metadata_json,before);self.assertEqual(Site.objects.count(),1)

    def test_pre_feature_attempt_retains_signed_legacy_site_when_corrected(self):
        req=self.draft();req.metadata_json.pop("site_selections");req.metadata_json["site"]="Original legacy site";req.save();submit_request(req)
        req.refresh_from_db();attempt=req.metadata_json["agent_attempts"][0]
        attempt.pop("site_text");attempt.pop("sites");attempt["version"]=1;req.save()
        self.returned(req)
        form=RequestForm(self.payload(),instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors);req.metadata_json=build_permission_metadata(form);req.save()
        resubmit_request(req,self.owner);req.refresh_from_db()
        archive=req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        self.assertEqual(readable_attempts([archive])[0]["site_names"],["Original legacy site"])

    def test_bilingual_validation_and_both_pickers_render_without_id_collisions(self):
        self.client.force_login(self.owner)
        for language,message,action in (("en","Select at most 5 sites.","Other site — Add manually"),
                ("fr","Sélectionnez au maximum 5 sites.","Autre site — Ajouter manuellement")):
            with override(language):
                with self.assertRaisesMessage(ValidationError,message):validate_sites([{}]*6)
            self.client.cookies["django_language"]=language
            response=self.client.get(reverse("create_request"));self.assertContains(response,action)
            self.assertContains(response,'id="site-search"',count=1);self.assertContains(response,'id="agent-search"',count=1)

    def test_pre_picker_signed_baseline_retains_legacy_site_in_shared_history(self):
        req=self.draft();req.metadata_json.pop("site_selections");req.metadata_json.pop("agent_selections")
        req.metadata_json["site"]="Pre-picker original site";req.save();submit_request(req)
        req.refresh_from_db();req.metadata_json.pop("agent_attempts");req.metadata_json.pop("agent_current_attempt");req.save()
        self.returned(req)
        form=RequestForm(self.payload(),instance=req,user=self.owner,draft=True)
        self.assertTrue(form.is_valid(),form.errors);req.metadata_json=build_permission_metadata(form);req.save()
        resubmit_request(req,self.owner);req.refresh_from_db()
        self.assertEqual(len(req.metadata_json["agent_attempts"]),2)
        archive=req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED")
        self.assertEqual(readable_attempts([archive])[0]["site_names"],["Pre-picker original site"])
        self.assertEqual(Site.objects.count(),1)

    def test_invalid_legacy_baselines_never_supply_historical_site_names(self):
        from django.core import signing
        from .resubmission import BASELINE_ACTION, BASELINE_SALT
        req=self.submitted();self.returned(req)
        old=req.metadata_json["agent_attempts"][0];old.pop("sites");old.pop("site_text");old["version"]=1;req.save()
        baseline=req.audit_logs.get(action=BASELINE_ACTION)
        evidence=signing.loads(baseline.comment,salt=BASELINE_SALT)
        invalid=deepcopy(evidence);invalid["information"]["metadata_json"]=[]
        for comment in ("not a signed baseline",signing.dumps(invalid,salt=BASELINE_SALT)):
            baseline.comment=comment;baseline.save(update_fields=["comment"])
            form=RequestForm(self.payload(),instance=req,user=self.owner,draft=True)
            self.assertTrue(form.is_valid(),form.errors)
            metadata=build_permission_metadata(form)
            self.assertNotIn("site_text",metadata["agent_attempts"][0])

    def test_http_draft_save_reopen_edit_and_submit(self):
        self.client.force_login(self.owner);url=reverse("create_request")
        token=self.client.get(url).context["submission_token"]
        response=self.client.post(url,{**self.payload(),"action":"save_draft","submission_token":token})
        self.assertEqual(response.status_code,302)
        req=Request.objects.exclude(pk=self.req.pk).get();url=reverse("edit_request",args=[req.pk])
        response=self.client.get(url);self.assertContains(response,"Directory Alpha")
        token=response.context["submission_token"]
        response=self.client.post(url,{**self.payload([self.selected()[1]]),"action":"submit","submission_token":token})
        self.assertEqual(response.status_code,302);req.refresh_from_db();self.assertEqual(req.site_names,["Remote site"])

    def test_manual_site_names_are_escaped(self):
        req=self.draft();req.metadata_json["site_selections"]=[{"kind":"manual","key":"safe","name":"<script>alert(1)</script>"}];req.save();submit_request(req)
        for order in (1,2,3):approve_step(req.approvals.get(step_order=order),self.people[order-1])
        self.client.force_login(self.owner)
        response=self.client.get(reverse("permission_document",args=[req.pk]))
        self.assertContains(response,"&lt;script&gt;alert(1)&lt;/script&gt;");self.assertNotContains(response,"<script>alert(1)</script>")


class SiteConcurrencyTests(PermissionFixtures, TransactionTestCase):
    run_parallel = permission_tests.PermissionConcurrencyTests.run_parallel

    def scenario(self, changed):
        site = Site.objects.create(name="Concurrent directory site")
        req = self.make_request(permission_group="SITE_AUTHORIZATION", valid_from="2026-11-09", valid_to="2026-11-10",
            site_selections=json.dumps([{"kind":"site","site_id":site.pk},{"kind":"manual","key":"m","name":"Original site"}]),
            agent_selections=json.dumps([{"kind":"user","user_id":self.people[0].pk}]))
        self.returned(req)
        original = deepcopy(req.metadata_json["agent_attempts"][0])
        if changed:
            req.metadata_json["site_selections"][1]["name"]="Corrected site"
            req.save(update_fields=["metadata_json"])
        self.assertCountEqual(self.run_parallel([lambda:resubmit_request(req,self.owner)]*2),["ok","rejected"])
        req.refresh_from_db();attempts=req.metadata_json["agent_attempts"]
        self.assertEqual(len(attempts),2);self.assertEqual(attempts[0]["sites"],original["sites"])
        self.assertEqual(attempts[0]["people"],original["people"])
        self.assertEqual(attempts[0]["archive_log_id"],req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED").pk)
        self.assertEqual(attempts[1]["approval_ids"],list(req.approvals.order_by("step_order").values_list("pk",flat=True)))
        self.assertEqual(req.current_step_order,1 if changed else 2)
        self.assertEqual(req.audit_logs.filter(action="RESUBMITTED").count(),1)

    def test_site_snapshot_resumes_once_under_concurrency(self):self.scenario(False)
    def test_site_correction_restarts_once_under_concurrency(self):self.scenario(True)

    def test_directory_rename_waits_for_snapshot_commit(self):
        from . import services
        site=Site.objects.create(name="Name at submission")
        req=Request.objects.create(request_type=self.kind,request_number=str(uuid4()),submitted_by=self.owner,
            department=self.department,request_for_department=self.department,status="DRAFT",description="Concurrent snapshot",
            metadata_json={"permission_group":"SITE_AUTHORIZATION","microcom_agents":"Legacy agent",
                           "site_selections":[{"kind":"site","site_id":site.pk}]})
        captured,release,updating=Event(),Event(),Event()
        original=services.create_approval_steps
        def pause_submission(*args,**kwargs):
            captured.set()
            if not release.wait(10):raise RuntimeError("Snapshot lock test timed out")
            return original(*args,**kwargs)
        def submit():
            close_old_connections()
            try:submit_request(req)
            finally:close_old_connections()
        def rename():
            close_old_connections()
            try:
                updating.set();Site.objects.filter(pk=site.pk).update(name="Name after commit")
            finally:close_old_connections()
        with patch("requests_app.services.create_approval_steps",side_effect=pause_submission),ThreadPoolExecutor(max_workers=2) as pool:
            submission=pool.submit(submit)
            try:
                self.assertTrue(captured.wait(10))
                update=pool.submit(rename);self.assertTrue(updating.wait(10))
                with self.assertRaises(FutureTimeout):update.result(timeout=.2)
            finally:release.set()
            submission.result(timeout=10);update.result(timeout=10)
        req.refresh_from_db();site.refresh_from_db()
        self.assertEqual(req.site_names,["Name at submission"])
        self.assertEqual(site.name,"Name after commit")
