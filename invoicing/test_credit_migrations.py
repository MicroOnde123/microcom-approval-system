"""E-B application/reversal and synthetic populated-ledger preflight."""
import io
import json
from time import perf_counter
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction, IntegrityError, DatabaseError
from django.db.migrations.executor import MigrationExecutor

from .models import CreditNote, CreditAllocation, CreditOperation, Invoice
from .test_credit_guards import CreditGuardFixtures

OLD = ("invoicing","0003_alter_invoice_options")
SCHEMA = ("invoicing","0004_credit_reservation_schema")
TARGET = ("invoicing","0005_credit_financial_guards")


class CreditMigrationTests(CreditGuardFixtures):
    def test_additive_migrations_preserve_legacy_null_tokens_zero_movements_and_invoice_guards(self):
        # Actual invoice service is existing; no credit lifecycle is invoked.
        self.setup_invoice(price="2")
        leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
        evidence={"synthetic_only":True,"timings":{},"locks":{},"preflight":"legacy ledger evaluated before new guards"}
        try:
            MigrationExecutor(connection).migrate([OLD])
            apps=MigrationExecutor(connection).loader.project_state([OLD]).apps
            apps.get_model("requests_app","StockMovement").objects.filter(pk=self.returned.pk).update(return_operation_token=None)
            old_credit=apps.get_model("invoicing","CreditNote").objects.create(invoice_id=self.invoice.pk,currency="USD",created_by_id=self.user.pk)
            apps.get_model("invoicing","CreditAllocation").objects.create(credit_note_id=old_credit.pk,
                issue_allocation_id=self.issue_allocation.pk,return_movement_id=self.returned.pk,
                quantity=1,unit_price_snapshot=2,line_total=2,description_snapshot="Historical synthetic credit")
            # Historic item/movement zeros remain unmodified; no financial attribution invented.
            legacy_request=apps.get_model("requests_app","Request").objects.create(request_number="SYNTHETIC-ZERO-EB",
                submitted_by_id=self.other.pk,department_id=self.department.pk,request_for_department_id=self.department.pk,
                request_type_id=self.request_type.pk,description="Synthetic legacy zero",status="APPROVED",stock_deducted=True)
            RequestItem=apps.get_model("requests_app","RequestMaterialItem")
            item=RequestItem.objects.create(request_id=legacy_request.pk,material_id=self.material.pk,quantity=0)
            movement=apps.get_model("requests_app","StockMovement").objects.create(material_id=self.material.pk,
                request_id=legacy_request.pk,movement_type="OUT",quantity=0,return_operation_token=None)
            before=self.source_snapshot()
            invoice_before=list(Invoice.objects.values())
            credit_before=apps.get_model("invoicing","CreditNote").objects.values().get(pk=old_credit.pk)
            with connection.cursor() as c:
                c.execute("SELECT pg_get_functiondef('inv_document_guard()'::regprocedure),pg_get_functiondef('inv_child_guard()'::regprocedure)")
                original_functions=c.fetchone()
            for target in (SCHEMA,TARGET):
                output=io.StringIO();call_command("sqlmigrate",*target,stdout=output)
                started=perf_counter()
                with transaction.atomic():
                    MigrationExecutor(connection).migrate([target])
                    with connection.cursor() as c:
                        c.execute("""SELECT DISTINCT cl.relname,l.mode FROM pg_locks l JOIN pg_class cl ON cl.oid=l.relation
                         WHERE l.pid=pg_backend_pid() AND cl.relname LIKE 'invoicing_%%' ORDER BY cl.relname,l.mode""")
                        evidence["locks"][target[1]]=c.fetchall()
                evidence["timings"][target[1]]=perf_counter()-started
                evidence[target[1]+"_sql"]=output.getvalue()
            self.assertEqual(self.source_snapshot(),before)
            self.assertEqual(list(Invoice.objects.values()),invoice_before)
            current=CreditNote.objects.values().get(pk=old_credit.pk)
            self.assertEqual({key:current[key] for key in credit_before},credit_before)
            self.assertIsNone(current["creation_operation_token"])
            self.assertEqual(CreditOperation.objects.count(),0)
            with connection.cursor() as c:
                c.execute("SELECT pg_get_functiondef('inv_document_guard()'::regprocedure),pg_get_functiondef('inv_child_guard()'::regprocedure)")
                self.assertEqual(c.fetchone(),original_functions)
                c.execute("SELECT quantity,return_operation_token FROM requests_app_stockmovement WHERE id=%s",[movement.pk])
                self.assertEqual(c.fetchone(),(0,None))
            # No E-B operation evidence: schema-only reversal and reapply are permitted.
            MigrationExecutor(connection).migrate([OLD])
            self.assertEqual(self.source_snapshot(),before)
            MigrationExecutor(connection).migrate([TARGET])
            evidence.update(legacy_values_preserved=True,invoice_functions_unchanged=True,
                no_backfill=True,empty_eb_evidence_reversal=True)
            if hasattr(settings,"STAGE2_EVIDENCE_ROOT"):
                (settings.STAGE2_EVIDENCE_ROOT/"checkpoint-eb-migration-results.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        finally:
            MigrationExecutor(connection).migrate(leaves)

    def test_incompatible_populated_legacy_rounding_aborts_migration_without_repair(self):
        self.setup_invoice()
        leaves=MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([SCHEMA])
            # Old guards independently round each one-unit allocation to .01.
            credit=CreditNote.objects.create(invoice=self.invoice,currency="USD",created_by=self.user)
            for _ in range(3):
                CreditAllocation.objects.create(credit_note=credit,issue_allocation=self.issue_allocation,
                    return_movement=self.returned,quantity=1,unit_price_snapshot=Decimal("0.0050"),
                    line_total=Decimal("0.01"),description_snapshot="Synthetic incompatible legacy reservation")
            before=list(CreditAllocation.objects.values())
            with self.assertRaises(IntegrityError):
                MigrationExecutor(connection).migrate([TARGET])
            self.assertEqual(list(CreditAllocation.objects.values()),before)
            with connection.cursor() as c:
                c.execute("SELECT count(*) FROM django_migrations WHERE app='invoicing' AND name=%s",[TARGET[1]])
                self.assertEqual(c.fetchone()[0],0)
            # Delete only these newly created, unnumbered synthetic fixtures under old guards.
            for row in CreditAllocation.objects.all(): row.delete()
            credit.delete()
        finally:
            MigrationExecutor(connection).migrate(leaves)

    def test_guard_reversal_is_refused_when_eb_evidence_exists(self):
        self.setup_invoice()
        with self.write("CREATE"):
            pass
        with self.assertRaises(DatabaseError):
            MigrationExecutor(connection).migrate([SCHEMA])
        self.assertEqual(CreditOperation.objects.count(),1)
        with connection.cursor() as c:
            c.execute("SELECT count(*) FROM pg_trigger WHERE tgname='eb_operation_frozen'")
            self.assertEqual(c.fetchone()[0],1)
