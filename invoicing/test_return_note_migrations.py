"""Additive migration preservation, lock evidence and reversal boundaries."""
import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction, DatabaseError
from django.db.migrations.executor import MigrationExecutor

from .models import MaterialReturnNoteAudit, MaterialReturnNote, CreditAllocation, CreditNote, Invoice
from .test_return_note_guards import ReturnNoteFixtures

OLD=('invoicing','0005_credit_financial_guards')
SCHEMA=('invoicing','0006_material_return_note_schema')
TARGET=('invoicing','0007_material_return_note_guards')


class ReturnNoteMigrationTests(ReturnNoteFixtures):
    def test_additive_preservation_sql_locks_and_empty_reversal(self):
        self.setup_invoice(price='2');credit=self.new_credit();self.reserve(credit,amount='2')
        leaves=MigrationExecutor(connection).loader.graph.leaf_nodes()
        evidence={'timings':{},'locks':{},'sql':{}}
        try:
            MigrationExecutor(connection).migrate([OLD])
            legacy_request,legacy_item=self.make_request(1)
            # Reproduce legacy data only in this disposable synthetic database.
            from requests_app.models import StockMovement, RequestMaterialItem
            with connection.cursor() as c:
                c.execute('UPDATE requests_app_requestmaterialitem SET quantity=0 WHERE id=%s',[legacy_item.pk])
            legacy_movement=StockMovement.objects.create(request=legacy_request,material=self.material,
                quantity=0,movement_type='OUT',performed_by=self.user)
            source=self.source_snapshot();invoices=list(Invoice.objects.values())
            credits=list(CreditNote.objects.values());allocations=list(CreditAllocation.objects.values())
            with connection.cursor() as c:
                c.execute("SELECT pg_get_functiondef('inv_eb_allocation_guard()'::regprocedure),pg_get_functiondef('inv_eb_operation_insert()'::regprocedure),pg_get_functiondef('inv_document_guard()'::regprocedure)")
                original=c.fetchone()
            for target in (SCHEMA,TARGET):
                output=io.StringIO();call_command('sqlmigrate',*target,stdout=output)
                started=perf_counter()
                with transaction.atomic():
                    MigrationExecutor(connection).migrate([target])
                    with connection.cursor() as c:
                        c.execute("SELECT DISTINCT cl.relname,l.mode FROM pg_locks l JOIN pg_class cl ON cl.oid=l.relation WHERE l.pid=pg_backend_pid() AND cl.relname LIKE 'invoicing_%%' ORDER BY 1,2")
                        evidence['locks'][target[1]]=c.fetchall()
                evidence['timings'][target[1]]=perf_counter()-started
                evidence['sql'][target[1]]=output.getvalue()
            self.assertEqual(source,self.source_snapshot());self.assertEqual(invoices,list(Invoice.objects.values()))
            self.assertEqual(credits,list(CreditNote.objects.values()));self.assertEqual(allocations,list(CreditAllocation.objects.values()))
            self.assertEqual(RequestMaterialItem.objects.get(pk=legacy_item.pk).quantity,0)
            legacy_movement.refresh_from_db()
            self.assertEqual(legacy_movement.quantity,0);self.assertIsNone(legacy_movement.return_operation_token)
            with connection.cursor() as c:
                c.execute("SELECT pg_get_functiondef('inv_eb_allocation_guard()'::regprocedure),pg_get_functiondef('inv_eb_operation_insert()'::regprocedure),pg_get_functiondef('inv_document_guard()'::regprocedure)")
                self.assertEqual(c.fetchone(),original)
            MigrationExecutor(connection).migrate([OLD]);MigrationExecutor(connection).migrate([TARGET])
            evidence.update(source_preserved=True,credit_guards_unchanged=True,empty_reversal=True,legacy_zeros_and_null_tokens_preserved=True)
            if hasattr(settings,'STAGE2_EVIDENCE_ROOT'):
                (settings.STAGE2_EVIDENCE_ROOT/'checkpoint-er1-migration-results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        finally:MigrationExecutor(connection).migrate(leaves)

    def test_reversal_refuses_append_only_return_note_audit(self):
        self.setup_invoice()
        op=MaterialReturnNoteAudit.objects.create(invoice=self.invoice,actor=self.user,reason='Retained audit')
        with self.assertRaises(DatabaseError):MigrationExecutor(connection).migrate([SCHEMA])
        self.assertTrue(MaterialReturnNoteAudit.objects.filter(pk=op.pk).exists())

    def test_existing_cross_ledger_conflict_aborts_guard_migration_without_repair(self):
        self.setup_invoice();credit=self.new_credit();self.reserve(credit)
        leaves=MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            MigrationExecutor(connection).migrate([SCHEMA])
            # The additive schema before guard installation has no return-note
            # workflow. Insert a synthetic conflicting construction explicitly.
            with transaction.atomic():self.note_rows()
            before=list(MaterialReturnNote.objects.values());credit_before=list(CreditAllocation.objects.values())
            with self.assertRaises(DatabaseError):MigrationExecutor(connection).migrate([TARGET])
            self.assertEqual(list(MaterialReturnNote.objects.values()),before)
            self.assertEqual(list(CreditAllocation.objects.values()),credit_before)
        finally:
            # Test-only cleanup of intentionally unguarded synthetic fixtures,
            # allowing the normal schema to be restored for other regressions.
            with connection.cursor() as c:
                c.execute('TRUNCATE invoicing_materialreturnnoteartifact,invoicing_materialreturnnoteline,invoicing_materialreturnnote,invoicing_materialreturnnoteaudit')
            # Sequence config alone is retained; no destructive reversal here.
            MigrationExecutor(connection).migrate(leaves)
