"""Disposable PostgreSQL only: keep the production TRUNCATE guard intact in tests.

Django TransactionTestCase teardown deliberately truncates all synthetic tables.
Only its generated flush SQL may temporarily disable the named guard, using the
test database owner. Explicit TRUNCATE statements in security tests are untouched.
"""
from pathlib import Path
from unittest.mock import patch

from django.db import connection
from django.db.backends.postgresql.operations import DatabaseOperations
from django.test.runner import DiscoverRunner


def verify_database(connection, *, test_only=False):
    expected = connection.settings_dict["TEST"]["NAME"]
    if not expected.startswith("test_microcom_catalogue_pricing_"):
        raise RuntimeError("Unexpected pricing test database name.")
    allowed = {expected} if test_only else {"postgres", expected}
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), host(inet_server_addr()), inet_server_port(), current_setting('data_directory')")
        name, host, port, directory = cursor.fetchone()
    if (name not in allowed or host != "127.0.0.1" or port != 55439
            or Path(directory).resolve() != Path.home().joinpath("AppData/Local/Temp/microcom_material_entries_pg").resolve()):
        raise RuntimeError("Refusing to use an unverified PostgreSQL cluster.")


class CataloguePricingRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        verify_database(connection)
        return super().setup_databases(**kwargs)

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        original = DatabaseOperations.sql_flush

        def synthetic_flush(ops, style, tables, **options):
            statements = original(ops, style, tables, **options)
            if "inventory_materialpricechange" not in tables:
                return statements
            verify_database(ops.connection, test_only=True)
            return ["ALTER TABLE inventory_materialpricechange DISABLE TRIGGER inventory_price_audit_no_truncate;",
                    *statements,
                    "ALTER TABLE inventory_materialpricechange ENABLE TRIGGER inventory_price_audit_no_truncate;"]

        self.flush_patch = patch.object(DatabaseOperations, "sql_flush", synthetic_flush)
        self.flush_patch.start()

    def teardown_test_environment(self, **kwargs):
        try:
            self.flush_patch.stop()
        finally:
            super().teardown_test_environment(**kwargs)
