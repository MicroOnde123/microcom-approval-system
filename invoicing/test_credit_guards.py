"""E-B schema fixtures only: no application credit lifecycle or number allocator."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from decimal import Decimal
import json
from threading import Event
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from django.utils.translation import override

from requests_app.models import StockMovement
from requests_app.services import approve_step
from .models import CreditNote, CreditAllocation, CreditOperation, CreditReservationAudit, DocumentSequence
from .services import database_now
from .configuration import business_date
from .test_lifecycle import LifecycleFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CreditGuardFixtures(LifecycleFixtures, TransactionTestCase):
    def _post_teardown(self):
        try:
            super()._post_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE invoicing_finalreference")

    def setup_invoice(self, price="0.0050", quantity=3):
        self.req,self.item = self.make_request(quantity)
        approve_step(self.req.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        self.req.refresh_from_db()
        self.out = StockMovement.objects.get(request=self.req,movement_type="OUT")
        invoice = self.create()
        self.price(invoice,price)
        self.verified_sequence()
        self.invoice = self.finalize(invoice)
        self.issue_allocation = self.invoice.lines.get().issue_allocation
        self.returned,_ = self.restore(quantity)
        return self.invoice

    @contextmanager
    def write(self, kind="REBALANCE", payload=None):
        with transaction.atomic():
            op = self.credit_operation_fixture(self.invoice,kind,payload)
            yield op

    def new_credit(self, token=None):
        with self.write("CREATE",{"creation_token":str(token)} if token else {}):
            return CreditNote.objects.create(invoice=self.invoice,currency=self.invoice.currency,
                created_by=self.user,creation_operation_token=token)

    def allocation_row(self,credit,quantity=1,amount="0.01",returned=None):
        line = self.invoice.lines.get()
        return CreditAllocation.objects.create(credit_note=credit,issue_allocation=self.issue_allocation,
            return_movement=returned or self.returned,quantity=Decimal(quantity),unit_price_snapshot=line.unit_price,
            line_total=Decimal(amount),description_snapshot=line.description_snapshot,
            audit_metadata={"line_snapshot":{"version":1,"material_code":line.material_code_snapshot,
                "unit":line.unit_snapshot,"rounding_policy":line.rounding_policy}})

    def reserve(self,credit,quantity=1,amount="0.01",returned=None):
        with self.write("RESERVE"):
            return self.allocation_row(credit,quantity,amount,returned)

    def schema_transition(self,credit,**changes):
        """Synthetic direct model transition. No sequence counter is allocated."""
        credit.refresh_from_db()
        sequence = DocumentSequence.objects.filter(document_type="CREDIT").first()
        if sequence is None:
            sequence = self.sequence(kind="CREDIT")
            sequence.attest(self.admin,"Synthetic E-B schema fixture only")
        credit.company_snapshot = self.invoice.company_snapshot
        credit.succursale_snapshot = self.invoice.succursale_snapshot
        credit.branding_snapshot = self.invoice.branding_snapshot
        credit.request_reference_snapshot = self.invoice.request_reference_snapshot
        credit.snapshot_version = 2
        credit.rounding_policy = "CREDIT_CUMULATIVE_HALF_UP_2_V1"
        credit.audit_metadata = {"credit_snapshot":{"version":1,"invoice_number":self.invoice.number,
            "invoice_issue_date":self.invoice.issue_date.isoformat(),"invoice_rounding_policy":self.invoice.rounding_policy,
            "invoice_snapshot_version":self.invoice.snapshot_version}}
        credit.total = sum((row.line_total for row in credit.allocations.filter(released_at__isnull=True)),Decimal("0"))
        credit.amount_words_fr = "Montant synthétique — test de schéma uniquement"
        credit.status = "FINALIZED"
        credit.number = f"SYNTHETIC-CREDIT-{credit.pk}"
        credit.sequence = sequence
        credit.sequence_counter = credit.pk
        credit.finalized_by = self.user
        credit.finalized_at = database_now()
        credit.issue_date = business_date(credit.finalized_at,"Africa/Kinshasa")
        for key,value in changes.items():
            setattr(credit,key,value)
        credit.save()
        credit.refresh_from_db()
        return credit

    def review(self,credit):
        with transaction.atomic():
            self.review_credit_fixture(credit)


class CreditGuardTests(CreditGuardFixtures):
    def test_nullable_tokens_and_unique_creation_binding(self):
        self.setup_invoice()
        self.assertIsNone(self.new_credit().creation_operation_token)
        self.assertIsNone(self.new_credit().creation_operation_token)
        token = uuid4()
        self.new_credit(token)
        # Raw insert exercises database uniqueness independently of full_clean.
        with self.assertRaises(IntegrityError),self.write("CREATE",{"creation_token":str(token)}):
            with connection.cursor() as c:
                c.execute("""INSERT INTO invoicing_creditnote(invoice_id,currency,created_by_id,created_at,status,
                 business_timezone,company_snapshot,succursale_snapshot,branding_snapshot,request_reference_snapshot,
                 rounding_policy,amount_words_fr,snapshot_version,audit_metadata,reservation_revision,creation_operation_token)
                 VALUES(%s,'USD',%s,clock_timestamp(),'DRAFT','Africa/Kinshasa','{}','{}','{}','',
                  'DECIMAL_HALF_UP_2_V1','',1,'{}',0,%s)""",[self.invoice.pk,self.user.pk,str(token)])

    def test_permission_metadata_does_not_grant_existing_user(self):
        permission = Permission.objects.get(content_type__app_label="invoicing",codename="finalize_creditnote")
        self.assertFalse(self.user.has_perm("invoicing.finalize_creditnote"))
        self.assertFalse(self.user.user_permissions.filter(pk=permission.pk).exists())

    def test_operation_context_is_required_and_cannot_be_replayed_after_commit(self):
        self.setup_invoice()
        with self.assertRaises(IntegrityError),transaction.atomic():
            CreditNote.objects.create(invoice=self.invoice,currency="USD",created_by=self.user)
        with self.write("CREATE") as op:
            pass
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c:
                c.execute("SELECT set_config('microcom.credit_operation',%s,true)",[str(op.pk)])
            CreditNote.objects.create(invoice=self.invoice,currency="USD",created_by=self.user)

    def test_parent_reassignment_and_currency_are_blocked(self):
        self.setup_invoice()
        credit = self.new_credit()
        with self.assertRaises(IntegrityError),self.write():
            with connection.cursor() as c:
                c.execute("UPDATE invoicing_creditnote SET invoice_id=invoice_id+100000 WHERE id=%s",[credit.pk])
        with self.assertRaises(IntegrityError),self.write():
            credit.currency="EUR"
            credit.save()

    def test_residual_cent_reservations_are_deterministic_and_zero_is_valid(self):
        self.setup_invoice()
        credits = [self.new_credit() for _ in range(3)]
        with self.write("RESERVE"):
            # Reverse INSERT order; ordering is credit ID, then allocation ID.
            rows = [self.allocation_row(credits[index],amount=amount) for index,amount in ((2,"0.01"),(1,"0"),(0,"0.01"))]
        self.assertEqual(self.invoice.total,Decimal("0.02"))
        self.assertEqual(sum(r.line_total for r in rows),Decimal("0.02"))
        self.assertEqual(CreditReservationAudit.objects.count(),3)
        self.assertEqual(CreditAllocation.objects.filter(line_total=0).get().quantity,1)

    def test_three_finalized_partial_credits_total_exactly_original_two_cents(self):
        self.setup_invoice()
        credits=[self.new_credit() for _ in range(3)]
        for credit,amount in zip(credits,("0.01","0","0.01")):
            self.reserve(credit,amount=amount)
        before=self.source_snapshot()
        for credit in credits:
            self.review(credit)
            with self.write("FINALIZE"):
                self.schema_transition(credit)
        self.assertEqual(list(CreditNote.objects.order_by("pk").values_list("total",flat=True)),
                         [Decimal("0.01"),Decimal("0"),Decimal("0.01")])
        self.assertEqual(sum(CreditNote.objects.values_list("total",flat=True)),self.invoice.total)
        self.assertEqual(self.source_snapshot(),before)

    def test_raw_sql_amount_overcredit_cannot_commit(self):
        self.setup_invoice()
        credit=self.new_credit(); row=self.reserve(credit)
        before=CreditReservationAudit.objects.count()
        with self.assertRaises(IntegrityError),self.write():
            with connection.cursor() as c:
                c.execute("UPDATE invoicing_creditallocation SET line_total=99 WHERE id=%s",[row.pk])
        row.refresh_from_db()
        self.assertEqual(row.line_total,Decimal("0.01"))
        self.assertEqual(CreditReservationAudit.objects.count(),before)

    def test_incomplete_rebalance_fails_commit_and_rolls_back_audit_and_revision(self):
        self.setup_invoice()
        a,b = self.new_credit(),self.new_credit()
        first,second = self.reserve(a),self.reserve(b,amount="0")
        before = list(CreditNote.objects.values()),CreditReservationAudit.objects.count()
        with self.assertRaises(IntegrityError),self.write():
            second.line_total=Decimal("0.01")
            second.save()
        second.refresh_from_db()
        self.assertEqual(second.line_total,0)
        self.assertEqual((list(CreditNote.objects.values()),CreditReservationAudit.objects.count()),before)

    def test_out_of_order_finalization_rebalances_drafts_and_invalidates_review(self):
        self.setup_invoice()
        a,b = self.new_credit(),self.new_credit()
        first,second = self.reserve(a),self.reserve(b,amount="0")
        self.review(a)
        before = self.source_snapshot()
        with self.write("FINALIZE"):
            second.line_total=Decimal("0.01")
            second.save()
            first.line_total=Decimal("0")
            first.save()
            self.review_credit_fixture(b)
            op = self.credit_operation_fixture(self.invoice,"FINALIZE")
            self.schema_transition(b)
        a.refresh_from_db()
        self.assertIsNone(a.reviewed_revision)
        self.assertIsNone(a.review_operation_id)
        adjustments = CreditReservationAudit.objects.filter(allocation=first).order_by("pk")
        self.assertEqual((adjustments.last().previous_amount,adjustments.last().new_amount),(Decimal("0.01"),0))
        self.assertEqual(adjustments.last().operation.reason,"Synthetic schema test")
        self.assertEqual(self.source_snapshot(),before)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(a)
        with transaction.atomic():
            self.review_credit_fixture(a)
            self.credit_operation_fixture(self.invoice,"FINALIZE")
            self.schema_transition(a)
        self.assertEqual(sum(CreditNote.objects.values_list("total",flat=True)),Decimal("0.01"))

    def test_finalization_rejects_unrebalanced_other_draft_at_commit(self):
        self.setup_invoice()
        a,b = self.new_credit(),self.new_credit()
        self.reserve(a)
        second = self.reserve(b,amount="0")
        before = list(CreditNote.objects.values()),CreditOperation.objects.count()
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            second.line_total=Decimal("0.01")
            second.save()
            self.review_credit_fixture(b)
            self.credit_operation_fixture(self.invoice,"FINALIZE")
            self.schema_transition(b)
        self.assertEqual((list(CreditNote.objects.values()),CreditOperation.objects.count()),before)

    def test_release_preserves_evidence_and_requires_atomic_remaining_rebalance(self):
        self.setup_invoice()
        a,b = self.new_credit(),self.new_credit()
        first,second = self.reserve(a),self.reserve(b,amount="0")
        with self.assertRaises(IntegrityError),self.write("RELEASE") as op:
            first.released_at=timezone.now(); first.release_operation=op; first.save()
        first.refresh_from_db()
        with self.write("RELEASE") as op:
            first.released_at=timezone.now(); first.release_operation=op; first.save()
            second.line_total=Decimal("0.01"); second.save()
        self.assertEqual(CreditAllocation.objects.count(),2)
        self.assertEqual((first.quantity,first.line_total),(1,Decimal("0.01")))
        with self.assertRaises(ValidationError):
            first.quantity=2; first.save()
        with self.assertRaises(IntegrityError),self.write():
            with connection.cursor() as c:
                c.execute("DELETE FROM invoicing_creditallocation WHERE id=%s",[first.pk])

    def test_review_cannot_be_forged_and_adjustment_clears_review(self):
        self.setup_invoice(price="2")
        credit = self.new_credit()
        row = self.reserve(credit,amount="2")
        with self.assertRaises(IntegrityError),self.write("REVIEW",{}):
            credit.refresh_from_db(); credit.reviewed_revision=credit.reservation_revision
            credit.reviewed_by=self.user; credit.reviewed_at=timezone.now(); credit.save()
        self.review(credit)
        with self.write():
            row.quantity=2; row.line_total=Decimal("4"); row.save()
        credit.refresh_from_db()
        self.assertIsNone(credit.reviewed_revision)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit)

    def test_final_snapshot_must_match_original_even_after_live_catalogue_changes(self):
        self.setup_invoice(price="2")
        credit = self.new_credit(); self.reserve(credit,amount="2"); self.review(credit)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit,company_snapshot={"invented":"identity"})
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit,audit_metadata={})
        self.configuration.company_name="Changed live identity"; self.configuration.save()
        with self.write("FINALIZE"):
            final = self.schema_transition(credit)
        self.assertEqual(final.company_snapshot,self.invoice.company_snapshot)
        self.assertNotEqual(final.company_snapshot["company_name"],self.configuration.company_name)

    def test_line_snapshot_and_frozen_price_are_enforced(self):
        self.setup_invoice(price="2")
        credit = self.new_credit()
        with self.assertRaises(IntegrityError),self.write("RESERVE"):
            self.allocation_row(credit,amount="2").unit_price_snapshot
            with connection.cursor() as c:
                c.execute("UPDATE invoicing_creditallocation SET unit_price_snapshot=3")
        row = self.reserve(credit,amount="2")
        with self.write():
            row.audit_metadata={}; row.save()
        self.review(credit)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit)

    def test_multiple_allocations_same_return_are_supported_with_caps(self):
        self.setup_invoice(price="2")
        credit = self.new_credit()
        with self.write("RESERVE"):
            self.allocation_row(credit,1,"2"); self.allocation_row(credit,2,"4")
        self.assertEqual(credit.allocations.count(),2)
        with self.assertRaises(IntegrityError),self.write("RESERVE"):
            self.allocation_row(credit,1,"2")

    def test_invalid_return_provenance_zero_out_and_exclusions_are_blocked(self):
        self.setup_invoice(price="2")
        credit = self.new_credit()
        wrong = StockMovement.objects.create(request=self.req,material=self.material,movement_type="IN",quantity=1)
        with self.assertRaises(IntegrityError),self.write("RESERVE"):
            self.allocation_row(credit,1,"2",wrong)
        # Preserve an unrelated synthetic historical zero; it remains untouched.
        zero = StockMovement.objects.create(material=self.material,movement_type="OUT",quantity=0)
        self.reserve(credit,1,"2")
        zero.refresh_from_db(); self.assertEqual(zero.quantity,0); self.assertIsNone(zero.return_operation_token)

    def test_finalized_credit_allocation_and_audits_are_strictly_immutable(self):
        self.setup_invoice(price="2")
        credit = self.new_credit(); row=self.reserve(credit,amount="2"); self.review(credit)
        with self.write("FINALIZE"):
            self.schema_transition(credit)
        for query in ("UPDATE invoicing_creditnote SET total=0 WHERE id=%s",
                      "DELETE FROM invoicing_creditnote WHERE id=%s"):
            with self.assertRaises(IntegrityError),transaction.atomic():
                with connection.cursor() as c: c.execute(query,[credit.pk])
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c: c.execute("UPDATE invoicing_creditallocation SET line_total=0 WHERE id=%s",[row.pk])
        event=CreditReservationAudit.objects.get(allocation=row)
        with self.assertRaises(ValidationError): event.save()
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c: c.execute("DELETE FROM invoicing_creditreservationaudit WHERE id=%s",[event.pk])
        with self.assertRaises(IntegrityError),transaction.atomic():
            with connection.cursor() as c: c.execute("UPDATE invoicing_invoice SET total=0 WHERE id=%s",[self.invoice.pk])

    def test_bulk_paths_and_manufactured_audit_are_prohibited(self):
        self.setup_invoice()
        credit=self.new_credit(); row=self.reserve(credit)
        with self.assertRaises(ValidationError): CreditNote.objects.update(total=0)
        with self.assertRaises(ValidationError): CreditAllocation.objects.bulk_create([])
        op=CreditOperation.objects.first()
        with self.assertRaises(IntegrityError),transaction.atomic():
            CreditReservationAudit.objects.create(allocation=row,operation=op,new_amount=0,new_quantity=0)

    def test_year_and_cross_document_reference_guards_are_preserved(self):
        self.setup_invoice(price="2")
        credit=self.new_credit(); self.reserve(credit,amount="2"); self.review(credit)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit,number=self.invoice.number)
        with self.assertRaises(IntegrityError),self.write("FINALIZE"):
            self.schema_transition(credit,issue_date=business_date(database_now(),"Africa/Kinshasa").replace(year=2000))
        self.assertIsNone(CreditNote.objects.get(pk=credit.pk).number)

    def test_english_french_schema_labels_and_validation(self):
        for language,label,message in (("en","Credit operation","A credit operation reason is required."),
                                       ("fr","Opération d’avoir","Un motif d’opération d’avoir est requis.")):
            with override(language):
                self.assertEqual(str(CreditOperation._meta.verbose_name),label)
                with self.assertRaisesMessage(ValidationError,message):
                    CreditOperation(reason=" ").clean()

    def test_competing_reservations_serialize_before_credit_row_locks(self):
        self.setup_invoice(price="2")
        a,b=self.new_credit(),self.new_credit()
        entered,release,attempting=Event(),Event(),Event()
        def reserve(credit,first):
            close_old_connections()
            try:
                if not first: attempting.set()
                try:
                    with self.write("RESERVE"):
                        if first:
                            entered.set()
                            if not release.wait(10): raise RuntimeError("Synthetic synchronization timeout")
                        self.allocation_row(credit,2,"4")
                    return "accepted"
                except IntegrityError:
                    return "rejected"
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            one=pool.submit(reserve,a,True)
            try:
                self.assertTrue(entered.wait(10))
                two=pool.submit(reserve,b,False)
                self.assertTrue(attempting.wait(10))
                with self.assertRaises(TimeoutError): two.result(timeout=.2)
            finally:
                release.set()
            self.assertEqual(one.result(timeout=10),"accepted")
            self.assertEqual(two.result(timeout=10),"rejected")
        self.assertEqual(CreditAllocation.objects.count(),1)
