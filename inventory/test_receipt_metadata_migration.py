"""Exercise the additive receipt migration on synthetic historical rows only."""
from uuid import uuid4
from unittest import skipUnless
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


@skipUnless(connection.vendor == "postgresql", "PostgreSQL schema upgrade regression")
class ReceiptMetadataMigrationTests(TransactionTestCase):
    def test_existing_receipt_data_is_preserved_and_metadata_remains_unknown(self):
        executor = MigrationExecutor(connection)
        leaves = executor.loader.graph.leaf_nodes()
        old = ("inventory", "0005_materialreceipt_materialreceiptline")
        try:
            executor.migrate([old])
            apps = executor.loader.project_state([old]).apps
            User = apps.get_model("accounts", "User")
            Category = apps.get_model("inventory", "MaterialCategory")
            Material = apps.get_model("inventory", "Material")
            Receipt = apps.get_model("inventory", "MaterialReceipt")
            Line = apps.get_model("inventory", "MaterialReceiptLine")
            Movement = apps.get_model("requests_app", "StockMovement")
            user = User.objects.create(username="legacy-migration")
            category = Category.objects.create(name="Legacy", code="LEGACY-MIG")
            material = Material.objects.create(name="Legacy material", code="LEGACY-MIG", category=category, stock_quantity=15, unit="m")
            movement = Movement.objects.create(material=material, quantity=5, movement_type="IN", performed_by=user)
            receipt = Receipt.objects.create(operation_token=uuid4(), reference="IN-MIGRATION-LEGACY", payload_hash="a" * 64,
                received_on="2026-10-31", supplier="Original supplier", delivery_reference="Original delivery", notes="Historical notes", created_by=user)
            Line.objects.create(receipt=receipt, material=material, quantity=5, stock_after=15, movement=movement)
            before_receipt = Receipt.objects.values().get(pk=receipt.pk)
            before_line = Line.objects.values().get(receipt=receipt)
            before_material = Material.objects.values().get(pk=material.pk)
            before_movement = Movement.objects.values().get(pk=movement.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(leaves)
            apps = executor.loader.project_state(leaves).apps
            after_receipt = apps.get_model("inventory", "MaterialReceipt").objects.values().get(pk=receipt.pk)
            after_line = apps.get_model("inventory", "MaterialReceiptLine").objects.values().get(receipt_id=receipt.pk)
            self.assertIsNone(after_receipt.pop("transaction_type"))
            self.assertIsNone(after_line.pop("material_snapshot"))
            self.assertEqual(after_receipt, before_receipt)
            self.assertEqual(after_line, before_line)
            self.assertEqual(apps.get_model("inventory", "Material").objects.values().get(pk=material.pk), before_material)
            self.assertEqual(apps.get_model("requests_app", "StockMovement").objects.values().get(pk=movement.pk), before_movement)
        finally:
            MigrationExecutor(connection).migrate(leaves)
