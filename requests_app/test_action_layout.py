"""Screen-only presentation contracts; never connects to a database."""
from pathlib import Path
import unittest
from unittest.mock import patch
from django.db.backends.base.base import BaseDatabaseWrapper
from django.template.loader import get_template

ROOT = Path(__file__).resolve().parents[1]


class ActionLayoutTests(unittest.TestCase):
    def test_all_user_templates_compile_without_database_access(self):
        with patch.object(BaseDatabaseWrapper, "ensure_connection", side_effect=AssertionError("No database access")):
            for path in (ROOT / "templates").rglob("*.html"):
                with self.subTest(template=str(path)):
                    get_template(path.relative_to(ROOT / "templates").as_posix())

    def test_shared_rules_are_scoped_to_application_screens(self):
        css = (ROOT / "static/css/action_layout.css").read_text(encoding="utf-8")
        self.assertIn("@media screen", css)
        self.assertNotIn("@media print", css)
        self.assertIn(".app-container .ops-badge", css)
        self.assertIn("white-space:nowrap", css)
        self.assertIn("flex-shrink:0", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("min-height:42px", css)
        self.assertIn(".btn-tertiary", css); self.assertIn(".btn-danger", css)

    def test_screen_chrome_is_not_loaded_by_printable_documents(self):
        for name in ("requests_app/approved_document.html", "requests_app/bulk_print_material_documents.html",
                     "requests_app/permission_document.html", "invoicing/print_document.html"):
            source = (ROOT / "templates" / name).read_text(encoding="utf-8")
            self.assertNotIn("action_layout.css", source)

    def test_invoice_actions_keep_post_csrf_and_separate_document_toolbar(self):
        source = (ROOT / "templates/invoicing/detail.html").read_text(encoding="utf-8")
        self.assertIn('class="context-toolbar"', source)
        self.assertIn('method="post"', source)
        self.assertIn("{% csrf_token %}", source)
        self.assertIn("'invoicing:print' invoice.pk", source)
        self.assertIn('if invoice.status == \'FINALIZED\'', source)
        self.assertIn('invoicing/return_notes/links.html', source)

    def test_request_actions_preserve_confirmation_and_eligibility(self):
        source = (ROOT / "templates/requests_app/request_detail.html").read_text(encoding="utf-8")
        for token in ("active_approval_for_user", "request_obj.stock_deducted", "can_cancel_request",
                      "request.user.can_manage_stock", "onclick=\"return confirm(", "{% csrf_token %}",
                      "'material_document' request_obj.id 'BC'", "'material_document' request_obj.id 'BS'"):
            self.assertIn(token, source)
        self.assertIn('class="btn btn-danger"', source)
        self.assertIn('class="context-toolbar"', source)
