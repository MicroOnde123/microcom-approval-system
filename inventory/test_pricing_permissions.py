"""Synthetic ordinary PostgreSQL roles; no Supabase grants are assumed or changed."""
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from .models import MaterialPriceChange
from .pricing import price_state, update_price
from .test_pricing import PricingFixtures


class PricingDatabasePermissionTests(PricingFixtures, TestCase):
    def setUp(self):
        super().setUp()
        from config.catalogue_pricing_test_runner import verify_database
        verify_database(connection, test_only=True)

    def role(self):
        name = "synthetic_price_" + uuid4().hex[:20]
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE ROLE {connection.ops.quote_name(name)} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")
            cursor.execute(f"GRANT USAGE ON SCHEMA public TO {connection.ops.quote_name(name)}")
        # PostgreSQL role and grant DDL is rolled back with this TestCase.
        return name

    @contextmanager
    def acting_as(self, role):
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {connection.ops.quote_name(role)}")
        try:
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def denied(self, sql, *, code="42501"):
        with self.assertRaises(DatabaseError) as caught, transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(sql)
        self.assertEqual(caught.exception.__cause__.pgcode, code)

    def test_untrusted_role_has_no_ledger_read_or_write_access(self):
        role = self.role()
        with self.acting_as(role):
            for sql in ("SELECT * FROM inventory_materialpricechange",
                        "INSERT INTO inventory_materialpricechange DEFAULT VALUES",
                        "UPDATE inventory_materialpricechange SET reason='tampered'",
                        "DELETE FROM inventory_materialpricechange",
                        "TRUNCATE inventory_materialpricechange"):
                self.denied(sql)

    def test_granted_truncate_and_row_mutation_still_fail_without_changing_history(self):
        update_price(self.material.pk, self.user, price=Decimal("1"), currency="USD", reason="Synthetic original",
                     expected_state=price_state(self.material))
        role = self.role()
        with connection.cursor() as cursor:
            # Resolve TestCase's deferred FK events so PostgreSQL reaches the
            # TRUNCATE guard, rather than rejecting TRUNCATE for pending events.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute(f"GRANT SELECT, UPDATE, DELETE, TRUNCATE ON inventory_materialpricechange TO {connection.ops.quote_name(role)}")
        with self.acting_as(role):
            for sql in ("TRUNCATE inventory_materialpricechange",
                        "UPDATE inventory_materialpricechange SET reason='tampered'",
                        "DELETE FROM inventory_materialpricechange"):
                self.denied(sql, code="23514")
        self.assertEqual(MaterialPriceChange.objects.get().reason, "Synthetic original")

    def test_minimum_trusted_backend_grants_allow_audited_price_update(self):
        role = self.role()
        quoted = connection.ops.quote_name(role)
        with connection.cursor() as cursor:
            cursor.execute(f"GRANT SELECT ON inventory_material, inventory_materialcategory, inventory_materialpricechange, accounts_user, auth_permission, django_content_type, accounts_user_user_permissions, accounts_user_groups, auth_group_permissions TO {quoted}")
            cursor.execute(f"GRANT UPDATE(unit_price,currency) ON inventory_material TO {quoted}")
            cursor.execute(f"GRANT INSERT ON inventory_materialpricechange TO {quoted}")
            cursor.execute("SELECT pg_get_serial_sequence('inventory_materialpricechange','id')")
            sequence = cursor.fetchone()[0]
            cursor.execute(f"GRANT USAGE ON SEQUENCE {sequence} TO {quoted}")
        with self.acting_as(role):
            update_price(self.material.pk, self.user, price=Decimal("2.50"), currency="EUR", reason="Trusted backend",
                         expected_state=price_state(self.material))
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user, has_table_privilege(current_user,'inventory_materialpricechange','TRUNCATE'), has_table_privilege(current_user,'inventory_materialpricechange','UPDATE'), has_table_privilege(current_user,'inventory_materialpricechange','DELETE')")
                self.assertEqual(cursor.fetchone(), (role, False, False, False))
            self.denied("INSERT INTO inventory_materialpricechange(material_id,user_id,changed_at,reason,source) VALUES (1,1,now(),'forged','admin')", code="23514")
        record = MaterialPriceChange.objects.get()
        self.assertEqual((record.new_price, record.new_currency, record.user_id), (Decimal("2.50"), "EUR", self.user.pk))

    def test_inherited_read_grant_survives_revoke_from_member(self):
        parent, member = self.role(), self.role()
        with connection.cursor() as cursor:
            cursor.execute(f"GRANT SELECT ON inventory_materialpricechange TO {connection.ops.quote_name(parent)}")
            cursor.execute(f"GRANT {connection.ops.quote_name(parent)} TO {connection.ops.quote_name(member)}")
            cursor.execute(f"REVOKE SELECT ON inventory_materialpricechange FROM {connection.ops.quote_name(member)}")
            cursor.execute("SELECT has_table_privilege(%s,'inventory_materialpricechange','SELECT')", [member])
            self.assertTrue(cursor.fetchone()[0])
        # Deployment inspection must examine effective rights, not only direct ACLs.
