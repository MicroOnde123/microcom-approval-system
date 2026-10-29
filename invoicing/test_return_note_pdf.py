"""Pure synthetic PDF tests: no database evidence or operational issuance."""
from copy import deepcopy
import ast
from pathlib import Path
import re
import unittest

from django.conf import settings
from django.core.exceptions import ValidationError
from .return_note_pdf import render_pdf
from .pdf_test_tools import pdf_text

ROOT = Path(__file__).resolve().parents[1]


def snapshot():
    return {"company": {"company_name": "SYNTHETIC Microcom", "company_address": "Synthetic address",
             "contact_details": "offline@example.invalid"}, "branch": {"code": "SYN", "name": "Succursale synthétique"},
        "branding": {"version": 1, "strategy": "no-logo"}, "number": "BR-SYN/0007/2026", "issue_date": "2026-10-27",
        "request_reference": "REQ-SYN-001", "original": {"number": "FAC-SYN/0001/2026", "issue_date": "2026-10-26", "total": "6.00"},
        "currency": "USD", "total": "2.00", "cumulative_returned_value": "2.00", "adjusted_net_value": "4.00",
        "amount_words_fr": "deux dollars américains", "reason": "Matériaux inutilisés & <retournés>",
        "lines": [{"movement": 42, "code": "SYN-CABLE", "description": "Câble électrique € & <test>", "unit": "pcs",
                   "quantity": "1.00", "price": "2.0000", "total": "2.00"}]}


def translation_messages():
    messages = set()
    for p in (ROOT / "invoicing").glob("return_note*.py"):
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_" and n.args and
                    isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
                messages.add(n.args[0].value)
    for p in (ROOT / "templates/invoicing/return_notes").glob("*.html"):
        for m in re.finditer(r"{%\s*trans\s+([\"'])(.*?)\1\s*%}", p.read_text(encoding="utf-8")):
            messages.add(m[2])
    messages.add("A material return note can optionally value returns already recorded in stock.")
    return messages


class ReturnNotePdfTests(unittest.TestCase):
    def test_english_french_frozen_values_and_explicit_nonpayment_language(self):
        source = snapshot(); before = deepcopy(source)
        for lang, title, value in [("en", "Material return note", "Returned value on this note"),
                                   ("fr", "Bon de retour", "Valeur retournée sur ce bon")]:
            with self.subTest(language=lang):
                content = render_pdf(source, lang); text = pdf_text(content)
                compact = re.sub(r"\s+", "", text)
                for item in [title, value, source["number"], source["original"]["number"], "REQ-SYN-001", "42",
                    "Câble électrique € & <test>", "USD", "2.00", "4.00", "6.00", source["amount_words_fr"], source["reason"]]:
                    self.assertIn(re.sub(r"\s+", "", item), compact)
                self.assertNotIn("Total amount payable", text); self.assertNotIn("Montant total à payer", text)
                self.assertNotIn(b"/Subtype /Image", content)
                self.assertNotIn("2.0000", text)
                output = getattr(settings, "RETURN_NOTE_OFFLINE_EVIDENCE_ROOT", ROOT / "local_artifacts/checkpoint_er3_evidence")
                output.mkdir(exist_ok=True)
                (output / f"synthetic-return-note-{lang}.pdf").write_bytes(content)
                (output / f"synthetic-return-note-{lang}-text.txt").write_text(text, encoding="utf-8")
        self.assertEqual(source, before)

    def test_multiple_pages_long_descriptions_and_footer(self):
        source = snapshot()
        source["lines"] = [{**source["lines"][0], "movement": n, "description": "Matériel & <description> " * 15} for n in range(70)]
        for lang in ["en", "fr"]:
            text = pdf_text(render_pdf(source, lang))
            self.assertIn("Page 2", text)
            self.assertIn("69", text)

    def test_zero_values_and_four_decimal_prices_are_not_lost(self):
        source = snapshot(); source["total"] = "0.00"
        source["lines"][0].update(quantity="0.25", price="0.0050", total="0.00")
        text = pdf_text(render_pdf(source, "en"))
        for value in ["0.25", "0.005", "0.00"]: self.assertIn(value, text)

    def test_invalid_language_unsupported_glyph_and_bad_frozen_logo_fail(self):
        with self.assertRaises(ValidationError): render_pdf(snapshot(), "de")
        source = snapshot(); source["reason"] = "Unsupported \U0001f680"
        with self.assertRaises(ValidationError): render_pdf(source, "en")
        source = snapshot(); source["branding"] = {"strategy": "embedded-content", "content_base64": "YnJva2Vu",
                                                  "sha256": "wrong", "content_type": "image/png"}
        with self.assertRaises(ValidationError): render_pdf(source, "fr")
