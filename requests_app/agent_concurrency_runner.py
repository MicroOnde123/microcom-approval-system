"""One transaction test per disposable database; never flush append-only tables.

Use --testrunner=requests_app.agent_concurrency_runner.FreshDatabaseRunner
with exactly one test method and config.test_agents_settings. Full migrations
and all triggers remain enabled. Django destroys the disposable database after
that single case, so no data cleanup or audit-trigger bypass is necessary.
"""
from types import MethodType
from django.conf import settings
from django.db import connections
from django.test import TransactionTestCase
from django.test.runner import DiscoverRunner, iter_test_cases


class FreshDatabaseRunner(DiscoverRunner):
    def build_suite(self, *args, **kwargs):
        if settings.SETTINGS_MODULE != "config.test_agents_settings" or settings.MIGRATION_MODULES:
            raise RuntimeError("Full-migration isolated agent settings required.")
        if self.keepdb:
            raise RuntimeError("A fresh database is required for each concurrency case.")
        suite = super().build_suite(*args, **kwargs)
        tests = list(iter_test_cases(suite))
        if len(tests) != 1 or not isinstance(tests[0], TransactionTestCase):
            raise RuntimeError("Run exactly one transaction test per disposable database.")

        def no_flush(test):
            # No trigger or table is altered. The entire test database is
            # disposed by DiscoverRunner.teardown_databases after this case.
            for conn in connections.all():
                conn.close()

        tests[0]._fixture_teardown = MethodType(no_flush, tests[0])
        return suite

    def setup_databases(self, **kwargs):
        result = super().setup_databases(**kwargs)
        connection = connections["default"]
        if not connection.settings_dict["NAME"].startswith("test_microcom_agents"):
            raise RuntimeError("Unexpected disposable test database name.")
        with connection.cursor() as cursor:
            cursor.execute("SELECT tgname, tgenabled FROM pg_trigger WHERE tgname IN (%s, %s)",
                           ["inventory_price_audit_no_truncate", "inventory_price_audit_immutable"])
            guards = dict(cursor.fetchall())
        if guards != {"inventory_price_audit_no_truncate": "O", "inventory_price_audit_immutable": "O"}:
            raise RuntimeError("Expected enabled append-only price-audit guards.")
        print("Verified append-only audit guards enabled; no per-case flush will be issued.")
        return result
