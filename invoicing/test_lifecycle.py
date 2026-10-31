"""Synthetic authorized lifecycle tests; no PDF or credit issuance claims."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import datetime, timezone as datetime_timezone
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override, activate, deactivate

from inventory.models import Material, Succursale
from requests_app.models import Request, RequestApproval, RequestMaterialItem, StockMovement
from requests_app.services import approve_step
from .admin import InvoiceAdmin
from .configuration import business_date
from .models import Invoice, InvoiceLine, DocumentSequence, InvoiceAuditEvent, InvoiceReturnExclusion
from .permissions import request_scope
from .services import create_draft, edit_draft, refresh_draft, finalize_invoice, draft_revision, database_now
from .tests import FinancialFixtures
from .words import amount_in_french


class LifecycleFixtures(FinancialFixtures):
    def setUp(self):
        activate("en")
        self.addCleanup(deactivate)
        super().setUp()
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",
            codename__in=["add_invoice","view_invoice","change_invoice","finalize_invoice"]))
        self.user = get_user_model().objects.get(pk=self.user.pk)

    def create(self,**kwargs):
        return create_draft(self.req.pk,self.user,currency=kwargs.get("currency","USD"))

    def price(self,invoice,price="2.00",user=None):
        user = user or self.user
        updated = edit_draft(invoice.pk,user,prices={line.pk:Decimal(price) if price is not None else None for line in invoice.lines.all()},
            note="Synthetic invoice",revision=draft_revision(invoice,user))
        invoice.refresh_from_db()
        return updated

    def verified_sequence(self,series="MAIN",start=1,year=None):
        sequence = DocumentSequence.objects.create(document_type="INVOICE",series=series,
            year=year or business_date(database_now(),"Africa/Kinshasa").year,
            number_format="FAC/{number:04d}/{year}",starting_value=start,next_counter=start)
        sequence.attest(self.admin,"Synthetic external numbering history checked")
        return sequence

    def finalize(self,invoice,user=None):
        user = user or self.user
        return finalize_invoice(invoice.pk,user,revision=draft_revision(invoice,user))

    def source_snapshot(self):
        return {name:list(model.objects.order_by("pk").values()) for name,model in (
            ("requests",Request),("approvals",RequestApproval),("movements",StockMovement),("materials",Material))}


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvoiceLifecycleTests(LifecycleFixtures,TestCase):
    def test_draft_is_explicit_unpriced_unnumbered_and_stock_is_unchanged(self):
        before = self.source_snapshot()
        self.assertFalse(Invoice.objects.exists())
        invoice = self.create()
        self.assertIsNone(invoice.number)
        self.assertIsNone(invoice.lines.get().unit_price)
        self.assertEqual(self.source_snapshot(),before)
        self.assertEqual(InvoiceAuditEvent.objects.get(invoice=invoice).event_type,"DRAFT_CREATED")
        self.assertFalse(DocumentSequence.objects.exists())

    def test_same_currency_catalogue_prices_only_and_no_conversion(self):
        self.material.unit_price = Decimal("3.25")
        self.material.currency = "EUR"
        self.material.save()
        invoice = self.create(currency="USD")
        self.assertIsNone(invoice.lines.get().unit_price)

    def test_catalogue_zero_and_manual_zero_are_valid(self):
        self.material.unit_price = 0
        self.material.currency = "USD"
        self.material.save()
        invoice = self.create()
        self.assertEqual(invoice.lines.get().unit_price,0)
        self.price(invoice,"0")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        self.assertEqual(invoice.total,0)
        self.assertEqual(invoice.amount_words_fr,"zéro dollar américain")

    def test_client_and_unconfirmed_requests_are_rejected(self):
        Request.objects.filter(pk=self.req.pk).update(classification="CLIENT",succursale=None)
        with self.assertRaises(ValidationError):
            self.create()
        Request.objects.filter(pk=self.req.pk).update(classification="MICROCOM",succursale=self.branch)
        self.req.approvals.update(requires_stock_classification=False)
        with self.assertRaises((PermissionDenied,ValidationError)):
            self.create()
        self.assertFalse(Invoice.objects.exists())

    def test_pending_and_missing_issue_requests_are_rejected(self):
        Request.objects.filter(pk=self.req.pk).update(status="IN_REVIEW")
        with self.assertRaises(ValidationError):
            self.create()
        Request.objects.filter(pk=self.req.pk).update(status="APPROVED")
        StockMovement.objects.filter(pk=self.out.pk).delete()
        with self.assertRaises(ValidationError):
            self.create()

    def test_inactive_historical_branch_and_net_return_allocation(self):
        self.branch.is_active = False
        self.branch.save()
        returned,_ = self.restore(3)
        invoice = self.create()
        self.assertEqual(invoice.lines.get().quantity,7)
        self.assertEqual(InvoiceReturnExclusion.objects.get(return_movement=returned).quantity,3)
        self.price(invoice)
        self.verified_sequence()
        invoice = self.finalize(invoice)
        self.assertEqual(invoice.total,14)
        self.assertEqual(self.balance(),93)

    def test_duplicate_lines_multiple_outs_and_legacy_zeros_are_blocked(self):
        duplicate = RequestMaterialItem.objects.create(request=self.req,material=self.material,quantity=1)
        with self.assertRaises(ValidationError):
            self.create()
        duplicate.delete()
        extra = StockMovement.objects.create(request=self.req,material=self.material,movement_type="OUT",quantity=1)
        with self.assertRaises(ValidationError):
            self.create()
        extra.delete()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE requests_app_requestmaterialitem SET quantity=0 WHERE id=%s",[self.item.pk])
            cursor.execute("UPDATE requests_app_stockmovement SET quantity=0 WHERE id=%s",[self.out.pk])
        with self.assertRaises(ValidationError):
            self.create()
        self.out.refresh_from_db()
        self.assertEqual(self.out.quantity,0)
        self.assertIsNone(self.out.return_operation_token)

    def test_duplicate_creation_and_unsupported_currency(self):
        with self.assertRaises(ValidationError):
            self.create(currency="ZZZ")
        self.create()
        with self.assertRaises(ValidationError):
            self.create()
        self.assertEqual(Invoice.objects.count(),1)

    def test_missing_price_prevents_finalization_and_number_consumption(self):
        invoice = self.create()
        sequence = self.verified_sequence()
        with self.assertRaises(ValidationError):
            self.finalize(invoice)
        invoice.refresh_from_db()
        sequence.refresh_from_db()
        self.assertEqual((invoice.status,invoice.number,sequence.next_counter),("DRAFT",None,1))

    def test_invalid_price_edit_is_atomic_and_null_is_preserved(self):
        invoice = self.create()
        before = self.source_snapshot()
        for value in (Decimal("-1"),Decimal("0.00001"),Decimal("NaN"),0.1):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                edit_draft(invoice.pk,self.user,prices={invoice.lines.get().pk:value},note="Bad",revision=draft_revision(invoice,self.user))
        self.assertIsNone(invoice.lines.get().unit_price)
        self.price(invoice,None)
        self.assertEqual(self.source_snapshot(),before)

    def test_round_half_up_and_sum_rounded_lines(self):
        second = Material.objects.create(category=self.category,name="Synthetic second",code="SECOND",unit="pcs",stock_quantity=100)
        req,first_item = self.make_request(quantity=Decimal("0.01"))
        RequestMaterialItem.objects.create(request=req,material=second,quantity=Decimal("0.01"))
        approve_step(req.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        invoice = create_draft(req.pk,self.user,currency="EUR")
        self.price(invoice,"0.50")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        self.assertEqual(list(invoice.lines.values_list("line_total",flat=True)),[Decimal("0.01"),Decimal("0.01")])
        self.assertEqual(invoice.total,Decimal("0.02"))
        self.assertEqual(invoice.amount_words_fr,"zéro euro et deux centimes")

    def test_new_return_requires_explicit_refresh_and_preserves_entered_prices(self):
        invoice = self.create()
        self.price(invoice,"3")
        sequence = self.verified_sequence()
        self.restore(4)
        with self.assertRaises(ValidationError):
            self.finalize(invoice)
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_counter,1)
        refresh_draft(invoice.pk,self.user,revision=draft_revision(invoice,self.user))
        self.assertEqual((invoice.lines.get().quantity,invoice.lines.get().unit_price),(6,3))
        invoice = self.finalize(invoice)
        self.assertEqual(invoice.total,18)

    def test_fully_returned_request_has_zero_net_without_changing_history(self):
        self.restore(10)
        before = self.source_snapshot()
        invoice = self.create()
        self.price(invoice,"2")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        self.assertEqual(invoice.lines.get().quantity,0)
        self.assertEqual(invoice.total,0)
        self.assertEqual(self.source_snapshot(),before)

    def test_stale_price_form_does_not_overwrite_newer_draft(self):
        invoice = self.create()
        stale = draft_revision(invoice,self.user)
        self.price(invoice,"4")
        with self.assertRaises(ValidationError):
            edit_draft(invoice.pk,self.user,prices={invoice.lines.get().pk:Decimal("9")},note="Stale",revision=stale)
        self.assertEqual(invoice.lines.get().unit_price,4)

    def test_changed_company_requires_new_attestation(self):
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        self.configuration.company_address = "New synthetic address"
        self.configuration.save()
        with self.assertRaises(ValidationError):
            self.finalize(invoice)
        from .models import CompanyVerification
        CompanyVerification.attest(self.configuration,self.admin)
        self.assertEqual(self.finalize(invoice).company_snapshot["company_address"],"New synthetic address")

    def test_numbering_starts_at_verified_external_counter_and_is_idempotent(self):
        invoice = self.create()
        self.price(invoice)
        sequence = self.verified_sequence(start=350)
        invoice = self.finalize(invoice)
        expected = f"FAC/0350/{invoice.issue_date.year}"
        self.assertEqual(invoice.number,expected)
        self.assertEqual(invoice.audit_metadata["sequence_snapshot"]["starting_value"],350)
        self.assertEqual(invoice.audit_metadata["sequence_snapshot"]["verified_by_id"],self.admin.pk)
        stale = "intentionally-irrelevant-after-finalization"
        again = finalize_invoice(invoice.pk,self.user,revision=stale)
        sequence.refresh_from_db()
        self.assertEqual((again.number,sequence.next_counter),(expected,351))
        self.assertEqual(InvoiceAuditEvent.objects.filter(invoice=invoice,event_type="FINALIZED").count(),1)

    def test_unverified_or_wrong_year_sequence_does_not_issue(self):
        invoice = self.create()
        self.price(invoice)
        sequence = self.verified_sequence(year=business_date(database_now(),"Africa/Kinshasa").year+1)
        with self.assertRaises(ValidationError):
            self.finalize(invoice)
        current = self.verified_sequence()
        current.number_format = "NEW/{year}/{number}"
        current.save()
        with self.assertRaises(ValidationError):
            self.finalize(invoice)
        self.assertIsNone(Invoice.objects.get(pk=invoice.pk).number)

    def test_annual_sequence_selection_at_kinshasa_new_year_and_wait_boundary(self):
        from .services import _issuance_sequence
        old = self.verified_sequence(year=2026,start=350)
        new = self.verified_sequence(year=2027,start=7)
        before = datetime(2026,12,31,22,59,59,tzinfo=datetime_timezone.utc)
        after = datetime(2026,12,31,23,0,0,tzinfo=datetime_timezone.utc)
        for moment,expected,year,counter in ((before,old,2026,350),(after,new,2027,7)):
            with patch("invoicing.services.database_now",return_value=moment):
                sequence,stamp,day = _issuance_sequence("MAIN",self.configuration)
            self.assertEqual((sequence.pk,day.year,sequence.next_counter),(expected.pk,year,counter))
            self.assertEqual(sequence.number_format.format(number=counter,year=day.year),f"FAC/{counter:04d}/{year}")
        with patch("invoicing.services.database_now",side_effect=[before,after]):
            with self.assertRaises(ValidationError):
                _issuance_sequence("MAIN",self.configuration)
        old.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual((old.next_counter,new.next_counter),(350,7))

    def test_failures_after_counter_update_roll_back_every_financial_write(self):
        invoice = self.create()
        self.price(invoice)
        sequence = self.verified_sequence()
        before = self.source_snapshot()
        with connection.cursor() as cursor:
            cursor.execute("SELECT number,document_type,document_id FROM invoicing_finalreference")
            registry_before = cursor.fetchall()
        with patch("invoicing.services._event",side_effect=ValidationError("Synthetic failure")):
            with self.assertRaises(ValidationError):
                self.finalize(invoice)
        invoice.refresh_from_db()
        sequence.refresh_from_db()
        self.assertEqual((invoice.status,invoice.number,sequence.next_counter),("DRAFT",None,1))
        with connection.cursor() as cursor:
            cursor.execute("SELECT number,document_type,document_id FROM invoicing_finalreference")
            self.assertCountEqual(cursor.fetchall(), registry_before)
        self.assertEqual(self.source_snapshot(),before)

    def test_snapshot_and_words_do_not_change_when_catalogues_change(self):
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        invoice = self.finalize(invoice)
        snapshot = (invoice.company_snapshot,invoice.succursale_snapshot,invoice.amount_words_fr,invoice.branding_snapshot)
        self.assertEqual(invoice.branding_snapshot["strategy"],"embedded-content")
        self.material.name = "Changed catalogue name"
        self.material.unit_price = 99
        self.material.currency = "EUR"
        self.material.save()
        self.branch.name = "Changed branch name"
        self.branch.save()
        self.configuration.company_name = "Changed company"
        self.configuration.save()
        invoice.refresh_from_db()
        self.assertEqual((invoice.company_snapshot,invoice.succursale_snapshot,invoice.amount_words_fr,invoice.branding_snapshot),snapshot)
        self.assertNotIn("Changed",invoice.lines.get().description_snapshot)
        self.client.force_login(self.user)
        response = self.client.get(reverse("invoicing:detail",args=[invoice.pk]))
        self.assertNotContains(response,"Changed catalogue")
        self.assertNotContains(response,"Changed branch")
        self.assertNotContains(response,"Changed company")

    def test_ordinary_orm_bulk_and_admin_edits_of_finalized_invoice_are_denied(self):
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        invoice = self.finalize(invoice)
        with self.assertRaises(ValidationError):
            invoice.save()
        with self.assertRaises(ValidationError):
            Invoice.objects.filter(pk=invoice.pk).update(total=0)
        with self.assertRaises(ValidationError):
            invoice.lines.all().delete()
        self.client.force_login(self.admin)
        url = reverse("admin:invoicing_invoice_change",args=[invoice.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{"total":"0","status":"DRAFT"}).status_code,403)
        self.assertEqual(self.client.post(reverse("admin:invoicing_invoice_delete",args=[invoice.pk]),{"post":"yes"}).status_code,403)
        invoice.refresh_from_db()
        self.assertEqual(invoice.total,20)

    def test_submitter_and_stock_flag_do_not_grant_invoice_access(self):
        invoice = self.create()
        for user in (self.other,get_user_model().objects.create_user(username="unassigned-stock",can_manage_stock=True)):
            self.client.force_login(user)
            for name,args in (("list",[]),("detail",[invoice.pk]),("edit",[invoice.pk]),("finalize",[invoice.pk]),("create",[self.req.pk])):
                self.assertEqual(self.client.get(reverse("invoicing:"+name,args=args)).status_code,403)
            with self.assertRaises(PermissionDenied):
                finalize_invoice(invoice.pk,user,revision="forged")

    def test_explicit_permission_does_not_grant_unrelated_employee_object_access(self):
        self.other.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",codename__in=["view_invoice","change_invoice","add_invoice","finalize_invoice"]))
        user = get_user_model().objects.get(pk=self.other.pk)
        invoice = self.create()
        with self.assertRaises(PermissionDenied):
            edit_draft(invoice.pk,user,prices={},note="",revision="forged")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("invoicing:detail",args=[invoice.pk])).status_code,403)

    def test_alternate_reviewer_and_explicit_staff_global_scope(self):
        self.req.approvals.update(alternate_approver_user=self.other)
        self.other.user_permissions.add(Permission.objects.get(codename="view_invoice",content_type__app_label="invoicing"))
        invoice = self.create()
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("invoicing:detail",args=[invoice.pk])).status_code,200)
        staff = get_user_model().objects.create_user(username="synthetic-invoice-staff",is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",codename__in=["view_invoice","manage_all_invoices"]))
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("invoicing:detail",args=[invoice.pk])).status_code,200)

    def test_later_approver_with_permissions_is_not_a_stock_reviewer(self):
        from workflows.models import ApprovalWorkflowStep
        step = ApprovalWorkflowStep.objects.create(workflow=self.workflow,step_order=2,approver_user=self.other)
        RequestApproval.objects.create(request=self.req,workflow_step=step,step_order=2,approver_user=self.other,
            acted_by=self.other,status="APPROVED")
        self.other.user_permissions.add(*Permission.objects.filter(content_type__app_label="invoicing",
            codename__in=["add_invoice","view_invoice","change_invoice","finalize_invoice"]))
        other = get_user_model().objects.get(pk=self.other.pk)
        self.assertFalse(request_scope(other).filter(pk=self.req.pk).exists())
        with self.assertRaises(PermissionDenied):
            create_draft(self.req.pk,other,currency="USD")

    def test_bilingual_pages_validation_and_success_messages(self):
        self.client.force_login(self.user)
        for language,title,error in (("en","Create invoice draft","A confirmed Microcom"),("fr","Créer une facture brouillon","Une classification Microcom confirmée")):
            Request.objects.filter(pk=self.req.pk).update(classification="CLIENT",succursale=None)
            response = self.client.post(reverse("invoicing:create",args=[self.req.pk]),{"currency":"USD"},HTTP_ACCEPT_LANGUAGE=language)
            self.assertContains(response,title)
            self.assertContains(response,error)
            Request.objects.filter(pk=self.req.pk).update(classification="MICROCOM",succursale=self.branch)
        invoice = self.create()
        for language,title in (("en","Edit invoice draft"),("fr","Modifier la facture brouillon")):
            self.assertContains(self.client.get(reverse("invoicing:edit",args=[invoice.pk]),HTTP_ACCEPT_LANGUAGE=language),title)
        self.price(invoice)
        self.verified_sequence()
        url = reverse("invoicing:finalize",args=[invoice.pk])
        response = self.client.post(url,{"series":"MAIN","revision":draft_revision(invoice,self.user),"confirm":"on"},HTTP_ACCEPT_LANGUAGE="fr",follow=True)
        self.assertContains(response,"Facture finalisée")
        self.assertContains(response,"lecture seule")

    def test_forged_line_submission_and_csrf_are_rejected(self):
        invoice = self.create()
        self.client.force_login(self.user)
        url = reverse("invoicing:edit",args=[invoice.pk])
        response = self.client.post(url,{"revision":draft_revision(invoice,self.user),"note":"Synthetic",
            "prices-TOTAL_FORMS":"1","prices-INITIAL_FORMS":"1","prices-0-line_id":"999999","prices-0-unit_price":"0"})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(invoice.lines.get().unit_price)
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(reverse("invoicing:finalize",args=[invoice.pk]),{}).status_code,403)

    def test_full_browser_lifecycle_and_validation_in_both_languages(self):
        self.client.force_login(self.user)
        self.verified_sequence()
        for language,created,saved,finalized in (("en","Invoice draft created.","Invoice draft saved.","Invoice finalized."),
                                               ("fr","Facture brouillon créée.","Facture brouillon enregistrée.","Facture finalisée.")):
            if language=="en":
                req = self.req
            else:
                req,item = self.make_request()
                approve_step(req.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
            response = self.client.post(reverse("invoicing:create",args=[req.pk]),{"currency":"USD"},HTTP_ACCEPT_LANGUAGE=language,follow=True)
            self.assertContains(response,created)
            invoice = Invoice.objects.get(request=req)
            line = invoice.lines.get()
            data = {"note":"Synthetic browser check","revision":draft_revision(invoice,self.user),
                "prices-TOTAL_FORMS":"1","prices-INITIAL_FORMS":"1","prices-0-line_id":line.pk,"prices-0-unit_price":"-1"}
            url = reverse("invoicing:edit",args=[invoice.pk])
            response = self.client.post(url,data,HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context["prices"].errors[0]["unit_price"])
            self.assertIsNone(invoice.lines.get().unit_price)
            data["prices-0-unit_price"] = "0"
            response = self.client.post(url,data,HTTP_ACCEPT_LANGUAGE=language,follow=True)
            self.assertContains(response,saved)
            invoice.refresh_from_db()
            response = self.client.post(reverse("invoicing:finalize",args=[invoice.pk]),
                {"revision":draft_revision(invoice,self.user),"series":"MAIN","confirm":"on"},HTTP_ACCEPT_LANGUAGE=language,follow=True)
            self.assertContains(response,finalized)
            self.assertEqual(Invoice.objects.get(pk=invoice.pk).total,0)

    def test_admin_configuration_and_attestation_actions_enforce_permissions(self):
        from .models import CompanyVerification
        self.client.force_login(self.admin)
        day = business_date(database_now(),"Africa/Kinshasa")
        response = self.client.post(reverse("admin:invoicing_documentsequence_add"),{
            "document_type":"INVOICE","year":day.year,"series":"MAIN","number_format":"FAC/{number:04d}/{year}",
            "starting_value":350,"verification_evidence":"Synthetic external history checked","_save":"Save"})
        self.assertEqual(response.status_code,302)
        sequence = DocumentSequence.objects.get(series="MAIN")
        self.assertEqual(sequence.next_counter,350)
        self.assertFalse(sequence.is_verified)
        self.client.post(reverse("admin:invoicing_documentsequence_changelist"),{
            "action":"verify_numbering_history","_selected_action":[sequence.pk]})
        sequence.refresh_from_db()
        self.assertTrue(sequence.is_verified)
        self.configuration.company_address = "New synthetic verified address"
        self.configuration.save()
        self.client.post(reverse("admin:core_companydocumentsettings_changelist"),{
            "action":"verify_company_information","_selected_action":[self.configuration.pk]})
        self.assertTrue(CompanyVerification.objects.order_by("-pk").first().is_current)
        staff = get_user_model().objects.create_user(username="synthetic-config-only",is_staff=True)
        staff.user_permissions.add(Permission.objects.get(content_type__app_label="core",codename="change_companydocumentsettings"))
        self.client.force_login(staff)
        count = CompanyVerification.objects.count()
        self.client.post(reverse("admin:core_companydocumentsettings_changelist"),{
            "action":"verify_company_information","_selected_action":[self.configuration.pk]})
        self.assertEqual(CompanyVerification.objects.count(),count)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvoiceLifecycleConcurrencyTests(LifecycleFixtures,TransactionTestCase):
    def _post_teardown(self):
        try:
            super()._post_teardown()
        finally:
            # This technical SQL-owned table has no ORM model; Django flush does
            # not include it. Only disposable synthetic test evidence is removed.
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE invoicing_finalreference")

    def test_concurrent_finalization_is_idempotent_and_consumes_one_counter(self):
        invoice = self.create()
        self.price(invoice)
        sequence = self.verified_sequence()
        revision = draft_revision(invoice,self.user)
        gate = Barrier(2)
        def finalize():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                gate.wait(timeout=10)
                return finalize_invoice(invoice.pk,user,revision=revision).number
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:finalize(),range(2)))
        self.assertEqual(results[0],results[1])
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_counter,2)
        self.assertEqual(InvoiceAuditEvent.objects.filter(invoice=invoice,event_type="FINALIZED").count(),1)

    def test_distinct_invoices_share_a_locked_sequence_without_duplicates(self):
        one = self.create()
        self.price(one)
        req,item = self.make_request()
        approve_step(req.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        two = create_draft(req.pk,self.user,currency="USD")
        self.price(two)
        sequence = self.verified_sequence()
        revisions = {row.pk:draft_revision(row,self.user) for row in (one,two)}
        gate = Barrier(2)
        def finalize(pk):
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                gate.wait(timeout=10)
                return finalize_invoice(pk,user,revision=revisions[pk]).number
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(finalize,[one.pk,two.pk]))
        self.assertEqual(len(set(results)),2)
        self.assertEqual(set(Invoice.objects.values_list("sequence_counter",flat=True)),{1,2})
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_counter,3)

    def test_concurrent_draft_creation_cannot_duplicate_invoice(self):
        gate = Barrier(2)
        def create():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                gate.wait(timeout=10)
                try:
                    create_draft(self.req.pk,user,currency="USD")
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:create(),range(2)))
        self.assertCountEqual(results,["created","rejected"])
        self.assertEqual(Invoice.objects.filter(request=self.req).count(),1)
        self.assertEqual(self.balance(),90)

    def test_finalization_serializes_with_existing_return_service(self):
        from . import services
        from requests_app.stock_services import return_material_stock
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        revision = draft_revision(invoice,self.user)
        token = self.token()
        locked = Event()
        release = Event()
        original = services._match_net
        def pause(*args):
            result = original(*args)
            locked.set()
            if not release.wait(10):
                raise RuntimeError("Synthetic synchronization timeout")
            return result
        def finalize():
            close_old_connections()
            try:
                return finalize_invoice(invoice.pk,get_user_model().objects.get(pk=self.user.pk),revision=revision).pk
            finally:
                connection.close()
        def restore():
            close_old_connections()
            try:
                return return_material_stock(self.item.pk,get_user_model().objects.get(pk=self.user.pk),Decimal("3"),"Synthetic post-invoice return",token)[0].pk
            finally:
                connection.close()
        with patch("invoicing.services._match_net",side_effect=pause),ThreadPoolExecutor(max_workers=2) as pool:
            finalizing = pool.submit(finalize)
            try:
                self.assertTrue(locked.wait(10))
                returning = pool.submit(restore)
                with self.assertRaises(TimeoutError):
                    returning.result(timeout=0.2)
            finally:
                release.set()
            self.assertEqual(finalizing.result(timeout=10),invoice.pk)
            returned = StockMovement.objects.get(pk=returning.result(timeout=10))
        invoice.refresh_from_db()
        self.assertEqual((invoice.lines.get().quantity,invoice.total,self.balance()),(10,20,93))
        self.assertGreater(returned.created_at,invoice.finalized_at)
