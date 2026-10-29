import io
import json
from time import perf_counter

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class StockClassificationMigrationTests(TransactionTestCase):
    def test_legacy_requests_approvals_and_movements_are_not_reclassified(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        others = [node for node in leaves if node[0] not in {"requests_app", "workflows", "invoicing"}]
        old = others + [("requests_app", "0016_protect_stock_movement_references"),
                        ("workflows", "0002_approvalworkflowstep_alternate_approver_user")]
        evidence = {"synthetic_only": True, "sql": {}, "timings_seconds": {}, "locks": {}}
        try:
            executor.migrate(old + [("invoicing", None)])
            apps = executor.loader.project_state(old).apps
            department = apps.get_model("accounts", "Department").objects.create(name="Synthetic", code="CLS")
            user = apps.get_model("accounts", "User").objects.create(username="synthetic-classification")
            kind = apps.get_model("requests_app", "RequestType").objects.create(name="Synthetic Material", code="CLS", requires_materials=True)
            workflow = apps.get_model("workflows", "ApprovalWorkflow").objects.create(name="Synthetic", request_type=kind)
            step = apps.get_model("workflows", "ApprovalWorkflowStep").objects.create(workflow=workflow, step_order=1, approver_user=user)
            category = apps.get_model("inventory", "MaterialCategory").objects.create(name="Synthetic", code="CLS")
            for index, (status, quantity, returned) in enumerate((("IN_REVIEW", 2, []), ("APPROVED", 0, []), ("APPROVED", 10, [3]), ("APPROVED", 10, [4, 6]))):
                material = apps.get_model("inventory", "Material").objects.create(name="Synthetic", code=f"CLS-{index}", category=category, stock_quantity=100)
                req = apps.get_model("requests_app", "Request").objects.create(request_number=f"SYNTHETIC-CLS-{index}",
                    request_type=kind, submitted_by=user, department=department, request_for_department=department,
                    description="Synthetic historical classification fixture", status=status,
                    stock_deducted=status == "APPROVED", current_step_order=1 if status == "IN_REVIEW" else None)
                apps.get_model("requests_app", "RequestMaterialItem").objects.create(request=req, material=material, quantity=quantity)
                apps.get_model("requests_app", "RequestApproval").objects.create(request=req, workflow_step=step,
                    approver_user=user, step_order=1, status="PENDING" if status == "IN_REVIEW" else "APPROVED")
                if status == "APPROVED":
                    for movement_type, value in [("OUT", quantity)] + [("RETURN", value) for value in returned]:
                        apps.get_model("requests_app", "StockMovement").objects.create(request=req, material=material,
                            movement_type=movement_type, quantity=value, return_operation_token=None)

            tracked = [("requests_app", name) for name in ("Request", "RequestApproval", "RequestMaterialItem", "StockMovement", "RequestAuditLog")]
            tracked += [("inventory", "Material"), ("workflows", "ApprovalWorkflowStep")]
            new_fields = {"classification", "succursale_id", "classified_by_id", "classified_at", "requires_stock_classification", "is_stock_review"}

            def snapshot(state):
                result = {}
                for app, name in tracked:
                    result[name] = [{key: value for key, value in row.items() if key not in new_fields}
                                    for row in state.get_model(app, name).objects.order_by("pk").values()]
                return result

            before = snapshot(apps)
            legacy_columns = {name: set(rows[0]) for name, rows in before.items() if rows}
            targets = list(old)
            for app in ("workflows", "requests_app"):
                node = next(node for node in leaves if node[0] == app)
                output = io.StringIO()
                call_command("sqlmigrate", app, node[1], stdout=output)
                evidence["sql"][app] = output.getvalue()
                targets = [target for target in targets if target[0] != app] + [node]
                started = perf_counter()
                with transaction.atomic():
                    MigrationExecutor(connection).migrate(targets)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT DISTINCT c.relname, l.mode FROM pg_locks l JOIN pg_class c ON c.oid=l.relation WHERE l.pid=pg_backend_pid() AND c.relname IN ('requests_app_request','requests_app_requestapproval','workflows_approvalworkflowstep') ORDER BY c.relname, l.mode")
                        evidence["locks"][app] = cursor.fetchall()
                evidence["timings_seconds"][app] = round(perf_counter() - started, 6)
                apps = MigrationExecutor(connection).loader.project_state(targets).apps
                after = snapshot(apps)
                # Compare every original column, not fields introduced by later
                # approved migrations. Verify their legacy defaults separately.
                self.assertEqual({name: [{key: row[key] for key in legacy_columns[name]} for row in rows]
                                  for name, rows in after.items()}, before)
                request_model = apps.get_model("requests_app", "Request")
                allocation_fields = {field.name for field in request_model._meta.fields} & {
                    "reference_namespace_snapshot", "reference_year", "reference_counter", "reference_allocated_at"}
                if allocation_fields:
                    for row in request_model.objects.values(*sorted(allocation_fields)):
                        self.assertTrue(all(value is None for value in row.values()))
            self.assertEqual(apps.get_model("requests_app", "Request").objects.filter(classification=None, succursale=None, classified_by=None, classified_at=None).count(), 4)
            self.assertFalse(apps.get_model("requests_app", "RequestApproval").objects.filter(requires_stock_classification=True).exists())
            self.assertFalse(apps.get_model("workflows", "ApprovalWorkflowStep").objects.filter(is_stock_review=True).exists())
            evidence.update(preserved_existing_columns=True, unclassified_legacy_requests=4, untouched_legacy_approvals=4,
                            zero_items=1, out_movements=3, return_movements=3, null_retry_tokens=6)
            if hasattr(settings, "STAGE2_EVIDENCE_ROOT"):
                (settings.STAGE2_EVIDENCE_ROOT / "stage2-migration-results.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        finally:
            MigrationExecutor(connection).migrate(leaves)
