"""Additive migration rehearsal over synthetic pre-Stage-1 data."""
import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Stage1MigrationTests(TransactionTestCase):
    def test_existing_records_survive_additive_migrations_without_price_backfill(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        others = [node for node in leaves if node[0] not in {"core", "inventory", "requests_app", "invoicing"}]
        others += [("requests_app", "0016_protect_stock_movement_references")]
        old = others + [("inventory", "0002_material_minimum_stock_level_material_stock_quantity")]
        evidence = {"synthetic_only": True, "timings_seconds": {}, "sql": {}, "locks": {}}
        models_to_check = [("inventory", "Material"), ("accounts", "Department"),
                           ("requests_app", "Request"), ("requests_app", "RequestMaterialItem"),
                           ("requests_app", "StockMovement"), ("requests_app", "RequestApproval")]

        def snapshot(apps):
            values = {}
            for app, name in models_to_check:
                rows = list(apps.get_model(app, name).objects.order_by("pk").values())
                if name == "Material":
                    for row in rows:
                        row.pop("unit_price", None)
                        row.pop("currency", None)
                values[name] = rows
            return values

        try:
            executor.migrate(old + [("core", None), ("invoicing", None)])
            apps = executor.loader.project_state(old).apps
            department = apps.get_model("accounts", "Department").objects.create(name="Synthetic", code="STG1")
            user = apps.get_model("accounts", "User").objects.create(username="stage1-migration")
            kind = apps.get_model("requests_app", "RequestType").objects.create(name="Synthetic Material", code="STG1", requires_materials=True)
            workflow = apps.get_model("workflows", "ApprovalWorkflow").objects.create(name="Synthetic", request_type=kind)
            step = apps.get_model("workflows", "ApprovalWorkflowStep").objects.create(workflow=workflow, step_order=1, approver_user=user)
            category = apps.get_model("inventory", "MaterialCategory").objects.create(name="Synthetic", code="STG1")
            for index, (quantity, returned, balance) in enumerate(((0, [], 50), (10, [3], 93), (10, [4, 6], 100))):
                material = apps.get_model("inventory", "Material").objects.create(category=category, code=f"STG1-{index}", name="Synthetic", stock_quantity=balance)
                req = apps.get_model("requests_app", "Request").objects.create(request_number=f"SYNTHETIC-STAGE1-{index}",
                    request_type=kind, submitted_by=user, department=department, request_for_department=department,
                    description="Synthetic historical fixture", status="APPROVED", stock_deducted=True)
                apps.get_model("requests_app", "RequestMaterialItem").objects.create(request=req, material=material, quantity=quantity)
                apps.get_model("requests_app", "RequestApproval").objects.create(request=req, workflow_step=step,
                    step_order=1, approver_user=user, acted_by=user, status="APPROVED")
                for movement_type, value in [("OUT", quantity)] + [("RETURN", value) for value in returned]:
                    apps.get_model("requests_app", "StockMovement").objects.create(request=req, material=material,
                        movement_type=movement_type, quantity=value, return_operation_token=None)
            before = snapshot(apps)
            target = list(old)
            for app in ("core", "inventory"):
                node = next(node for node in leaves if node[0] == app)
                output = io.StringIO()
                call_command("sqlmigrate", app, node[1], stdout=output)
                evidence["sql"][app] = output.getvalue()
                target = [item for item in target if item[0] != app] + [node]
                started = perf_counter()
                with transaction.atomic():
                    MigrationExecutor(connection).migrate(target)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT DISTINCT c.relname, l.mode FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE l.pid=pg_backend_pid() AND c.relname IN ('inventory_material', 'requests_app_request', 'requests_app_stockmovement') ORDER BY c.relname, l.mode")
                        evidence["locks"][app] = cursor.fetchall()
                evidence["timings_seconds"][app] = round(perf_counter() - started, 6)
                apps = MigrationExecutor(connection).loader.project_state(target).apps
                self.assertEqual(snapshot(apps), before)
            material_model = apps.get_model("inventory", "Material")
            self.assertEqual(material_model.objects.filter(unit_price=None, currency=None).count(), 3)
            self.assertEqual(apps.get_model("inventory", "Succursale").objects.count(), 0)
            self.assertEqual(apps.get_model("core", "CompanyDocumentSettings").objects.count(), 0)
            evidence.update(preserved_all_existing_values=True, unpriced_materials=3, zero_items=1,
                            out_movements=3, return_movements=3, null_retry_tokens=6, approvals=3,
                            no_succursale_or_company_backfill=True)
            if hasattr(settings, "STAGE1_EVIDENCE_ROOT"):
                (settings.STAGE1_EVIDENCE_ROOT / "stage1-migration-results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        finally:
            MigrationExecutor(connection).migrate(leaves)
