"""Synthetic PDF/HTTP contracts and template checks. No financial DB writes."""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template import Context, Engine
from django.urls import resolve, reverse
from django.utils.translation import override
from pypdf import PdfReader

from inventory import test_address_offline as synthetic
from . import documents, views
from .pdf import render_pdf


class InvoicePdfDeliveryTests(SimpleTestCase):
    def setUp(self):
        from .test_mock_http import isolate_mock_context
        isolate_mock_context(self)

    def request(self, method="get"):
        request = getattr(RequestFactory(), method)("/invoices/1/print/")
        request.user = Mock(is_authenticated=True, is_active=True)
        return request

    def test_print_and_download_redirect_to_protected_get_without_html_or_javascript(self):
        for language in ("en", "fr"):
            for attachment, route in ((False, "invoicing:download"), (True, "invoicing:download_file")):
                with self.subTest(language=language, attachment=attachment), override(language), \
                        patch.object(views, "_invoice", return_value=SimpleNamespace(status="FINALIZED")), \
                        patch.object(views, "generate_pdf", return_value=SimpleNamespace(pk=9)) as generate:
                    request = self.request("post")
                    response = views.invoice_print(request, 1, attachment=attachment)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], reverse(route, args=[9]))
                generate.assert_called_once_with(1, request.user, language=language)
                self.assertIn("no-store", response["Cache-Control"])

    def test_inline_and_attachment_serve_readable_pdf_bytes_with_private_headers(self):
        snapshot = synthetic.AddressOfflineTests().snapshot()
        before = deepcopy(snapshot)
        for language in ("en", "fr"):
            content = render_pdf(snapshot, language)
            artifact = SimpleNamespace(invoice_id=1, language=language)
            for attachment in (False, True):
                with self.subTest(language=language, attachment=attachment), \
                        patch.object(views, "require_permission"), \
                        patch.object(views, "download_pdf", return_value=(artifact, io.BytesIO(content))):
                    response = views.invoice_download(self.request(), 9, attachment=attachment)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertTrue(response["Content-Disposition"].startswith("attachment;" if attachment else "inline;"))
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response["Referrer-Policy"], "no-referrer")
                self.assertIn("no-store", response["Cache-Control"])
                data = b"".join(response.streaming_content)
                response.close()
                self.assertEqual(data, content)
                self.assertTrue(PdfReader(io.BytesIO(data)).pages)
        self.assertEqual(snapshot, before)

    def test_download_rechecks_permissions_and_never_generates_a_pdf(self):
        with patch.object(views, "require_permission"), \
                patch.object(views, "download_pdf", side_effect=PermissionDenied), \
                patch.object(views, "generate_pdf") as generate:
            with self.assertRaises(PermissionDenied):
                views.invoice_download(self.request(), 9)
        generate.assert_not_called()

    def test_storage_read_rechecks_object_scope_before_reading_bytes(self):
        artifact = SimpleNamespace(invoice=SimpleNamespace(request_id=71, status="FINALIZED"))
        with patch.object(documents.DocumentArtifact.objects, "select_related") as query, \
                patch.object(documents, "authorize", side_effect=PermissionDenied), \
                patch.object(documents, "artifact_bytes") as read:
            query.return_value.get.return_value = artifact
            with self.assertRaises(PermissionDenied):
                documents.download_pdf(9, self.request().user)
        read.assert_not_called()

    def test_missing_or_corrupt_stored_artifact_fails_closed_without_rewriting(self):
        content = render_pdf(synthetic.AddressOfflineTests().snapshot(), "en")
        with TemporaryDirectory(prefix="microcom-pdf-delivery-") as folder, \
                override_settings(INVOICE_DOCUMENT_ROOT=folder, MEDIA_ROOT="", STATIC_ROOT="", STATICFILES_DIRS=[]):
            path = Path(folder) / ("a" * 32 + ".pdf")
            artifact = SimpleNamespace(rendering_status="READY", file_reference=path.name,
                                       checksum=hashlib.sha256(content).hexdigest())
            path.write_bytes(content)
            self.assertEqual(documents.artifact_bytes(artifact), content)
            path.write_bytes(b"%PDF-damaged")
            with self.assertRaises(ValidationError):
                documents.artifact_bytes(artifact)
            self.assertEqual(path.read_bytes(), b"%PDF-damaged")
            path.unlink()
            with self.assertRaises(ValidationError):
                documents.artifact_bytes(artifact)

    def test_delivery_errors_are_controlled_and_do_not_regenerate(self):
        for error in (ValidationError("The private PDF is unavailable or damaged. Generate it again."),
                      OSError("PRIVATE_PATH_MUST_NOT_LEAK")):
            with self.subTest(error=type(error).__name__), patch.object(views, "require_permission"), \
                    patch.object(views, "download_pdf", side_effect=error), \
                    patch.object(views, "generate_pdf") as generate:
                response = views.invoice_download(self.request(), 9, attachment=True)
            self.assertEqual(response.status_code, 409)
            self.assertNotIn(b"PRIVATE_PATH_MUST_NOT_LEAK", response.content)
            generate.assert_not_called()

    def test_missing_artifact_returns_404(self):
        with patch.object(views, "require_permission"), \
                patch.object(views, "download_pdf", side_effect=documents.DocumentArtifact.DoesNotExist):
            from django.http import Http404
            with self.assertRaises(Http404):
                views.invoice_download(self.request(), 99)

    def test_new_routes_keep_generation_post_only_and_csrf_protected(self):
        path = resolve(reverse("invoicing:download_invoice", args=[1]))
        self.assertTrue(path.kwargs["attachment"])
        self.assertEqual(views.invoice_print(self.request(), 1, attachment=True).status_code, 405)
        request = self.request("post")
        self.assertEqual(CsrfViewMiddleware(lambda request: HttpResponse()).process_view(
            request, path.func, (), path.kwargs).status_code, 403)
        for route in ("invoicing:download", "invoicing:download_file"):
            delivery = resolve(reverse(route, args=[9]))
            self.assertEqual(delivery.func, views.invoice_download)
        anonymous = self.request()
        anonymous.user = SimpleNamespace(is_authenticated=False)
        self.assertEqual(views.invoice_download(anonymous, 9, attachment=True).status_code, 302)

    def test_toolbar_permissions_status_order_and_bilingual_labels(self):
        template = Path("templates/invoicing/detail.html").read_text(encoding="utf-8")
        engine = Engine(loaders=[("django.template.loaders.locmem.Loader", {
            "base.html": "{% block content %}{% endblock %}", "detail.html": template})],
            libraries={"i18n": "django.templatetags.i18n", "static": "django.templatetags.static"})
        for language in ("en", "fr"):
            for status in ("DRAFT", "FINALIZED"):
                for can_read, can_issue in ((False, False), (True, False), (True, True)):
                    with self.subTest(language=language, status=status, read=can_read, issue=can_issue), override(language):
                        html = engine.get_template("detail.html").render(Context({
                            "invoice": SimpleNamespace(pk=1, status=status, get_status_display=status,
                                                       currency="USD", total=2, number="SYNTHETIC"),
                            "return_note_nav": {"can_read": can_read, "can_issue": can_issue, "invoice_id": 1},
                            "lines": [], "audit_history": []}))
                        issue = reverse("invoicing:return_note_select", args=[1])
                        history = reverse("invoicing:return_note_history", args=[1])
                        self.assertEqual(issue in html, status == "FINALIZED" and can_read and can_issue)
                        self.assertEqual(history in html, status == "FINALIZED" and can_read)
                        self.assertEqual("invoice-actions__documents" in html, status == "FINALIZED")
                        if status == "FINALIZED":
                            self.assertIn(reverse("invoicing:download_invoice", args=[1]), html)
                            self.assertIn("Print Invoice" if language == "en" else "Imprimer la facture", html)
                            self.assertIn("Download PDF" if language == "en" else "Télécharger PDF", html)
                            if can_read and can_issue:
                                self.assertLess(html.index("invoice-actions__documents"), html.index(issue))
                                self.assertLess(html.index('href="' + issue + '"'), html.index('href="' + history + '"'))
