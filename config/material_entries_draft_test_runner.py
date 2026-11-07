"""Verified local-only draft tests; never import normal/deployment settings.

Use with config.test_material_entries_settings and --keepdb. Each run creates a
fresh synthetic database, leaving microcom_material_test and older test DBs alone.
"""
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from django.db import connection
from django.db.backends.postgresql.operations import DatabaseOperations
from django.test.runner import DiscoverRunner


def verify_local_database(conn, *, test_only=False):
    expected = conn.settings_dict["TEST"]["NAME"]
    if not expected.startswith("test_microcom_material_entries_"):
        raise RuntimeError("Unexpected draft test database name.")
    with conn.cursor() as cursor:
        cursor.execute("SELECT current_database(), host(inet_server_addr()), inet_server_port(), current_setting('data_directory')")
        name, host, port, directory = cursor.fetchone()
    allowed = {expected} if test_only else {"microcom_material_test", expected}
    local = Path("C:/Program Files/PostgreSQL/18/data").resolve()
    if name not in allowed or host != "127.0.0.1" or port != 5432 or Path(directory).resolve() != local:
        raise RuntimeError("Refusing an unverified draft test database.")
    if int((local / "postmaster.pid").read_text().splitlines()[3]) != 5432:
        raise RuntimeError("Local PostgreSQL PID-file port does not match.")


class MaterialEntriesDraftRunner(DiscoverRunner):
    def setup_databases(self, **kwargs):
        if not self.keepdb:
            raise RuntimeError("Use --keepdb: this runner never drops test databases.")
        connection.settings_dict["TEST"]["NAME"] = "test_microcom_material_entries_" + uuid4().hex[:12]
        verify_local_database(connection)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname=%s", [connection.settings_dict["TEST"]["NAME"]])
            if cursor.fetchone():
                raise RuntimeError("Refusing to reuse an existing database.")
        return super().setup_databases(**kwargs)

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        original = DatabaseOperations.sql_flush

        def flush_synthetic_tables(ops, style, tables, **options):
            statements = original(ops, style, tables, **options)
            if "inventory_materialpricechange" not in tables:
                return statements
            verify_local_database(ops.connection, test_only=True)
            return ["ALTER TABLE inventory_materialpricechange DISABLE TRIGGER inventory_price_audit_no_truncate;",
                    *statements, "ALTER TABLE inventory_materialpricechange ENABLE TRIGGER inventory_price_audit_no_truncate;"]

        self.flush_patch = patch.object(DatabaseOperations, "sql_flush", flush_synthetic_tables)
        self.flush_patch.start()

    def teardown_test_environment(self, **kwargs):
        try:
            self.flush_patch.stop()
        finally:
            super().teardown_test_environment(**kwargs)
