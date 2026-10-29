"""The Checkpoint C migration adds permission metadata, never financial values."""
import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from .models import Invoice, InvoiceLine, InvoiceIssueAllocation, InvoiceReturnExclusion, InvoiceAuditEvent
from .test_lifecycle import LifecycleFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvoicePermissionMigrationTests(LifecycleFixtures,TransactionTestCase):
    def test_permission_metadata_migration_preserves_financial_and_source_records(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        target = ("invoicing","0003_alter_invoice_options")
        old = ("invoicing","0002_financial_guards")
        try:
            executor.migrate([old])
            invoice = self.create()
            before = self.source_snapshot()
            financial_models = (Invoice,InvoiceLine,InvoiceIssueAllocation,InvoiceReturnExclusion,InvoiceAuditEvent)
            financial_before = {model.__name__:list(model.objects.order_by("pk").values()) for model in financial_models}
            grants = list(self.user.user_permissions.values_list("pk",flat=True).order_by("pk"))
            output = io.StringIO()
            call_command("sqlmigrate",*target,stdout=output)
            self.assertNotIn("ALTER TABLE",output.getvalue())
            started = perf_counter()
            MigrationExecutor(connection).migrate([target])
            elapsed = perf_counter()-started
            self.assertEqual(self.source_snapshot(),before)
            self.assertEqual({model.__name__:list(model.objects.order_by("pk").values()) for model in financial_models},financial_before)
            self.assertEqual(list(self.user.user_permissions.values_list("pk",flat=True).order_by("pk")),grants)
            state = MigrationExecutor(connection).loader.project_state([target])
            self.assertIn(("finalize_invoice","Can finalize invoices"),state.apps.get_model("invoicing","Invoice")._meta.permissions)
            MigrationExecutor(connection).migrate([old])
            self.assertEqual(self.source_snapshot(),before)
            self.assertTrue(Invoice.objects.filter(pk=invoice.pk,status="DRAFT",number=None).exists())
            if hasattr(settings,"STAGE2_EVIDENCE_ROOT"):
                (settings.STAGE2_EVIDENCE_ROOT/"checkpoint-c-migration-results.json").write_text(json.dumps({
                    "migration":"invoicing.0003_alter_invoice_options","seconds":elapsed,"sql":output.getvalue(),
                    "synthetic_only":True,"financial_and_source_rows_preserved":True,
                    "no_automatic_permission_grants":True,"metadata_reversal_passed":True},indent=2),encoding="utf-8")
        finally:
            MigrationExecutor(connection).migrate(leaves)
