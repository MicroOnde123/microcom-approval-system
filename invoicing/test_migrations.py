"""Additive migration/reversal rehearsal; exclusively synthetic legacy fixtures."""
import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class InvoiceMigrationTests(TransactionTestCase):
    def test_additive_schema_preserves_legacy_data_and_guards_reverse(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        others = [node for node in leaves if node[0] not in {"core", "invoicing"}]
        old = others + [("core", "0001_initial")]
        evidence = {"synthetic_only": True, "timings_seconds": {}, "sql": {}, "locks": {}}
        tables = [("requests_app", "Request"), ("requests_app", "RequestMaterialItem"),
                  ("requests_app", "StockMovement"), ("inventory", "Material")]

        def snapshot(apps):
            return {name: list(apps.get_model(app, name).objects.order_by("pk").values()) for app, name in tables}

        try:
            executor.migrate(old + [("invoicing", None)])
            apps = executor.loader.project_state(old).apps
            user = apps.get_model("accounts", "User").objects.create(username="synthetic-invoice-migration")
            department = apps.get_model("accounts", "Department").objects.create(name="Synthetic", code="INV")
            kind = apps.get_model("requests_app", "RequestType").objects.create(name="Synthetic", code="INV", requires_materials=True)
            category = apps.get_model("inventory", "MaterialCategory").objects.create(name="Synthetic", code="INV")
            for index, (quantity, returns) in enumerate(((0, []), (10, [3]), (10, [4,6]))):
                material = apps.get_model("inventory", "Material").objects.create(code=f"INV{index}", name="Synthetic",
                    category=category, stock_quantity=100)
                req = apps.get_model("requests_app", "Request").objects.create(request_number=f"SYNTHETIC-INVOICE-{index}",
                    submitted_by=user, department=department, request_for_department=department, request_type=kind,
                    description="Synthetic legacy fixture", status="APPROVED", stock_deducted=True)
                apps.get_model("requests_app", "RequestMaterialItem").objects.create(request=req, material=material, quantity=quantity)
                for movement_type, amount in [("OUT",quantity)]+[("RETURN",value) for value in returns]:
                    apps.get_model("requests_app", "StockMovement").objects.create(request=req, material=material,
                        movement_type=movement_type, quantity=amount, return_operation_token=None)
            company = apps.get_model("core", "CompanyDocumentSettings").objects.create(company_name="Synthetic unverified company")
            before = snapshot(apps)
            company_before = apps.get_model("core", "CompanyDocumentSettings").objects.values().get(pk=company.pk)
            targets = list(old)
            for node in [("core", "0002_companydocumentsettings_business_timezone"),
                         ("invoicing", "0001_initial"), ("invoicing", "0002_financial_guards")]:
                output = io.StringIO()
                call_command("sqlmigrate", *node, stdout=output)
                key = ".".join(node)
                evidence["sql"][key] = output.getvalue()
                targets = [target for target in targets if target[0]!=node[0]]+[node]
                started = perf_counter()
                with transaction.atomic():
                    MigrationExecutor(connection).migrate(targets)
                    with connection.cursor() as cursor:
                        cursor.execute("""SELECT DISTINCT c.relname,l.mode FROM pg_locks l JOIN pg_class c ON c.oid=l.relation
                            WHERE l.pid=pg_backend_pid() AND (c.relname LIKE 'invoicing_%%' OR c.relname IN
                            ('core_companydocumentsettings','requests_app_request','requests_app_stockmovement','inventory_material'))
                            ORDER BY c.relname,l.mode""")
                        evidence["locks"][key] = cursor.fetchall()
                evidence["timings_seconds"][key] = round(perf_counter()-started,6)
                apps = MigrationExecutor(connection).loader.project_state(targets).apps
                self.assertEqual(snapshot(apps), before)
            current = apps.get_model("core", "CompanyDocumentSettings").objects.values().get(pk=company.pk)
            self.assertEqual(current.pop("business_timezone"), "Africa/Kinshasa")
            self.assertEqual(current, company_before)
            self.assertEqual(apps.get_model("invoicing", "Invoice").objects.count(), 0)
            self.assertEqual(apps.get_model("invoicing", "CompanyVerification").objects.count(), 0)
            # Reversible DDL only. No promise that reversing populated financial
            # schema is a safe business rollback.
            MigrationExecutor(connection).migrate(others+[("core","0002_companydocumentsettings_business_timezone"),("invoicing","0001_initial")])
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'inv_%%' AND NOT tgisinternal")
                self.assertEqual(cursor.fetchone()[0],0)
            MigrationExecutor(connection).migrate(old + [("invoicing", None)])
            self.assertEqual(snapshot(MigrationExecutor(connection).loader.project_state(old).apps), before)
            evidence.update(all_legacy_values_preserved=True, null_retry_tokens=6, zero_outs=1,
                partial_return_histories=1, full_return_histories=1, no_financial_backfill=True, empty_schema_reversal=True)
            if hasattr(settings,"STAGE2_EVIDENCE_ROOT"):
                (settings.STAGE2_EVIDENCE_ROOT/"checkpoint-b-migration-results.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        finally:
            MigrationExecutor(connection).migrate(leaves)
