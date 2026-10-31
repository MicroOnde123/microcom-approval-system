"""Database-free timestamp handoff and sanitized failure diagnostics."""
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from django.db import IntegrityError, models
from django.db.models.functions import Now
from django.core.exceptions import ValidationError

from .models import MaterialReturnNote, CreditNote
from . import return_note_services as service
from .configuration import business_date


class ReturnNoteClockTests(unittest.TestCase):
    def note(self):
        note = MaterialReturnNote(pk=1, status="FINALIZED", finalized_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        note._state.adding = False
        return note

    def test_statement_expression_is_installed_only_after_validation(self):
        note = self.note(); order = []
        def check():
            order.append("validate"); self.assertNotIsInstance(note.finalized_at, Now)
        def persist(instance, *args, **kwargs):
            order.append("update"); self.assertIsInstance(instance.finalized_at, Now)
            self.assertNotIn("_finalize_at_statement_time", kwargs)
        with patch.object(note, "_check_immutable"), patch.object(note, "full_clean", side_effect=check), \
                patch.object(models.Model, "save", autospec=True, side_effect=persist):
            note.save(_finalize_at_statement_time=True)
        self.assertEqual(order, ["validate", "update"])

    def test_validation_failure_prevents_persistence(self):
        note = self.note()
        with patch.object(note, "_check_immutable"), patch.object(note, "full_clean", side_effect=ValidationError("blocked")), \
                patch.object(models.Model, "save") as save, self.assertRaises(ValidationError):
            note.save(_finalize_at_statement_time=True)
        save.assert_not_called()

    def test_postgresql_note_update_compiles_statement_timestamp(self):
        from django.db.backends.postgresql.base import DatabaseWrapper
        from django.db.models import Q
        from django.db.models.sql.subqueries import UpdateQuery
        backend = DatabaseWrapper({"ENGINE": "django.db.backends.postgresql", "NAME": "", "OPTIONS": {}, "TIME_ZONE": None})
        query = UpdateQuery(MaterialReturnNote)
        query.add_update_values({"finalized_at": Now()}); query.add_q(Q(pk=1))
        sql, params = query.get_compiler(connection=backend).as_sql()
        self.assertIn('"finalized_at" = STATEMENT_TIMESTAMP()', sql)
        self.assertEqual(params, (1,)); self.assertIsNone(backend.connection)

    def test_opt_in_rejects_new_draft_and_credit_records(self):
        for record in (MaterialReturnNote(status="FINALIZED"), MaterialReturnNote(status="DRAFT"), CreditNote()):
            with self.assertRaises(ValueError): record.save(_finalize_at_statement_time=True)

    def test_kinshasa_midnight_and_new_year(self):
        for instant, expected in (("2026-12-31T22:59:59+00:00", "2026-12-31"),
                                  ("2026-12-31T23:00:00+00:00", "2027-01-01")):
            self.assertEqual(business_date(datetime.fromisoformat(instant), "Africa/Kinshasa").isoformat(), expected)


class ReturnNoteDiagnosticTests(unittest.TestCase):
    def test_allowlisted_guard_without_private_error_contents(self):
        driver = Exception("PRIVATE signed confirmation and SQL")
        driver.sqlstate = "23514"
        driver.diag = SimpleNamespace(message_primary="Backdated or future issuance prohibited", constraint_name=None,
                                      context="PRIVATE", message_detail="PRIVATE")
        error = IntegrityError("PRIVATE"); error.__cause__ = driver
        with self.assertLogs(service.logger, level="WARNING") as logs:
            service._diagnose(error)
        message = logs.records[0].getMessage()
        self.assertIn("sqlstate=23514", message)
        self.assertIn("guard=return_note_timestamp_window", message)
        self.assertNotIn("PRIVATE", message)
        self.assertIsNone(logs.records[0].exc_info)

    def test_missing_and_untrusted_diagnostics_fail_safe(self):
        for primary in (None, "Backdated or future issuance prohibited PRIVATE"):
            error = IntegrityError("PRIVATE")
            error.diag = SimpleNamespace(message_primary=primary, constraint_name="PRIVATE\nSQL")
            with self.assertLogs(service.logger, level="WARNING") as logs: service._diagnose(error)
            self.assertIn("guard=unavailable", logs.output[0])
            self.assertNotIn("PRIVATE", logs.output[0])

    def test_conversion_retains_error_and_same_token_retry(self):
        from uuid import uuid4
        error = IntegrityError("PRIVATE")
        with patch.object(service, "_outermost"), patch.object(service, "_issue", side_effect=error), \
                patch.object(service, "_diagnose") as log, self.assertRaises(ValidationError) as caught:
            service.issue_material_return_note(1, None, return_movement_ids=[1], reason="Synthetic",
                issuance_token=str(uuid4()), confirmation="PRIVATE")
        log.assert_called_once_with(error)
        self.assertIs(caught.exception.__cause__, error)
        self.assertEqual(caught.exception.code, "outcome_uncertain")
