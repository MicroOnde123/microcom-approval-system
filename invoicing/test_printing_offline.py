"""Synthetic PDFs, mocked ORM and local HTTP only. No financial records or DB."""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware
from django.template import Context, Engine, Library
from django.test import RequestFactory, override_settings
from django.urls import reverse, resolve
from django.utils.translation import override
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from . import documents, printing, views
from inventory import test_address_offline as synthetic
from .pdf import render_pdf, RENDERER_VERSION


class InvoicePrintingTests(unittest.TestCase):
    def test_client_only_layout_in_both_languages_preserves_snapshot(self):
        snapshot = synthetic.AddressOfflineTests().snapshot()
        snapshot["company"] = {"company_name": "MICROCOM PRIVATE ISSUER",
                               "company_address": "ISSUER ADDRESS PRIVATE",
                               "contact_details": "issuer-private@example.invalid"}
        snapshot["branch"]["name"] = "Kinshasa Équateur & <Centre>"
        snapshot["number"] = "FAC/10000/2027"
        before = deepcopy(snapshot)
        for language, label, title in (("en", "Client: ", "Invoice"), ("fr", "Client : ", "Facture")):
            reader = PdfReader(io.BytesIO(render_pdf(snapshot, language)))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn(label + snapshot["branch"]["name"], text)
            self.assertIn(title, text)
            for hidden in snapshot["company"].values():
                self.assertNotIn(hidden, text)
            self.assertNotIn("Succursale:", text)
            self.assertNotIn("Succursale :", text)
            self.assertFalse(reader.metadata.author)
            for value in (snapshot["number"], snapshot["issue_date"], snapshot["request_reference"],
                          snapshot["lines"][0]["description"], "2.00 USD", snapshot["amount_words_fr"] if language == "fr" else "two US dollars", snapshot["branch"]["physical_address"].splitlines()[0]):
                self.assertIn(value, text)
            self.assertEqual(snapshot, before)

    def request(self, method="post", data=None):
        request = getattr(RequestFactory(), method)("/invoices/1/print/", data=data or {})
        request.user = Mock(is_authenticated=True, is_active=True)
        request.user.has_perm.return_value = True
        return request

    def pdf(self, label, pages=1):
        output = io.BytesIO(); canvas = Canvas(output)
        for page in range(pages):
            canvas.drawString(50, 750, label + " page " + str(page + 1)); canvas.showPage()
        canvas.save(); return output.getvalue()

    def test_active_language_ignores_client_submitted_language(self):
        for language, expected in (("en", "en"), ("fr", "fr"), ("fr-ca", "fr"), ("de", "en")):
            with override(language):
                self.assertEqual(views._print_language(), expected)
        request = self.request(data={"language": "en"})
        with override("fr"), patch.object(views, "_invoice", return_value=SimpleNamespace(status="FINALIZED")), \
                patch.object(views, "generate_pdf", return_value=SimpleNamespace(pk=9)) as generate, \
                patch.object(views, "download_pdf", return_value=(None, io.BytesIO(self.pdf("single")))):
            response = views.invoice_print(request, 1)
        generate.assert_called_once_with(1, request.user, language="fr")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("invoicing:download", args=[9]))

    def test_download_is_authenticated_authorized_inline_and_private(self):
        request = self.request("get")
        artifact = SimpleNamespace(invoice_id=1, language="fr")
        with patch.object(views, "require_permission") as permission, \
                patch.object(views, "download_pdf", return_value=(artifact, io.BytesIO(self.pdf("single")))):
            response = views.invoice_download(request, 9)
        permission.assert_called_once_with(request.user, "view_invoice")
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertIn("invoice-1-fr.pdf", response["Content-Disposition"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-")); response.close()

    def test_single_permission_denied_before_generation(self):
        with patch.object(views, "_invoice", side_effect=PermissionDenied), patch.object(views, "generate_pdf") as generate:
            with self.assertRaises(PermissionDenied):
                views.invoice_print(self.request(), 1)
        generate.assert_not_called()

    def test_draft_rejected_without_generation(self):
        with patch.object(views, "_invoice", return_value=SimpleNamespace(status="DRAFT")), \
                patch.object(views, "generate_pdf") as generate, patch.object(views, "render", return_value=HttpResponse(status=409)):
            self.assertEqual(views.invoice_print(self.request(), 1).status_code, 409)
        generate.assert_not_called()

    def test_generation_routes_are_post_only_and_csrf_protected(self):
        for view in (views.invoice_print, views.invoice_bulk_print):
            args = (1,) if view is views.invoice_print else ()
            self.assertEqual(view(self.request("get"), *args).status_code, 405)
            request = self.request()
            self.assertEqual(CsrfViewMiddleware(lambda request: HttpResponse()).process_view(request, view, args, {}).status_code, 403)
            self.assertFalse(getattr(view, "csrf_exempt", False))

    def test_unauthenticated_single_bulk_and_download_redirect_to_login(self):
        for view, args in ((views.invoice_print, (1,)), (views.invoice_bulk_print, ()), (views.invoice_download, (9,))):
            request = self.request(); request.user = SimpleNamespace(is_authenticated=False)
            response = view(request, *args)
            self.assertEqual(response.status_code, 302)

    def test_selection_validation_and_limits(self):
        self.assertEqual(printing.selected_invoice_ids(["2", "1"]), [2, 1])
        for values in ([], ["1", "1"], [True], ["-1"], ["0"], ["bad"], ["9" * 30], list(range(1, 22))):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                printing.selected_invoice_ids(values)

    def test_entire_batch_authorized_before_any_generation(self):
        invoices = [SimpleNamespace(pk=i, request_id=i * 10, status="FINALIZED") for i in (1, 2)]
        with patch.object(printing.Invoice.objects, "filter") as query, \
                patch.object(printing, "authorize", side_effect=[None, PermissionDenied]) as authorize, \
                patch.object(printing, "generate_pdf") as generate:
            query.return_value.only.return_value = invoices
            with self.assertRaises(PermissionDenied):
                printing.prepare_bulk_print([1, 2], Mock(), language="en")
        self.assertEqual(authorize.call_count, 2); generate.assert_not_called()

    def test_missing_or_draft_batch_member_rejects_whole_selection(self):
        for invoices in ([], [SimpleNamespace(pk=1, request_id=10, status="DRAFT")]):
            with patch.object(printing.Invoice.objects, "filter") as query, patch.object(printing, "authorize"), \
                    patch.object(printing, "generate_pdf") as generate:
                query.return_value.only.return_value = invoices
                with self.assertRaises(ValidationError):
                    printing.prepare_bulk_print([1], Mock(), language="en")
                generate.assert_not_called()

    def test_bulk_reuses_source_services_and_checks_every_download(self):
        invoices = [SimpleNamespace(pk=i, request_id=i * 10, status="FINALIZED") for i in (1, 2)]
        sources = [self.pdf("first", 2), self.pdf("second")]
        with patch.object(printing.Invoice.objects, "filter") as query, patch.object(printing, "authorize") as authorize, \
                patch.object(printing, "generate_pdf", side_effect=[SimpleNamespace(pk=8), SimpleNamespace(pk=9)]) as generate, \
                patch.object(printing, "download_pdf", side_effect=[(None, io.BytesIO(data)) for data in sources]) as download:
            query.return_value.only.return_value = invoices
            content = printing.prepare_bulk_print([1, 2], "synthetic-user", language="fr")
        self.assertEqual(authorize.call_count, 2); self.assertEqual(download.call_count, 2)
        self.assertEqual([call.kwargs["language"] for call in generate.call_args_list], ["fr", "fr"])
        pages = PdfReader(io.BytesIO(content)).pages
        self.assertEqual(len(pages), 3)
        for page, label in zip(pages, ("first page 1", "first page 2", "second page 1")):
            self.assertIn(label, page.extract_text())

    def test_bulk_response_uses_active_language_and_inline_headers(self):
        request = self.request(data={"date_from": "2026-01-01", "date_to": "2026-12-31", "language": "en"})
        with override("fr"), patch.object(views, "require_permission"), \
                patch.object(views, "prepare_filtered_print", return_value=self.pdf("combined")) as prepare:
            response = views.invoice_bulk_print(request)
        prepare.assert_called_once_with(request.POST, request.user, language="fr")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("invoices-fr.pdf", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        self.assertIn("no-store", response["Cache-Control"])
        response.close()

    def test_merge_rejects_invalid_and_oversized_documents_safely(self):
        with self.assertRaises(ValidationError) as caught:
            printing.merge_invoice_pdfs([b"not a PDF SECRET"])
        self.assertNotIn("SECRET", str(caught.exception))
        with patch.object(printing, "MAX_PRINT_BYTES", 5), self.assertRaises(ValidationError):
            printing.merge_invoice_pdfs([b"too large"])
        with patch.object(printing, "MAX_PRINT_PAGES", 1), self.assertRaises(ValidationError):
            printing.merge_invoice_pdfs([self.pdf("two pages", 2)])

    def test_bilingual_real_invoice_pdfs_merge_with_page_boundaries(self):
        snapshot = synthetic.AddressOfflineTests().snapshot(); before = deepcopy(snapshot)
        for language, label in (("en", "Invoice"), ("fr", "Facture")):
            merged = printing.merge_invoice_pdfs([render_pdf(snapshot, language), render_pdf(snapshot, language)])
            pages = PdfReader(io.BytesIO(merged)).pages
            self.assertEqual(len(pages), 2)
            self.assertTrue(all(label in page.extract_text() for page in pages))
        self.assertEqual(snapshot, before)

    def test_storage_configuration_and_public_overlap_fail_closed(self):
        root = (Path.cwd() / "local_artifacts" / "invoice-print-path-fixture").resolve()
        for configured in ("", "relative", str(root / "media" / "private")):
            with override_settings(INVOICE_DOCUMENT_ROOT=configured, MEDIA_ROOT=root / "media", STATIC_ROOT=root / "static", STATICFILES_DIRS=[]), \
                    patch.object(Path, "is_dir", return_value=True), \
                    self.assertRaises(ImproperlyConfigured):
                documents._private_root()
        with override_settings(INVOICE_DOCUMENT_ROOT=str(root / "private"), MEDIA_ROOT=root / "media", STATIC_ROOT=root / "static", STATICFILES_DIRS=[]):
            with self.assertRaises(ImproperlyConfigured):
                documents._private_root()
            with patch.object(Path, "is_dir", return_value=True):
                self.assertEqual(documents._private_root(), root / "private")
            with patch.object(Path, "is_symlink", return_value=True), self.assertRaises(ImproperlyConfigured):
                documents._private_root()

    def test_existing_ready_artifact_is_reused_without_new_attempt_or_render(self):
        content = self.pdf("ready"); before = hashlib.sha256(content).hexdigest()
        path = Mock(); path.open.side_effect = lambda *args, **kwargs: io.BytesIO(content)
        artifact = SimpleNamespace(pk=9, rendering_status="READY", file_reference="a" * 32 + ".pdf", checksum=before)
        invoice = Mock(status="FINALIZED")
        with patch.object(documents, "connection", get_autocommit=lambda: True, in_atomic_block=False), \
                patch.object(documents.transaction, "atomic", return_value=nullcontext()), \
                patch.object(documents.Invoice.objects, "select_for_update") as query, \
                patch.object(documents.DocumentArtifact.objects, "filter") as artifacts, \
                patch.object(documents.DocumentArtifact.objects, "create") as create, \
                patch.object(documents, "authorize"), patch.object(documents, "_path", return_value=path), \
                patch.object(documents, "render_pdf") as render:
            query.return_value.get.return_value = invoice
            artifacts.return_value.order_by.return_value = [artifact]
            self.assertIs(documents.generate_pdf(1, Mock(), language="en"), artifact)
        artifacts.assert_called_once_with(invoice=invoice, language="en",
            rendering_version=RENDERER_VERSION, rendering_status="READY")
        render.assert_not_called(); create.assert_not_called(); invoice.save.assert_not_called()
        self.assertEqual(hashlib.sha256(content).hexdigest(), before)
        artifact.checksum = "0" * 64
        with patch.object(documents, "_path", return_value=path), self.assertRaises(ValidationError):
            documents.artifact_bytes(artifact)

    def test_configuration_exception_is_sanitized(self):
        for error in (ImproperlyConfigured("SECRET private path"), OSError("SECRET private path")):
            with patch.object(views, "_invoice", return_value=SimpleNamespace(status="FINALIZED")), \
                    patch.object(views, "generate_pdf", side_effect=error), \
                    patch.object(views, "render", return_value=HttpResponse(status=409)) as render:
                self.assertEqual(views.invoice_print(self.request(), 1).status_code, 409)
            self.assertNotIn("SECRET", str(render.call_args.args[2]))

    def test_render_failure_records_only_append_only_artifact_metadata(self):
        invoice = Mock(status="FINALIZED")
        with patch.object(documents, "connection", get_autocommit=lambda: True, in_atomic_block=False), \
                patch.object(documents.transaction, "atomic", return_value=nullcontext()), \
                patch.object(documents.Invoice.objects, "select_for_update") as query, \
                patch.object(documents.DocumentArtifact.objects, "filter") as artifacts, \
                patch.object(documents.DocumentArtifact.objects, "create") as create, \
                patch.object(documents, "authorize"), patch.object(documents, "_private_root"), \
                patch.object(documents, "_path"), patch.object(documents, "_snapshot", return_value={}), \
                patch.object(documents, "render_pdf", side_effect=RuntimeError("SECRET internal data")):
            query.return_value.get.return_value = invoice
            artifacts.return_value.order_by.return_value = []
            with self.assertRaises(ValidationError) as caught:
                documents.generate_pdf(1, Mock(), language="en")
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(create.call_args.kwargs["rendering_status"], "FAILED")
        self.assertEqual(create.call_args.kwargs["checksum"], hashlib.sha256(b"").hexdigest())
        self.assertNotIn("SECRET", str(create.call_args.kwargs))
        invoice.save.assert_not_called()

    def test_routes_and_print_templates(self):
        self.assertEqual(resolve(reverse("invoicing:print", args=[1])).func, views.invoice_print)
        self.assertEqual(resolve(reverse("invoicing:bulk_print")).func, views.invoice_bulk_print)
        engine = Engine(libraries={"i18n": "django.templatetags.i18n", "static": "django.templatetags.static", "return_note_navigation": "invoicing.templatetags.return_note_navigation"})
        for name in ("list", "detail", "pdf_error"):
            engine.from_string(Path("templates/invoicing/" + name + ".html").read_text(encoding="utf-8"))
        detail = Path("templates/invoicing/detail.html").read_text(encoding="utf-8")
        self.assertIn('target="_blank"', detail); self.assertNotIn('Download English PDF', detail)
        for language, text in (("en", "Print Invoice"), ("fr", "Imprimer la facture")):
            from django.utils.translation import gettext
            with override(language):
                self.assertEqual(gettext("Print Invoice"), text)
