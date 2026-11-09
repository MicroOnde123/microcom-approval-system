"""Run each method alone with FreshDatabaseRunner and full PostgreSQL migrations."""
import json
from copy import deepcopy
from django.test import TransactionTestCase
from . import test_permission_resubmission as permission_tests
from .services import resubmit_request


class AgentConcurrencyTests(permission_tests.PermissionFixtures, TransactionTestCase):
    run_parallel = permission_tests.PermissionConcurrencyTests.run_parallel

    def scenario(self, changed):
        req = self.make_request(permission_group="SITE_AUTHORIZATION", site="Concurrent site",
            site_selections=json.dumps([{"kind":"manual", "key":"concurrent-site", "name":"Concurrent site"}]),
            valid_from="2026-11-09", valid_to="2026-11-10", agent_selections=json.dumps([
                {"kind":"user", "user_id":self.people[0].pk},
                {"kind":"manual", "key":"person", "first_name":"Concurrent", "surname":"Person"}]))
        self.returned(req)
        previous = deepcopy(req.metadata_json["agent_attempts"][0])
        if changed:
            req.metadata_json["agent_selections"][1]["surname"] = "Corrected"
            req.save(update_fields=["metadata_json"])
        results = self.run_parallel([lambda: resubmit_request(req, self.owner)] * 2)
        self.assertCountEqual(results, ["ok", "rejected"])
        req.refresh_from_db()
        self.assertEqual(len(req.metadata_json["agent_attempts"]), 2)
        old, new = req.metadata_json["agent_attempts"]
        self.assertEqual(old["people"], previous["people"])
        self.assertEqual(old["id"], previous["id"])
        self.assertNotEqual(new["id"], old["id"])
        self.assertEqual(old["archive_log_id"], req.audit_logs.get(action="APPROVAL_HISTORY_ARCHIVED").pk)
        self.assertEqual(new["approval_ids"], list(req.approvals.order_by("step_order").values_list("pk", flat=True)))
        self.assertEqual(req.audit_logs.filter(action="RESUBMITTED").count(), 1)
        self.assertEqual(req.current_step_order, 1 if changed else 2)

    def test_concurrent_unchanged_snapshot_resumes_once(self):
        self.scenario(False)

    def test_concurrent_corrected_snapshot_restarts_once(self):
        self.scenario(True)
