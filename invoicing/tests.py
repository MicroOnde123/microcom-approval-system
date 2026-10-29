"""Synthetic schema/guard tests, not invoice issuance or credit service tests."""
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction, close_old_connections
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from django.utils.translation import override

from core.models import CompanyDocumentSettings
from inventory.models import Succursale
from requests_app.models import RequestMaterialItem, StockMovement
from requests_app.services import approve_step
from requests_app.test_stock_safety import StockSafetyFixtures
from .configuration import business_date, validate_business_timezone
from .models import (CompanyVerification, CreditAllocation, CreditNote, DocumentArtifact,
    DocumentSequence, Invoice, InvoiceAuditEvent, InvoiceIssueAllocation, InvoiceLine,
    InvoiceReturnExclusion, CreditOperation)


class FinancialFixtures(StockSafetyFixtures):
    def setUp(self):
        super().setUp()
        self.workflow.steps.update(is_stock_review=True)
        self.branch = Succursale.objects.create(code="FIN", name="Synthetic branch", physical_address="12, avenue Équateur\nKinshasa")
        self.req, self.item = self.make_request()
        approve_step(self.req.approvals.get(), self.user, classification="MICROCOM", succursale=self.branch)
        self.req.refresh_from_db()
        self.admin = get_user_model().objects.create_superuser(username="synthetic-financial-admin", password="synthetic")
        self.configuration = CompanyDocumentSettings.objects.create(company_name="Synthetic Company",
            company_address="Synthetic address", contact_details="Synthetic contact")
        self.verification = CompanyVerification.attest(self.configuration, self.admin)
        self.out = StockMovement.objects.get(request=self.req, movement_type="OUT")

    def draft(self, **kwargs):
        values = dict(request=self.req, currency="USD", created_by=self.user, succursale=self.branch,
            classification_approval=self.req.approvals.get(), classification_actor=self.user,
            classification_at=self.req.classified_at, company_verification=self.verification)
        values.update(kwargs)
        return Invoice.objects.create(**values)

    def line(self, invoice, quantity=10, price=None):
        price = None if price is None else Decimal(str(price))
        return InvoiceLine.objects.create(invoice=invoice, material=self.material,
            material_code_snapshot="SYNTHETIC", description_snapshot="Synthetic material", unit_snapshot="pcs",
            quantity=quantity, unit_price=price, currency="USD",
            line_total=None if price is None else Decimal(str(quantity))*price)

    def allocation(self, line):
        return InvoiceIssueAllocation.objects.create(line=line, out_movement=self.out, quantity=line.quantity)

    def sequence(self, kind="INVOICE", series="MAIN", year=None):
        return DocumentSequence.objects.create(document_type=kind, series=series,
            year=year or business_date(timezone.now(), "Africa/Kinshasa").year,
            number_format=("FAC" if kind=="INVOICE" else "AV")+"/{number:04d}/{year}")

    def finalize_fixture(self, invoice, number=None):
        """Direct schema fixture transition; no real numbering allocation/API."""
        sequence = self.sequence()
        number = number or "SYNTHETIC-SCHEMA-" + uuid4().hex
        sequence.attest(self.admin, "Synthetic external-history check; schema test only")
        moment = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE invoicing_invoice SET status='FINALIZED', number=%s,
                sequence_id=%s, sequence_counter=1, finalized_by_id=%s, finalized_at=%s,
                issue_date=%s, company_snapshot=%s::jsonb, succursale_snapshot='{"code":"FIN"}',
                branding_snapshot='{"strategy":"embedded-content","sha256":"synthetic"}',
                request_reference_snapshot='SYNTHETIC', amount_words_fr='Montant synthétique',
                total=(SELECT sum(line_total) FROM invoicing_invoiceline WHERE invoice_id=%s) WHERE id=%s""",
                [number, sequence.pk, self.admin.pk, moment, business_date(moment, "Africa/Kinshasa"),
                 __import__("json").dumps(self.verification.configuration_snapshot), invoice.pk, invoice.pk])
        invoice.refresh_from_db()
        return invoice

    def expect_db_rejection(self, sql, params):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql, params)

    def credit_operation_fixture(self, invoice, kind="RESERVE", payload=None):
        """Synthetic SQL test context only, not an application operation service."""
        op = CreditOperation.objects.create(invoice=invoice,actor=self.user,kind=kind,
            reason="Synthetic schema test",payload=payload or {})
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('microcom.credit_operation',%s,true)",[str(op.pk)])
        return op

    def credit_fixture(self, invoice, **kwargs):
        with transaction.atomic():
            self.credit_operation_fixture(invoice,"CREATE")
            credit = CreditNote.objects.create(invoice=invoice,currency=invoice.currency,created_by=self.user,**kwargs)
            self.credit_operation_fixture(invoice)
            return credit

    def review_credit_fixture(self,credit):
        credit.refresh_from_db()
        with connection.cursor() as cursor:
            cursor.execute("SELECT inv_eb_review_payload(%s)",[credit.pk])
            payload = __import__('json').loads(cursor.fetchone()[0])
        op = self.credit_operation_fixture(credit.invoice,"REVIEW",payload)
        credit.reviewed_revision = credit.reservation_revision
        credit.reviewed_by = self.user
        credit.reviewed_at = timezone.now()
        credit.review_operation = op
        credit.save()
        credit.refresh_from_db()

    def finalize_credit_fixture(self, credit, number=None):
        """Direct synthetic schema transition; never allocates a business counter."""
        number = number or "SYNTHETIC-CREDIT-" + uuid4().hex
        sequence = self.sequence(kind="CREDIT")
        sequence.attest(self.admin, "Synthetic numbering-history evidence")
        invoice = credit.invoice
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE invoicing_creditallocation a SET description_snapshot=l.description_snapshot,
               audit_metadata=jsonb_build_object('line_snapshot',jsonb_build_object('version',1,
                 'material_code',l.material_code_snapshot,'unit',l.unit_snapshot,'rounding_policy',l.rounding_policy))
               FROM invoicing_invoiceissueallocation x JOIN invoicing_invoiceline l ON l.id=x.line_id
               WHERE a.issue_allocation_id=x.id AND a.credit_note_id=%s""",[credit.pk])
        self.review_credit_fixture(credit)
        self.credit_operation_fixture(invoice,"FINALIZE")
        moment = timezone.now()
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE invoicing_creditnote SET status='FINALIZED',number=%s,
                sequence_id=%s,sequence_counter=1,finalized_by_id=%s,finalized_at=%s,issue_date=%s,
                company_snapshot=%s::jsonb,succursale_snapshot=%s::jsonb,
                branding_snapshot=%s::jsonb,request_reference_snapshot=%s,snapshot_version=2,
                rounding_policy='CREDIT_CUMULATIVE_HALF_UP_2_V1',audit_metadata=%s::jsonb,
                amount_words_fr='Synthétique',total=(SELECT sum(line_total) FROM invoicing_creditallocation WHERE credit_note_id=%s)
                WHERE id=%s""",[number,sequence.pk,self.user.pk,moment,business_date(moment,"Africa/Kinshasa"),
                __import__('json').dumps(invoice.company_snapshot),__import__('json').dumps(invoice.succursale_snapshot),
                __import__('json').dumps(invoice.branding_snapshot),invoice.request_reference_snapshot,
                __import__('json').dumps({'credit_snapshot':{'version':1,'invoice_number':invoice.number,
                    'invoice_issue_date':invoice.issue_date.isoformat(),'invoice_rounding_policy':invoice.rounding_policy,
                    'invoice_snapshot_version':invoice.snapshot_version}}),credit.pk,credit.pk])
        credit.refresh_from_db()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FinancialSchemaTests(FinancialFixtures, TestCase):

    def test_valid_draft_has_no_number_and_does_not_touch_stock(self):
        before = self.balance(), list(StockMovement.objects.values())
        invoice = self.draft()
        self.line(invoice)
        self.assertIsNone(invoice.number)
        self.assertIsNone(invoice.finalized_at)
        self.assertEqual((self.balance(), list(StockMovement.objects.values())), before)
        self.assertFalse(DocumentSequence.objects.exists())

    def test_unknown_price_is_distinct_from_explicit_zero(self):
        line = self.line(self.draft())
        self.assertIsNone(line.unit_price)
        self.assertIsNone(line.line_total)
        line.unit_price = line.line_total = Decimal("0")
        line.save()
        line.refresh_from_db()
        self.assertEqual(line.unit_price, 0)

    def test_negative_prices_and_quantities_rejected_by_model_and_database(self):
        line = self.line(self.draft())
        for field in ("quantity", "unit_price", "line_total"):
            with self.subTest(field=field):
                original = getattr(line, field)
                setattr(line, field, Decimal("-1"))
                with self.assertRaises(ValidationError):
                    line.save()
                setattr(line, field, original)
                self.expect_db_rejection(f"UPDATE invoicing_invoiceline SET {field}=-1 WHERE id=%s", [line.pk])

    def test_only_one_invoice_per_request(self):
        self.draft()
        with self.assertRaises(ValidationError):
            self.draft()

    def test_draft_number_is_prohibited(self):
        with self.assertRaises(ValidationError):
            self.draft(number="NOT-ALLOCATED")

    def test_client_pending_and_missing_confirmation_are_ineligible(self):
        for change in ({"classification": "CLIENT", "succursale": None}, {"status": "IN_REVIEW"}, {"stock_deducted": False}):
            original = {key: getattr(self.req, key) for key in change}
            type(self.req).objects.filter(pk=self.req.pk).update(**change)
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.draft()
            type(self.req).objects.filter(pk=self.req.pk).update(**original)
        self.req.approvals.update(requires_stock_classification=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft()

    def test_inactive_legitimately_classified_succursale_is_allowed(self):
        self.branch.is_active = False
        self.branch.save()
        self.assertEqual(self.draft().succursale_id, self.branch.pk)

    def test_duplicate_lines_and_multiple_outs_block_only_financial_process(self):
        duplicate = RequestMaterialItem.objects.create(request=self.req, material=self.material, quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft()
        duplicate.delete()
        extra = StockMovement.objects.create(request=self.req, material=self.material, movement_type="OUT", quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft()
        self.assertTrue(StockMovement.objects.filter(pk=extra.pk).exists())
        self.assertEqual(self.balance(), 90)

    def test_historical_zero_out_remains_but_blocks_financial_allocation(self):
        # Synthetic legacy writes deliberately bypass present-day item validation.
        with connection.cursor() as cursor:
            cursor.execute("UPDATE requests_app_requestmaterialitem SET quantity=0 WHERE id=%s", [self.item.pk])
            cursor.execute("UPDATE requests_app_stockmovement SET quantity=0 WHERE id=%s", [self.out.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft()
        self.out.refresh_from_db()
        self.assertEqual(self.out.quantity, 0)
        self.assertIsNone(self.out.return_operation_token)

    def test_partial_return_net_billing_requires_exclusion(self):
        returned, _ = self.restore(3)
        invoice = self.draft()
        line = self.line(invoice, quantity=7, price=2)
        allocation = self.allocation(line)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.finalize_fixture(invoice)
        InvoiceReturnExclusion.objects.create(issue_allocation=allocation, return_movement=returned, quantity=3)
        self.finalize_fixture(invoice)
        self.assertEqual(invoice.total, 14)
        self.assertEqual(self.balance(), 93)

    def test_fully_returned_pair_can_be_recorded_as_zero_net(self):
        returned, _ = self.restore(10)
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice, quantity=0, price=0))
        InvoiceReturnExclusion.objects.create(issue_allocation=allocation, return_movement=returned, quantity=10)
        self.finalize_fixture(invoice)
        self.assertEqual(invoice.total, 0)
        self.assertEqual(self.balance(), 100)

    def test_wrong_out_and_excess_allocations_are_rejected(self):
        line = self.line(self.draft())
        with self.assertRaises(IntegrityError), transaction.atomic():
            InvoiceIssueAllocation.objects.create(line=line, out_movement=self.out, quantity=11)
        other = StockMovement.objects.create(request=self.req, material=self.material, movement_type="RETURN", quantity=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            InvoiceIssueAllocation.objects.create(line=line, out_movement=other, quantity=10)

    def test_finalized_parent_children_and_evidence_are_immutable(self):
        invoice = self.draft()
        line = self.line(invoice, price=2)
        allocation = self.allocation(line)
        self.finalize_fixture(invoice)
        for instance in (invoice, line, allocation):
            with self.subTest(model=type(instance).__name__):
                with self.assertRaises(ValidationError):
                    instance.save()
                with self.assertRaises(ValidationError):
                    instance.delete()
        for table, pk, assignment in (("invoice",invoice.pk,"total=1"),
                ("invoiceline",line.pk,"quantity=1"),("invoiceissueallocation",allocation.pk,"quantity=1")):
            self.expect_db_rejection(f"UPDATE invoicing_{table} SET {assignment} WHERE id=%s", [pk])
            self.expect_db_rejection(f"DELETE FROM invoicing_{table} WHERE id=%s", [pk])
        event = InvoiceAuditEvent.objects.create(invoice=invoice, event_type="SCHEMA_TEST", actor=self.admin,
            document_identifier="SYNTHETIC", details={"synthetic": True})
        self.expect_db_rejection("UPDATE invoicing_invoiceauditevent SET event_type='ALTERED' WHERE id=%s", [event.pk])
        self.expect_db_rejection("DELETE FROM invoicing_invoiceauditevent WHERE id=%s", [event.pk])

    def test_orm_bulk_paths_are_prohibited(self):
        invoice = self.draft()
        for operation in (lambda: Invoice.objects.update(currency="EUR"), lambda: Invoice.objects.all().delete(),
                lambda: Invoice.objects.bulk_update([invoice], ["currency"]), lambda: Invoice.objects.bulk_create([])):
            with self.assertRaises(ValidationError):
                operation()

    def test_protected_source_references(self):
        invoice = self.draft()
        self.allocation(self.line(invoice))
        for instance in (self.req, self.out, self.material, self.branch, self.verification):
            with self.assertRaises((ProtectedError, ValidationError)):
                instance.delete()

    def test_company_verification_content_binding_and_permissions(self):
        self.assertTrue(self.verification.is_current)
        with self.assertRaises(PermissionDenied):
            CompanyVerification.attest(self.configuration, self.user)
        self.configuration.company_address = "Changed synthetic address"
        self.configuration.save()
        self.assertFalse(self.verification.is_current)
        self.expect_db_rejection("DELETE FROM invoicing_companyverification WHERE id=%s", [self.verification.pk])

    def test_company_verification_invalidates_on_bulk_configuration_edit(self):
        CompanyDocumentSettings.objects.filter(pk=self.configuration.pk).update(invoice_number_format="INV/{year}/{number}")
        self.assertFalse(self.verification.is_current)

    def test_missing_company_data_cannot_be_attested(self):
        self.configuration.company_address = ""
        self.configuration.save()
        with self.assertRaises(ValidationError):
            CompanyVerification.attest(self.configuration, self.admin)

    def test_sequence_scopes_and_starting_counter_do_not_allocate(self):
        one = self.sequence()
        self.sequence(kind="CREDIT")
        self.sequence(series="OTHER")
        self.sequence(year=one.year+1)
        self.assertEqual(DocumentSequence.objects.count(), 4)
        with self.assertRaises(ValidationError):
            self.sequence()
        one.starting_value = one.next_counter = 350
        one.save()
        one.attest(self.admin, "Synthetic numbering-history evidence")
        self.assertTrue(one.is_verified)
        self.assertEqual(one.next_counter, 350)
        one.number_format = "NEW/{year}/{number}"
        one.save()
        self.assertFalse(one.is_verified)

    def test_sequence_missing_year_and_invalid_counters(self):
        sequence = self.sequence()
        for field, value in (("number_format", "FAC/{number}"), ("next_counter",0), ("year",10000)):
            original = getattr(sequence, field)
            setattr(sequence, field, value)
            with self.assertRaises(ValidationError):
                sequence.save()
            setattr(sequence, field, original)

    def test_backdating_and_mismatched_business_date_are_rejected(self):
        invoice = self.draft()
        self.allocation(self.line(invoice, price=2))
        # Completeness and time checks run before any financial status changes.
        sequence = self.sequence()
        sequence.attest(self.admin, "Synthetic numbering evidence")
        self.expect_db_rejection("""UPDATE invoicing_invoice SET status='FINALIZED',number='SYNTHETIC',
            sequence_id=%s,sequence_counter=1,finalized_by_id=%s,finalized_at=now()-interval '1 day',
            issue_date=current_date-1,total=20,company_snapshot='{"synthetic":true}',succursale_snapshot='{"synthetic":true}',
            branding_snapshot='{"synthetic":true}',request_reference_snapshot='SYNTHETIC',amount_words_fr='Synthétique'
            WHERE id=%s""",[sequence.pk,self.admin.pk,invoice.pk])
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "DRAFT")

    def test_finalized_children_cannot_be_added_or_reparented(self):
        invoice = self.draft()
        line = self.line(invoice, price=2)
        self.allocation(line)
        self.finalize_fixture(invoice)
        self.expect_db_rejection("UPDATE invoicing_invoiceline SET position=2 WHERE id=%s", [line.pk])
        self.expect_db_rejection("""INSERT INTO invoicing_invoiceline
            (invoice_id,material_id,material_code_snapshot,description_snapshot,unit_snapshot,quantity,
             unit_price,currency,line_total,position,rounding_policy)
            VALUES (%s,%s,'SYNTHETIC','Synthetic','pcs',1,2,'USD',2,2,'DECIMAL_HALF_UP_2_V1')""",
            [invoice.pk,self.material.pk])

    def test_stale_company_verification_blocks_finalized_transition(self):
        invoice = self.draft()
        self.allocation(self.line(invoice, price=2))
        self.configuration.contact_details = "Changed synthetic contact"
        self.configuration.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.finalize_fixture(invoice)

    def test_credit_draft_requires_finalized_invoice(self):
        invoice = self.draft()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CreditNote.objects.create(invoice=invoice, currency="USD", created_by=self.user)

    def test_current_company_timezone_must_match_document(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.draft(business_timezone="UTC")
        invoice = self.draft()
        self.allocation(self.line(invoice,price=2))
        self.finalize_fixture(invoice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CreditNote.objects.create(invoice=invoice,currency="USD",created_by=self.user,business_timezone="UTC")

    def test_business_year_boundary_is_kinshasa_not_utc_or_laptop(self):
        before = datetime(2026,12,31,22,59,59,tzinfo=datetime_timezone.utc)
        after = datetime(2026,12,31,23,0,0,tzinfo=datetime_timezone.utc)
        self.assertEqual(business_date(before, "Africa/Kinshasa").year, 2026)
        self.assertEqual(business_date(after, "Africa/Kinshasa").year, 2027)
        with self.assertRaises(ValidationError):
            business_date(after.replace(tzinfo=None), "Africa/Kinshasa")
        with self.assertRaises(ValidationError):
            validate_business_timezone("Not/A_Timezone")

    def test_partial_credit_schema_caps_return_and_original_billing(self):
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice, price=2))
        self.finalize_fixture(invoice)
        returned, _ = self.restore(3)
        credit = self.credit_fixture(invoice)
        def create(quantity):
            return CreditAllocation.objects.create(credit_note=credit, issue_allocation=allocation,
                return_movement=returned, quantity=quantity, unit_price_snapshot=2,
                line_total=quantity*2, description_snapshot="Synthetic credit schema")
        create(1)
        create(2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            create(1)
        self.assertEqual(self.balance(), 93)
        self.assertEqual(StockMovement.objects.filter(request=self.req).count(), 2)

    def test_preinvoice_return_exclusion_cannot_support_credit(self):
        returned, _ = self.restore(3)
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice, quantity=7, price=2))
        InvoiceReturnExclusion.objects.create(issue_allocation=allocation, return_movement=returned, quantity=3)
        self.finalize_fixture(invoice)
        credit = self.credit_fixture(invoice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CreditAllocation.objects.create(credit_note=credit, issue_allocation=allocation, return_movement=returned,
                quantity=1, unit_price_snapshot=2, line_total=2, description_snapshot="Synthetic")

    def test_final_credit_immutability_and_global_reference_uniqueness(self):
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice,price=2))
        self.finalize_fixture(invoice)
        returned,_ = self.restore(2)
        credit = self.credit_fixture(invoice)
        item = CreditAllocation.objects.create(credit_note=credit,issue_allocation=allocation,
            return_movement=returned,quantity=1,unit_price_snapshot=2,line_total=2,description_snapshot="Synthetic")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.finalize_credit_fixture(credit,number=invoice.number)
        self.finalize_credit_fixture(credit)
        for instance in (credit,item):
            with self.assertRaises(ValidationError):
                instance.save()
            with self.assertRaises(ValidationError):
                instance.delete()
        self.expect_db_rejection("UPDATE invoicing_creditnote SET total=0 WHERE id=%s",[credit.pk])
        self.expect_db_rejection("UPDATE invoicing_creditallocation SET quantity=2 WHERE id=%s",[item.pk])
        self.expect_db_rejection("DELETE FROM invoicing_creditallocation WHERE id=%s",[item.pk])
        with connection.cursor() as cursor:
            cursor.execute("SELECT number,document_type,document_id FROM invoicing_finalreference ORDER BY document_type")
            self.assertCountEqual(cursor.fetchall(),[(invoice.number,"INVOICE",invoice.pk),(credit.number,"CREDIT",credit.pk)])
        self.expect_db_rejection("DELETE FROM invoicing_finalreference WHERE number=%s",[invoice.number])

    def test_postinvoice_returns_cannot_exceed_net_invoiced_credit_cap(self):
        excluded,_ = self.restore(3)
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice,quantity=7,price=2))
        InvoiceReturnExclusion.objects.create(issue_allocation=allocation,return_movement=excluded,quantity=3)
        self.finalize_fixture(invoice)
        # Forged synthetic movement tests the independent original-billing cap.
        returned = StockMovement.objects.create(request=self.req,material=self.material,movement_type="RETURN",quantity=8)
        credit = self.credit_fixture(invoice)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CreditAllocation.objects.create(credit_note=credit,issue_allocation=allocation,return_movement=returned,
                quantity=8,unit_price_snapshot=2,line_total=16,description_snapshot="Synthetic")

    def test_artifact_is_separate_append_only_metadata(self):
        invoice = self.draft()
        self.allocation(self.line(invoice, price=2))
        self.finalize_fixture(invoice)
        artifact = DocumentArtifact.objects.create(invoice=invoice, document_type="INVOICE", language="fr",
            rendering_version="SCHEMA_ONLY", file_reference="synthetic-no-file-created", checksum="a"*64,
            rendering_status="PENDING", created_by=self.user)
        with self.assertRaises(ValidationError):
            artifact.save()
        self.expect_db_rejection("DELETE FROM invoicing_documentartifact WHERE id=%s", [artifact.pk])

    def test_english_french_labels_and_validation(self):
        for language, label in (("en", "Business timezone"), ("fr", "Fuseau horaire métier")):
            with override(language):
                self.assertEqual(str(Invoice._meta.get_field("business_timezone").verbose_name), label)
                self.assertEqual(str(InvoiceLine._meta.verbose_name), "Ligne de facture" if language=="fr" else "Invoice line")
                self.assertEqual(str(Invoice._meta.get_field("created_by").verbose_name), "Créé par" if language=="fr" else "Created by")
                with self.assertRaises(ValidationError) as error:
                    validate_business_timezone("Invalid/Zone")
                self.assertIn("fuseau" if language=="fr" else "timezone", str(error.exception))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FinancialConcurrencyTests(FinancialFixtures, TransactionTestCase):
    def test_nondefault_isolation_fails_closed_for_financial_aggregate_checks(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            self.draft()
        self.assertFalse(Invoice.objects.exists())

    def test_global_reference_uniqueness_under_repeatable_read(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        gate = Barrier(2)
        reference = "SYNTHETIC-RACE-" + uuid4().hex
        document_id = uuid4().int % (2**63 - 1)
        def claim(kind):
            close_old_connections()
            try:
                try:
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                            cursor.execute("SELECT count(*) FROM invoicing_finalreference")
                            gate.wait(timeout=10)
                            # Technical schema fixture only; no business issuance.
                            cursor.execute("INSERT INTO invoicing_finalreference(number,document_type,document_id) VALUES (%s,%s,%s)",[reference,kind,document_id])
                    return "accepted"
                except IntegrityError:
                    return "rejected"
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(claim,["INVOICE","CREDIT"]))
        self.assertCountEqual(outcomes,["accepted","rejected"])

    def test_sequence_row_can_be_locked_without_allocating_any_number(self):
        from concurrent.futures import ThreadPoolExecutor
        sequence = self.sequence()
        def cannot_lock():
            close_old_connections()
            try:
                from django.db import DatabaseError
                with transaction.atomic():
                    try:
                        DocumentSequence.objects.select_for_update(nowait=True).get(pk=sequence.pk)
                    except DatabaseError:
                        return True
                    return False
            finally:
                connection.close()
        with transaction.atomic():
            DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
            with ThreadPoolExecutor(max_workers=1) as executor:
                self.assertTrue(executor.submit(cannot_lock).result(timeout=10))
        sequence.refresh_from_db()
        self.assertEqual(sequence.next_counter, 1)

    def test_concurrent_partial_credits_cannot_overallocate_return(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        invoice = self.draft()
        allocation = self.allocation(self.line(invoice,price=2))
        self.finalize_fixture(invoice)
        returned, _ = self.restore(3)
        credits = [self.credit_fixture(invoice) for _ in range(2)]
        gate = Barrier(2)
        def allocate(credit_id):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                try:
                    with transaction.atomic():
                        self.credit_operation_fixture(invoice)
                        CreditAllocation.objects.create(credit_note_id=credit_id,issue_allocation_id=allocation.pk,
                            return_movement_id=returned.pk,quantity=2,unit_price_snapshot=2,line_total=4,description_snapshot="Synthetic race")
                    return "accepted"
                except IntegrityError:
                    return "rejected"
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(allocate,[credit.pk for credit in credits]))
        self.assertCountEqual(outcomes,["accepted","rejected"])
        self.assertEqual(CreditAllocation.objects.count(),1)
        self.assertEqual(self.balance(),93)
