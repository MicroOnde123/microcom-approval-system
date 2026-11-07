"""Allow the existing stock role to use the audited catalogue service only."""
from importlib import import_module
from django.db import migrations

original = import_module("inventory.migrations.0007_materialpricechange").SQL
# Replace only the existing function; keep all ledger/stock guards and records.
function = original[original.index("CREATE FUNCTION inventory_record_price_change()"):
                    original.index("CREATE TRIGGER inventory_material_price_change")]
function = function.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
forward = function.replace("(u.is_superuser OR EXISTS (",
    "(u.is_superuser OR (u.can_manage_stock AND context->>'source'='service') OR EXISTS (")


class Migration(migrations.Migration):
    dependencies = [("inventory", "0010_materialentrydraft_cancelled")]
    operations = [migrations.RunSQL(forward, function)]
