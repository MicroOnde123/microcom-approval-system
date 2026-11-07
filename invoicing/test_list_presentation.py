"""Invoice-list UI regressions; synthetic, isolated PostgreSQL only."""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from requests_app.services import approve_step
from .test_lifecycle import LifecycleFixtures
from .models import Invoice


class InvoiceListPresentationTests(LifecycleFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.url = reverse("invoicing:list")
        from inventory.entry_services import receive_stock, new_token
        receive_stock(user=self.admin, mode="existing", token=new_token(self.admin,"existing"),
            material_id=self.material.pk, receipt_data={"quantity":"1000", "received_on":"2026-11-07"})

    def test_pagination_total_navigation_and_responsive_structure(self):
        self.create()
        for _ in range(25):
            request, _ = self.make_request()
            approve_step(request.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
            self.req = request
            self.create()
        first = self.client.get(self.url)
        second = self.client.get(self.url, {"page":2})
        self.assertEqual(first.context["page_obj"].paginator.count,26)
        self.assertEqual(len(first.context["page_obj"]),25)
        self.assertEqual(len(second.context["page_obj"]),1)
        self.assertContains(first,"26 matching invoices")
        self.assertContains(first,'role="columnheader"',count=8)
        self.assertContains(first,'role="cell"',count=25*8)
        self.assertContains(first,'class="status-badge status-DRAFT"',count=25)
        self.assertContains(first,self.configuration.company_name)
        self.assertContains(first,self.branch.name)
        self.assertContains(first,reverse("invoicing:detail",args=[first.context["page_obj"][0].pk]))
        self.assertEqual(self.client.get(self.url,{"page":"bad"}).context["page_obj"].number,1)
        self.assertEqual(self.client.get(self.url,{"page":"99999"}).context["page_obj"].number,2)
        self.assertEqual([row.pk for row in first.context["page_obj"]], list(Invoice.objects.order_by("-created_at","-pk").values_list("pk",flat=True)[:25]))

    def test_frozen_company_branch_dates_and_filter_values_both_languages(self):
        invoice = self.create(); self.price(invoice); self.verified_sequence(); invoice = self.finalize(invoice)
        original_branch = invoice.succursale_snapshot["name"]
        self.branch.name="NEW LIVE BRANCH"; self.branch.save()
        for lang in ("en","fr"):
            self.client.cookies["django_language"]=lang
            iso = invoice.issue_date.isoformat()
            page = self.client.get(self.url,{"date_from":iso,"date_to":iso,"q":invoice.number,"status":"FINALIZED"})
            self.assertEqual(page.context["page_obj"].paginator.count,1)
            self.assertContains(page,invoice.number)
            self.assertContains(page,"1 facture correspondante" if lang=="fr" else "1 matching invoice")
            self.assertContains(page,original_branch)
            self.assertContains(page,invoice.company_snapshot["company_name"])
            self.assertContains(page,invoice.issue_date.strftime("%d/%m/%Y") if lang=="fr" else iso)
            self.assertContains(page,'data-entry-date')
            self.assertNotContains(page,'type="date"')
            self.assertContains(page,'status-FINALIZED')
            localized = invoice.issue_date.strftime("%d/%m/%Y")
            self.assertEqual(self.client.get(self.url,{"date_from":localized,"date_to":localized}).context["page_obj"].paginator.count,1)

    def test_invalid_filters_preserve_input_and_field_errors(self):
        for lang in ("en","fr"):
            self.client.cookies["django_language"]=lang
            page=self.client.get(self.url,{"date_from":"31/02/2026","q":"Kept search"})
            self.assertContains(page,'value="31/02/2026"')
            self.assertContains(page,'value="Kept search"')
            self.assertContains(page,'id="id_date_from_error"')
            self.assertContains(page,'aria-invalid="true"')
            self.assertContains(page,'role="alert"')
            self.assertEqual(page.context["page_obj"].paginator.count,0)
            reversed_page=self.client.get(self.url,{"date_from":"2026-12-31","date_to":"2026-01-01"})
            self.assertIn("date_to",reversed_page.context["filter_form"].errors)
            self.assertContains(reversed_page,'id="id_date_to_error"')
            self.assertFalse(self.client.get(self.url,{"status":"invalid"}).context["filter_form"].is_valid())

    def test_candidate_cap_search_and_independence_from_invoice_filters(self):
        reference=self.req.request_number
        for _ in range(50):
            request,_=self.make_request()
            approve_step(request.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        page=self.client.get(self.url,{"q":"no invoice matches","status":"FINALIZED"})
        self.assertEqual(len(page.context["candidate_requests"]),50)
        self.assertTrue(page.context["candidate_has_more"])
        self.assertContains(page,"Only the 50 most recent matching requests")
        narrowed=self.client.get(self.url,{"candidate_q":reference,"date_from":"2026-01-01"})
        self.assertEqual([r.pk for r in narrowed.context["candidate_requests"]],[self.req.pk])
        self.assertFalse(narrowed.context["candidate_has_more"])
        self.assertEqual(narrowed.context["active_filters"]["date_from"],"2026-01-01")
        self.assertNotIn("candidate_q",narrowed.context["active_filters"])
        self.assertEqual(narrowed.context["page_obj"].paginator.count,0)
        self.assertEqual(len(self.client.get(self.url,{"candidate_q":"x"*201}).context["candidate_requests"]),0)

    def test_permissions_and_creation_actions(self):
        self.create()
        other=get_user_model().objects.create_user(username="list-no-access")
        self.client.force_login(other)
        self.assertEqual(self.client.get(self.url).status_code,403)
        self.client.force_login(self.user)
        self.assertTrue(self.client.get(self.url).context["can_create_invoice"])
        from django.contrib.auth.models import Permission
        self.user.user_permissions.remove(Permission.objects.get(codename="add_invoice"))
        self.client.force_login(self.user)
        page=self.client.get(self.url)
        self.assertEqual(page.status_code,200)
        self.assertNotContains(page,'id="invoice-candidates-title"')
