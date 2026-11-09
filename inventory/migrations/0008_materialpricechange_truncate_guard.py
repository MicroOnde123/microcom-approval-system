"""Defence in depth; ownership and role privileges still need deployment review.

Separate from 0007 so existing installations receive the guard as well. No data
is rewritten and no role names, ownership or environment grants are assumed.
"""
from django.db import migrations


SQL = """
CREATE FUNCTION inventory_price_audit_no_truncate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Price history cannot be truncated' USING ERRCODE='23514';
END $$;
CREATE TRIGGER inventory_price_audit_no_truncate
 BEFORE TRUNCATE ON inventory_materialpricechange
 FOR EACH STATEMENT EXECUTE FUNCTION inventory_price_audit_no_truncate();
"""

REVERSE_SQL = """
DROP TRIGGER inventory_price_audit_no_truncate ON inventory_materialpricechange;
DROP FUNCTION inventory_price_audit_no_truncate();
"""


class Migration(migrations.Migration):
    dependencies = [("inventory", "0007_materialpricechange")]
    operations = [migrations.RunSQL(SQL, REVERSE_SQL)]
