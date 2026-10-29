"""Timestamp handoff tests with mocked persistence only; no database/network."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Now

from .configuration import business_date
from .models import DocumentSequence, Invoice
from . import services


class InvoiceStatementClockTests(unittest.TestCase):
    def invoice(self):
        invoice = Invoice(pk=1, status="FINALIZED", finalized_at=datetime(2026, 10, 27, tzinfo=timezone.utc))
        invoice._state.adding = False
        return invoice

    def test_timestamp_expression_is_assigned_after_all_model_checks(self):
        invoice = self.invoice(); old = invoice.finalized_at; order = []
        def immutable():
            order.append("immutable"); self.assertEqual(invoice.finalized_at, old)
        def validate():
            order.append("validation"); self.assertEqual(invoice.finalized_at, old)
            # Simulate arbitrarily delayed database validation; no sleeping.
            invoice.finalized_at = old - timedelta(minutes=10)
        def persist(instance, *args, **kwargs):
            order.append("update"); self.assertIsInstance(instance.finalized_at, Now)
            self.assertNotIn("_finalize_at_statement_time", kwargs)
        with patch.object(invoice, "_check_immutable", side_effect=immutable), \
                patch.object(invoice, "full_clean", side_effect=validate), patch.object(models.Model, "save", autospec=True, side_effect=persist):
            invoice.save(_finalize_at_statement_time=True)
        self.assertEqual(order, ["immutable", "validation", "update"])

    def test_postgresql_expression_uses_statement_not_transaction_time(self):
        with patch.object(Now, "as_sql", return_value=("STATEMENT_TIMESTAMP()", [])) as sql:
            self.assertEqual(Now().as_postgresql(None, None)[0], "STATEMENT_TIMESTAMP()")
        self.assertEqual(sql.call_args.kwargs["template"], "STATEMENT_TIMESTAMP()")

    def test_postgresql_update_compiles_timestamp_in_the_same_statement(self):
        from django.db.backends.postgresql.base import DatabaseWrapper
        from django.db.models import Q
        from django.db.models.sql.subqueries import UpdateQuery
        # Unconnected compiler only: no socket, transaction or SQL execution.
        backend = DatabaseWrapper({"ENGINE": "django.db.backends.postgresql", "NAME": "", "OPTIONS": {}, "TIME_ZONE": None})
        query = UpdateQuery(Invoice)
        query.add_update_values({"finalized_at": Now()})
        query.add_q(Q(pk=1))
        sql, params = query.get_compiler(connection=backend).as_sql()
        self.assertIn('"finalized_at" = STATEMENT_TIMESTAMP()', sql)
        self.assertEqual(params, (1,))
        self.assertIsNone(backend.connection)

    def test_validation_and_immutability_failures_still_block_save(self):
        for method in ("_check_immutable", "full_clean"):
            invoice = self.invoice()
            with patch.object(invoice, "_check_immutable"), patch.object(invoice, "full_clean"), \
                    patch.object(invoice, method, side_effect=ValidationError("blocked")), patch.object(models.Model, "save") as save:
                with self.assertRaises(ValidationError):
                    invoice.save(_finalize_at_statement_time=True)
                save.assert_not_called()

    def test_opt_in_cannot_be_used_on_drafts_new_invoices_or_other_records(self):
        invoices = [Invoice(status="FINALIZED"), self.invoice(), DocumentSequence()]
        invoices[1].status = "DRAFT"
        for invoice in invoices:
            with patch.object(models.Model, "save") as save, self.assertRaises(ValueError):
                invoice.save(_finalize_at_statement_time=True)
            save.assert_not_called()

    def test_ordinary_saves_preserve_the_existing_timestamp(self):
        invoice = self.invoice(); moment = invoice.finalized_at
        with patch.object(invoice, "_check_immutable"), patch.object(invoice, "full_clean"), patch.object(models.Model, "save"):
            invoice.save()
        self.assertEqual(invoice.finalized_at, moment)

    def test_kinshasa_midnight_and_year_boundary(self):
        before = datetime(2026, 12, 31, 22, 59, 59, tzinfo=timezone.utc)
        self.assertEqual(str(business_date(before, "Africa/Kinshasa")), "2026-12-31")
        self.assertEqual(str(business_date(before + timedelta(seconds=1), "Africa/Kinshasa")), "2027-01-01")

    def test_year_change_during_sequence_lock_still_rejects(self):
        before = datetime(2026, 12, 31, 22, 59, 59, tzinfo=timezone.utc)
        sequence = SimpleNamespace(year=2026, is_verified=True, full_clean=Mock())
        with patch.object(services, "database_now", side_effect=[before, before + timedelta(seconds=1)]), \
                patch.object(services.DocumentSequence.objects, "select_for_update") as lock:
            lock.return_value.get.return_value = sequence
            with self.assertRaises(ValidationError):
                services._issuance_sequence("MAIN", SimpleNamespace(business_timezone="Africa/Kinshasa"))
        sequence.full_clean.assert_called_once_with()

    def test_service_refreshes_database_time_before_audit(self):
        tree = ast.parse(Path("invoicing/services.py").read_text(encoding="utf-8"))
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "finalize_invoice")
        save = next(n for n in ast.walk(function) if isinstance(n, ast.Call) and ast.unparse(n.func) == "invoice.save")
        self.assertEqual({k.arg: ast.literal_eval(k.value) for k in save.keywords}, {"_finalize_at_statement_time": True})
        refresh = next(n for n in ast.walk(function) if isinstance(n, ast.Call) and ast.unparse(n.func) == "invoice.refresh_from_db")
        audit = next(n for n in ast.walk(function) if isinstance(n, ast.Call) and ast.unparse(n.func) == "_event")
        self.assertLess(save.lineno, refresh.lineno); self.assertLess(refresh.lineno, audit.lineno)

    def test_timestamp_and_business_date_guards_are_present(self):
        source = Path("invoicing/migrations/0002_financial_guards.py").read_text(encoding="utf-8")
        for fragment in ("statement_timestamp()-interval '5 seconds'", "NEW.finalized_at := clock_timestamp()",
                "NEW.issue_date IS DISTINCT FROM docdate", "s.year<>extract(year FROM docdate)::int"):
            self.assertIn(fragment, source)
