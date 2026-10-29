"""Database-free validation and PDF tests; use the dedicated offline runner."""
import ast
import unittest
from copy import deepcopy
from unittest.mock import patch

from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.template import Context, Engine
from django.utils.translation import override, gettext

from inventory.models import Succursale
from invoicing.pdf import render_pdf, RENDERER_VERSION
from invoicing.pdf_test_tools import pdf_text


class AddressOfflineTests(unittest.TestCase):
    def test_new_address_required_in_both_languages(self):
        for language in ("en", "fr"):
            with self.subTest(language=language), override(language):
                branch = Succursale(code="NEW", name="New", physical_address=" \n ")
                with self.assertRaises(ValidationError) as caught:
                    branch.full_clean(validate_unique=False, validate_constraints=False)
                self.assertIn("physical_address", caught.exception.message_dict)
                self.assertEqual(caught.exception.message_dict["physical_address"],
                    [gettext("Enter a physical address for a new succursale.")])

    def test_new_multiline_address_is_trimmed(self):
        branch = Succursale(code="NEW", name="New", physical_address="  Avenue Équateur\nKinshasa  ")
        branch.full_clean(validate_unique=False, validate_constraints=False)
        self.assertEqual(branch.physical_address, "Avenue Équateur\nKinshasa")

    def test_legacy_blank_can_be_edited(self):
        branch = Succursale(pk=9, code="OLD", name="Updated", physical_address="")
        branch._state.adding = False
        branch.full_clean(validate_unique=False, validate_constraints=False)
        self.assertEqual(branch.physical_address, "")

    def test_admin_generated_form_requires_address_only_on_creation(self):
        form_class = modelform_factory(Succursale, fields=("code", "name", "physical_address"))
        self.assertIsInstance(form_class().fields["physical_address"].widget, forms.Textarea)
        with patch.object(Succursale, "validate_unique"):
            self.assertFalse(form_class({"code": "NEW", "name": "New", "physical_address": ""}).is_valid())
            legacy = Succursale(pk=9, code="OLD", name="Old")
            legacy._state.adding = False
            self.assertTrue(form_class({"code": "OLD", "name": "Updated", "physical_address": ""}, instance=legacy).is_valid())

    def snapshot(self):
        return {"company": {"company_name": "Microcom", "company_address": "Company address", "contact_details": "Contact"},
            "branch": {"code": "KIN", "name": "Kinshasa", "physical_address": "12, avenue Équateur\nBâtiment A & <B>"},
            "branding": {"strategy": "no-logo"}, "number": "FAC/SYNTHETIC", "issue_date": "2026-10-27",
            "request_reference": "REQ/SYNTHETIC", "total": "2.00", "currency": "USD", "amount_words_fr": "deux dollars",
            "note": "", "lines": [{"code": "MAT", "description": "Câble", "unit": "m", "quantity": "1", "price": "2", "total": "2"}]}

    def test_bilingual_pdf_retains_but_does_not_display_frozen_address(self):
        snapshot = self.snapshot(); original = deepcopy(snapshot)
        for language, label in (("en", "Succursale physical address"), ("fr", "Adresse physique de la succursale")):
            text = pdf_text(render_pdf(snapshot, language=language))
            for value in (label, "12, avenue Équateur", "Bâtiment A & <B>"):
                self.assertNotIn("".join(value.split()), "".join(text.split()))
        self.assertEqual(snapshot, original)
        self.assertIn("v4", RENDERER_VERSION)

    def test_legacy_pdf_without_address_remains_renderable(self):
        snapshot = self.snapshot(); del snapshot["branch"]["physical_address"]
        for language in ("en", "fr"):
            self.assertTrue(render_pdf(snapshot, language=language).startswith(b"%PDF-"))

    def test_detail_template_compiles(self):
        from pathlib import Path
        Engine(libraries={"i18n": "django.templatetags.i18n"}).from_string(
            Path("templates/invoicing/detail.html").read_text(encoding="utf-8"))

    def test_detail_address_uses_escaped_snapshot_only(self):
        from pathlib import Path
        source = Path("templates/invoicing/detail.html").read_text(encoding="utf-8")
        block = source.split("{% if invoice.succursale_snapshot.physical_address %}", 1)[1].split("{% endif %}", 1)[0]
        template = Engine(libraries={"i18n": "django.templatetags.i18n"}).from_string("{% load i18n %}" + block)
        for language in ("en", "fr"):
            with override(language):
                result = template.render(Context({"invoice": {"succursale_snapshot": self.snapshot()["branch"]}}))
                self.assertIn("Équateur<br>", result)
                self.assertIn("&amp; &lt;B&gt;", result)

    def test_migration_state_matches_models_without_database(self):
        from django.apps import apps
        from django.db.migrations.loader import MigrationLoader
        from django.db.migrations.state import ProjectState
        from django.db.migrations.autodetector import MigrationAutodetector
        loader = MigrationLoader(None)
        changes = MigrationAutodetector(loader.project_state(), ProjectState.from_apps(apps)).changes(graph=loader.graph)
        self.assertEqual(changes, {})

    def test_address_translations(self):
        for message in ("Physical address", "Enter a physical address for a new succursale.",
            "Enter the succursale physical address before finalizing this invoice.", "Succursale physical address",
            "Required for new succursales and future invoice issuance. Existing blank addresses may be completed later."):
            with override("fr"):
                self.assertNotEqual(gettext(message), message)

    def test_return_note_keeps_original_branch_snapshot(self):
        from pathlib import Path
        tree = ast.parse(Path("invoicing/return_note_services.py").read_text(encoding="utf-8"))
        assignments = [ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.Assign)]
        self.assertTrue(any("note.succursale_snapshot" in code and "invoice.succursale_snapshot" in code
                            for code in assignments))

    def test_address_check_precedes_line_writes_and_numbering(self):
        from pathlib import Path
        tree = ast.parse(Path("invoicing/services.py").read_text(encoding="utf-8"))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "finalize_invoice")
        guard = next(node for node in function.body if isinstance(node, ast.If) and ast.unparse(node.test) == "not address")
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and ast.unparse(node.func) in {"line.save", "invoice.save", "sequence.save", "_issuance_sequence"}:
                self.assertLess(guard.lineno, node.lineno)
