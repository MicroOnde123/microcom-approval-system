"""Mocked persistence only; these tests do not prove PostgreSQL locking."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.utils.translation import override, gettext
from django.core.management import call_command
from django.core.management.base import CommandError
from io import StringIO

from . import year_preparation as preparation


def sequence(series="MAIN", year=2026, verified=True, counter=57, fmt="FAC/{number:04d}/{year}"):
    return SimpleNamespace(series=series, year=year, is_verified=verified,
                           next_counter=counter, number_format=fmt, full_clean=Mock())


class PreparationOfflineTests(TestCase):
    def test_kinshasa_year_boundary(self):
        self.assertEqual(preparation.following_year(datetime(2026, 12, 31, 22, 59, tzinfo=timezone.utc), "Africa/Kinshasa"), 2027)
        self.assertEqual(preparation.following_year(datetime(2026, 12, 31, 23, tzinfo=timezone.utc), "Africa/Kinshasa"), 2028)

    def test_invalid_timezone_and_overflow(self):
        for moment, zone in [(datetime(2026, 1, 1, tzinfo=timezone.utc), "UTC"),
                             (datetime(9999, 1, 1, tzinfo=timezone.utc), "Africa/Kinshasa")]:
            with self.assertRaises(ValidationError):
                preparation.following_year(moment, zone)

    def run_preparation(self, rows):
        manager = Mock()
        manager.select_for_update.return_value.filter.return_value.order_by.return_value = rows
        manager.get_or_create.return_value = (sequence(year=2027, verified=False, counter=1), True)
        with patch.object(preparation.CompanyDocumentSettings, "objects") as configuration, \
                patch.object(preparation.DocumentSequence, "objects", manager), \
                patch.object(preparation, "database_now", return_value=datetime(2026, 10, 1, tzinfo=timezone.utc)):
            configuration.select_for_update.return_value.get.return_value.business_timezone = "Africa/Kinshasa"
            # Exercise the transaction body without opening a connection.
            report = preparation.prepare_invoice_year.__wrapped__()
        return report, manager

    def test_creation_preserves_source_and_requires_attestation(self):
        source = sequence()
        report, manager = self.run_preparation([source])
        self.assertEqual(report["prepared"], ["MAIN"])
        self.assertEqual(report["unverified"], ["MAIN"])
        self.assertEqual(source.next_counter, 57)
        defaults = manager.get_or_create.call_args.kwargs["defaults"]
        self.assertEqual(defaults, {"number_format": source.number_format, "starting_value": 1, "next_counter": 1})

    def test_existing_target_is_never_overwritten(self):
        target = sequence(year=2027, counter=42, verified=False)
        for _ in range(2):
            report, manager = self.run_preparation([sequence(), target])
            manager.get_or_create.assert_not_called()
            self.assertEqual(report["existing"], ["MAIN"])
        self.assertEqual(target.next_counter, 42)

    def test_unverified_source_is_not_copied(self):
        report, manager = self.run_preparation([sequence(verified=False)])
        manager.get_or_create.assert_not_called()
        self.assertEqual(report["sources"], 0)

    def test_conflicts_prevent_all_creation(self):
        report, manager = self.run_preparation([sequence(), sequence(series="OTHER")])
        self.assertEqual(report["conflicts"], [("MAIN", "OTHER")])
        manager.get_or_create.assert_not_called()

    def test_conservative_prefix_proof(self):
        self.assertFalse(preparation.conflicting_series([sequence(), sequence("OTHER", fmt="OTHER/{number}/{year}")]))
        self.assertTrue(preparation.conflicting_series([sequence(), sequence("OTHER", fmt="FAC/{year}/{number}")]))

    def test_french_labels(self):
        with override("fr"):
            self.assertEqual(gettext("Prepared"), "Préparées")
            self.assertEqual(gettext("Already existing"), "Déjà existantes")

    def test_command_reports_unverified_in_both_languages(self):
        report = {"year": 2027, "prepared": ["MAIN"], "existing": [],
                  "unverified": ["MAIN"], "conflicts": [], "sources": 1}
        for language, expected in [("en", "administrator attestation required"),
                                   ("fr", "attestation d’un administrateur requise")]:
            output = StringIO()
            with patch("invoicing.management.commands.prepare_invoice_year.prepare_invoice_year", return_value=report):
                call_command("prepare_invoice_year", language=language, stdout=output)
            self.assertIn(expected, output.getvalue())
            self.assertIn("2027", output.getvalue())

    def test_command_conflict_is_failure(self):
        report = {"year": 2027, "prepared": [], "existing": [], "unverified": [],
                  "conflicts": [("MAIN", "OTHER")], "sources": 2}
        errors = StringIO()
        with patch("invoicing.management.commands.prepare_invoice_year.prepare_invoice_year", return_value=report):
            with self.assertRaises(CommandError):
                call_command("prepare_invoice_year", stdout=StringIO(), stderr=errors)
        self.assertIn("MAIN / OTHER", errors.getvalue())
