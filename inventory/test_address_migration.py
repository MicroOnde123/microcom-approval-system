"""Isolated PostgreSQL only: additive address migration preserves legacy rows."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AddressMigrationTests(TransactionTestCase):
    def test_legacy_branch_and_material_values_are_preserved(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("inventory", "0003_succursale_material_currency_material_unit_price_and_more")])
            apps = executor.loader.project_state([
                ("inventory", "0003_succursale_material_currency_material_unit_price_and_more")]).apps
            Branch = apps.get_model("inventory", "Succursale")
            Material = apps.get_model("inventory", "Material")
            category = apps.get_model("inventory", "MaterialCategory").objects.create(code="ADDRESS-SYNTH", name="Synthetic")
            Material.objects.create(code="ADDRESS-SYNTH", name="Synthetic stock", category=category,
                stock_quantity="123.45", minimum_stock_level="2.00", unit_price="1.25", currency="USD")
            branch = Branch.objects.create(code="LEGACY-ADDRESS", name="Legacy branch")
            before = list(Branch.objects.order_by("pk").values())
            materials = list(Material.objects.order_by("pk").values())
            executor = MigrationExecutor(connection)
            executor.migrate([("inventory", "0004_succursale_physical_address")])
            apps = executor.loader.project_state([("inventory", "0004_succursale_physical_address")]).apps
            rows = list(apps.get_model("inventory", "Succursale").objects.order_by("pk").values())
            self.assertEqual([{k: v for k, v in row.items() if k != "physical_address"} for row in rows], before)
            self.assertEqual(next(row for row in rows if row["id"] == branch.pk)["physical_address"], "")
            self.assertEqual(list(apps.get_model("inventory", "Material").objects.order_by("pk").values()), materials)
        finally:
            MigrationExecutor(connection).migrate(leaves)
