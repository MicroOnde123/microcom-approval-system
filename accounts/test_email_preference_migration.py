"""Migration test: disposable local database only, no historical notification backfill."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EmailPreferenceMigrationTests(TransactionTestCase):
    def test_existing_and_new_users_default_to_enabled(self):
        executor=MigrationExecutor(connection)
        leaves=executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([("accounts","0003_user_can_view_administration_reports")])
            old=executor.loader.project_state([("accounts","0003_user_can_view_administration_reports")]).apps
            user=old.get_model("accounts","User").objects.create(username="before-preference")
            executor=MigrationExecutor(connection); executor.migrate(leaves)
            apps=executor.loader.project_state(leaves).apps
            User=apps.get_model("accounts","User")
            self.assertTrue(User.objects.get(pk=user.pk).receive_email_notifications)
            self.assertTrue(User.objects.create(username="after-preference").receive_email_notifications)
            legacy=old.get_model("accounts","User").objects.create(username="old-client-after-migration")
            self.assertTrue(User.objects.get(pk=legacy.pk).receive_email_notifications)
            self.assertEqual(apps.get_model("requests_app","WorkflowNotification").objects.count(),0)
        finally:
            MigrationExecutor(connection).migrate(leaves)
