"""Synthetic errors and mocked transactions only; no database is required."""
from contextlib import contextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError
from django.utils.translation import gettext, override

from . import services


MESSAGE = "The invoice could not be saved safely. Reload it and ask an administrator to review its evidence or numbering configuration."


class SyntheticDriverError(Exception):
    pass


class IntegrityDiagnosticTests(unittest.TestCase):
    def wrapped_error(self, **attributes):
        driver = SyntheticDriverError("SECRET exception text with SQL and credentials")
        for name, value in attributes.items():
            setattr(driver, name, value)
        error = IntegrityError("SECRET wrapper text")
        error.__cause__ = driver
        return error

    def logged(self, error):
        with self.assertLogs("invoicing.services", level="WARNING") as logs:
            services._log_integrity_error(error)
        self.assertEqual(len(logs.records), 1)
        record = logs.records[0]
        self.assertIsNone(record.exc_info); self.assertIsNone(record.stack_info)
        self.assertNotIn("SECRET", record.getMessage())
        return record.getMessage()

    def test_allowlisted_guard_and_psycopg2_metadata_only(self):
        error = self.wrapped_error(pgcode="23514", diag=SimpleNamespace(
            constraint_name="invoice_total_nonnegative", message_primary="Backdated or future finalization is prohibited",
            message_detail="SECRET SQL", context="SECRET invoice data"))
        message = self.logged(error)
        for value in ("exception_class=SyntheticDriverError", "sqlstate=23514", "constraint=invoice_total_nonnegative",
                "guard=finalization_timestamp_window"):
            self.assertIn(value, message)
        self.assertNotIn("Backdated", message)

    def test_psycopg3_sqlstate_fallback(self):
        message = self.logged(self.wrapped_error(pgcode=None, sqlstate="23505", diag=SimpleNamespace(constraint_name="number_key")))
        self.assertIn("sqlstate=23505", message); self.assertIn("constraint=number_key", message)

    def test_missing_driver_diagnostics(self):
        message = self.logged(IntegrityError("SECRET"))
        self.assertIn("exception_class=IntegrityError", message)
        for value in ("sqlstate=unavailable", "constraint=unavailable", "guard=unavailable"):
            self.assertIn(value, message)

    def test_untrusted_metadata_and_near_match_are_not_logged(self):
        message = self.logged(self.wrapped_error(pgcode="23514\nSECRET", sqlstate="SECRET", diag=SimpleNamespace(
            constraint_name="number_key\nSECRET", message_primary="Backdated or future finalization is prohibited SECRET")))
        self.assertIn("sqlstate=unavailable", message); self.assertIn("constraint=unavailable", message)
        self.assertIn("guard=unavailable", message)

    def test_broken_driver_properties_do_not_mask_original(self):
        class Broken(Exception):
            @property
            def diag(self):
                raise RuntimeError("SECRET")
            @property
            def pgcode(self):
                raise RuntimeError("SECRET")
        error = IntegrityError("SECRET"); error.__cause__ = Broken()
        self.assertIn("sqlstate=unavailable", self.logged(error))

    def test_handler_retains_translated_message_chaining_and_transaction_exit(self):
        for language in ("en", "fr"):
            error = self.wrapped_error(pgcode="23514")
            state = {"exited": False}
            @contextmanager
            def atomic():
                try:
                    yield
                finally:
                    state["exited"] = True
            @services.financial_transaction
            def fail():
                raise error
            def diagnostic(original):
                self.assertTrue(state["exited"]); self.assertIs(original, error)
            with override(language), patch.object(services.transaction, "atomic", side_effect=atomic), \
                    patch.object(services, "_log_integrity_error", side_effect=diagnostic), self.assertRaises(ValidationError) as caught:
                fail()
            self.assertEqual(caught.exception.messages, [gettext(MESSAGE)] if language == "en" else [self.french_message()])
            self.assertIs(caught.exception.__cause__, error)
            self.assertIs(caught.exception.__cause__.__cause__, error.__cause__)

    def french_message(self):
        with override("fr"):
            return gettext(MESSAGE)

    def test_logging_failure_does_not_change_conversion(self):
        error = self.wrapped_error()
        @services.financial_transaction
        def fail():
            raise error
        with patch.object(services.transaction, "atomic"), patch.object(services.logger, "warning", side_effect=RuntimeError("SECRET")), \
                self.assertRaises(ValidationError) as caught:
            fail()
        self.assertIs(caught.exception.__cause__, error)

    def test_integrity_error_at_transaction_exit_is_also_converted(self):
        error = self.wrapped_error(pgcode="23514")
        @services.financial_transaction
        def success():
            return "value"
        with patch.object(services.transaction, "atomic") as atomic, patch.object(services, "_log_integrity_error") as diagnostic:
            atomic.return_value.__exit__.side_effect = error
            with self.assertRaises(ValidationError) as caught:
                success()
        diagnostic.assert_called_once_with(error); self.assertIs(caught.exception.__cause__, error)

    def test_success_and_non_integrity_errors_are_unchanged(self):
        @services.financial_transaction
        def success():
            return 42
        error = OperationalError("SECRET")
        @services.financial_transaction
        def other_failure():
            raise error
        with patch.object(services.transaction, "atomic"), patch.object(services.logger, "warning") as warning:
            self.assertEqual(success(), 42)
            with self.assertRaises(OperationalError) as caught:
                other_failure()
            self.assertIs(caught.exception, error)
        warning.assert_not_called()
