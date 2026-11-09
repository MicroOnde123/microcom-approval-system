"""Paginated read-only reports and explicit cross-page printing; local fixtures."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from .models import Request, RequestMaterialItem, RequestApproval, StockMovement
from .test_stock_safety import StockSafetyFixtures
from .views import material_reports
from invoicing.return_note_access import navigation, navigation_for_requests


@override_settings(MATERIAL_RETURN_NOTE_UI_ENABLED=True)
class MaterialReportPerformanceTests(StockSafetyFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("material_reports")
        self.now = timezone.now()
        self.rows = self.add_rows(60)

    def add_rows(self, count, start=0):
        rows = Request.objects.bulk_create([Request(request_number=f"BENCH-{i:04d}",
            request_type=self.request_type, submitted_by=self.user, department=self.department,
            request_for_department=self.department, status="APPROVED", stock_deducted=True,
            description="Synthetic benchmark", date_needed=date(2026, 10, 1), finalized_at=self.now)
            for i in range(start, start+count)])
        Request.objects.filter(pk__in=[r.pk for r in rows]).update(submitted_at=self.now)
        RequestMaterialItem.objects.bulk_create([RequestMaterialItem(request=r, material=self.material, quantity=10) for r in rows])
        StockMovement.objects.bulk_create([StockMovement(request=r, material=self.material, quantity=10 if kind=="OUT" else 2, movement_type=kind) for r in rows for kind in ("OUT", "RETURN")])
        return rows

    def test_three_pages_totals_ordering_and_invalid_pages(self):
        pages = [self.client.get(self.url, {"page": n}) for n in (1,2,3)]
        ids = []
        for response, count in zip(pages, (25,25,10)):
            self.assertEqual(response.context["page_obj"].paginator.count, 60)
            self.assertEqual(len(response.context["requests"]), count)
            ids += [r.pk for r in response.context["requests"]]
        self.assertEqual(ids, sorted([r.pk for r in self.rows], reverse=True))
        self.assertEqual(len(set(ids)), 60)
        self.assertEqual(self.client.get(self.url,{"page":"bad"}).context["page_obj"].number,1)
        self.assertEqual(self.client.get(self.url,{"page":"999999"}).context["page_obj"].number,3)
        self.assertEqual(self.client.get(self.url,{"page":"-1"}).status_code,200)

    def test_filters_history_balances_and_translations(self):
        before = (self.material.stock_quantity, list(StockMovement.objects.values()))
        for language, text in (("en","60 matching requests"),("fr","60 demandes correspondantes")):
            response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response,text)
            if language == "fr":
                self.assertContains(response,"Tout sélectionner sur cette page")
                self.assertContains(response,"Effacer la sélection")
                self.assertContains(response,"demandes sélectionnées")
            row = response.context["requests"][0]
            item = row.material_items.all()[0]
            self.assertEqual((item.return_ledger["issued_quantity"],item.return_ledger["returned_quantity"],item.return_ledger["remaining_quantity"]),(Decimal(10),Decimal(2),Decimal(8)))
            self.assertEqual(len(item.return_history),2)
        response=self.client.get(self.url,{"q":"BENCH-0059","date_from":"2026-10-01","date_to":"2026-10-01","department":self.department.pk})
        self.assertEqual(response.context["page_obj"].paginator.count,1)
        self.assertEqual(response.context["requests"][0].pk,self.rows[-1].pk)
        self.assertEqual(self.client.get(self.url,{"date_from":"2026-11-01"}).context["page_obj"].paginator.count,0)
        self.assertEqual(self.client.get(self.url,{"date_from":"invalid"}).context["page_obj"].paginator.count,0)
        self.material.refresh_from_db()
        self.assertEqual((self.material.stock_quantity,list(StockMovement.objects.values())),before)

    def test_queries_and_prefetch_remain_bounded(self):
        request=RequestFactory().get(self.url);request.user=self.user
        self.user.get_all_permissions()  # Normalize the reused RequestFactory actor cache.
        with CaptureQueriesContext(connection) as small: material_reports(request)
        self.add_rows(440,60)
        with CaptureQueriesContext(connection) as large: material_reports(request)
        self.assertEqual(len(small),len(large))
        self.assertLessEqual(len(large),18)
        self.assertFalse(any('FROM "requests_app_requestapproval"' in q["sql"] and 'COUNT' not in q["sql"] for q in large))
        page=self.client.get(self.url).context["requests"]
        self.assertEqual(len(page),25)

    def test_authorized_navigation_query_count_is_page_bounded(self):
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",codename__in=["view_invoice","view_materialreturnnote"]))
        step=self.workflow.steps.get()
        RequestApproval.objects.bulk_create([RequestApproval(request=r,workflow_step=step,step_order=1,approver_user=self.user,requires_stock_classification=True) for r in self.rows])
        self.user.get_all_permissions()
        request=RequestFactory().get(self.url);request.user=self.user
        with CaptureQueriesContext(connection) as small: material_reports(request)
        rows=self.add_rows(440,60)
        RequestApproval.objects.bulk_create([RequestApproval(request=r,workflow_step=step,step_order=1,approver_user=self.user,requires_stock_classification=True) for r in rows])
        with CaptureQueriesContext(connection) as large: material_reports(request)
        self.assertEqual(len(small),len(large))
        self.assertLessEqual(len(large),20)

    def test_bulk_print_explicit_cross_page_ids_duplicates_and_stale_ids(self):
        page=self.client.get(self.url)
        token=page.context["report_filter_token"]
        ids=[self.rows[0].pk,self.rows[25].pk,self.rows[55].pk]
        url=reverse("bulk_print_material_documents")
        response=self.client.post(url,{"selected_requests":ids+[ids[0]],"report_filter_scope":token})
        self.assertEqual(response.status_code,200)
        self.assertEqual({r.pk for r in response.context["requests"]},set(ids))
        Request.objects.filter(pk=ids[0]).update(status="RETURNED")
        self.assertEqual(self.client.post(url,{"selected_requests":ids,"report_filter_scope":token}).status_code,400)
        for bad in ("invalid","-1","999999999999999999999999"):
            self.assertEqual(self.client.post(url,{"selected_requests":[bad]}).status_code,400)
        self.assertEqual(self.client.post(url,{"selected_requests":[999999999]}).status_code,400)
        self.assertEqual(self.client.post(url,{"selected_requests":[ids[1]],"report_filter_scope":"tampered"}).status_code,400)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{"selected_requests":[ids[1]]}).status_code,403)

    def test_bulk_filter_proof_is_bound_to_current_login_session(self):
        token=self.client.get(self.url).context["report_filter_token"]
        self.client.logout();self.client.force_login(self.user)
        response=self.client.post(reverse("bulk_print_material_documents"),{
            "selected_requests":[self.rows[0].pk],"report_filter_scope":token},HTTP_ACCEPT_LANGUAGE="fr")
        self.assertContains(response,"La sélection est invalide ou a changé.",status_code=400)

    def test_bulk_scope_and_existing_two_copy_limit(self):
        page=self.client.get(self.url,{"q":"BENCH-0059"})
        token=page.context["report_filter_token"]
        self.assertEqual(self.client.post(reverse("bulk_print_material_documents"),{"selected_requests":[self.rows[0].pk],"report_filter_scope":token}).status_code,400)
        row=self.rows[-1]
        RequestMaterialItem.objects.bulk_create([RequestMaterialItem(request=row,material=self.material,quantity=1) for _ in range(6)])
        response=self.client.post(reverse("bulk_print_material_documents")+"?copies=2",{"selected_requests":[row.pk],"report_filter_scope":token})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context["requests"][0].print_copies,"1")
        self.assertTrue(response.context["two_copy_warning"])

    def test_excel_ignores_html_page_and_keeps_complete_dataset(self):
        response=self.client.get(reverse("export_material_report_excel"),{"page":"2"})
        self.assertEqual(response.status_code,200)
        book=load_workbook(BytesIO(response.content))
        ids={row[0] for row in list(book.worksheets[0].values)[4:]}
        self.assertEqual(ids,{r.request_number for r in self.rows})

    def test_batched_navigation_matches_existing_permissions_and_scope(self):
        actor=self.user
        ids=[r.pk for r in self.rows[:3]]
        self.assertEqual(navigation_for_requests(actor,ids),{})
        actor.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",codename__in=["view_invoice","view_materialreturnnote"]))
        RequestApproval.objects.create(request=self.rows[0],workflow_step=self.workflow.steps.get(),step_order=1,approver_user=actor,requires_stock_classification=True)
        self.assertEqual(navigation_for_requests(actor,ids),{ids[0]:{"unavailable":True}})
        # Compare the original fresh per-object authorization path.
        for pk in ids:
            self.assertEqual(navigation_for_requests(actor,ids).get(pk,{}),navigation(actor,request_id=pk))
        actor.is_active=False;actor.save()
        self.assertEqual(navigation_for_requests(actor,ids),{})


from invoicing.test_lifecycle import LifecycleFixtures


@override_settings(MATERIAL_RETURN_NOTE_UI_ENABLED=True)
class FinalizedReportNavigationTests(LifecycleFixtures,TestCase):
    def test_finalized_invoice_links_read_only_issue_and_revoked_rights(self):
        invoice=self.create();self.price(invoice);self.verified_sequence();invoice=self.finalize(invoice)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label="invoicing",codename="view_materialreturnnote"))
        for actor in (self.user,self.admin):
            self.assertEqual(navigation_for_requests(actor,[self.req.pk]).get(self.req.pk,{}),navigation(actor,request_id=self.req.pk))
        result=navigation_for_requests(self.user,[self.req.pk])[self.req.pk]
        self.assertTrue(result["can_read"]);self.assertFalse(result["can_issue"])
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",codename__in=["issue_materialreturnnote","add_materialreturnnote"]))
        self.assertTrue(navigation_for_requests(self.user,[self.req.pk])[self.req.pk]["can_issue"])
        self.user.user_permissions.clear()
        self.assertEqual(navigation_for_requests(self.user,[self.req.pk]),{})
