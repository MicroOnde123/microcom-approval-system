"""Real committed synthetic invoices, private PDFs and PostgreSQL concurrency."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import re
from pathlib import Path
from tempfile import mkdtemp
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import close_old_connections, connection, transaction, IntegrityError
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from inventory.models import Material
from requests_app.models import Request, RequestMaterialItem
from requests_app.services import approve_step, submit_request
from .documents import generate_pdf, download_pdf, artifact_bytes, _snapshot, _private_root
from .models import DocumentArtifact, DocumentSequence, Invoice, InvoiceAuditEvent
from .pdf import render_pdf, display_decimal, RENDERER_VERSION
from .pdf_test_tools import pdf_text
from .test_lifecycle import LifecycleFixtures


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class InvoiceDocumentTests(LifecycleFixtures, TransactionTestCase):
    def setUp(self):
        super().setUp()
        # Retain isolated synthetic files for inspection; never use real artifacts.
        root = Path(mkdtemp(prefix="invoice-regression-", dir=Path(settings.MEDIA_ROOT).parent))
        private = root / "private"
        private.mkdir()
        self._storage = override_settings(INVOICE_DOCUMENT_ROOT=private, STAGE1_EVIDENCE_ROOT=root)
        self._storage.enable()
        self.addCleanup(self._storage.disable)

    def make_request(self, quantity=10):
        # PDF examples use an explicitly synthetic human-readable source number.
        # The general stock fixture uses uuid4() as request_number (not as its PK).
        request = Request.objects.create(request_number=f"REQ-SYN{Request.objects.count()+1:03d}",
            submitted_by=self.other, department=self.department, request_type=self.request_type,
            description="Synthetic PDF request")
        item = RequestMaterialItem.objects.create(request=request, material=self.material, quantity=quantity)
        submit_request(request)
        return request, item

    def _post_teardown(self):
        try:
            super()._post_teardown()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE invoicing_finalreference")

    def final_document(self):
        self.material.name = "Câble électrique € & <test>"
        self.material.save()
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        return self.finalize(invoice)

    def financial_state(self):
        return {"source": self.source_snapshot(), "invoice": list(Invoice.objects.values()),
                "sequence": list(DocumentSequence.objects.values()), "audit": list(InvoiceAuditEvent.objects.values())}

    def test_english_french_pdf_contents_checksum_and_frozen_french_words(self):
        invoice = self.final_document()
        before = self.financial_state()
        evidence = Path(settings.STAGE1_EVIDENCE_ROOT)
        for language, title, total, department in (("en", "Invoice", "Total amount payable", "Stock Department"),
                                                   ("fr", "Facture", "Montant total à payer", "Service Stock")):
            with self.subTest(language=language):
                artifact = generate_pdf(invoice.pk, self.user, language=language)
                data = artifact_bytes(artifact)
                text = pdf_text(data)
                for value in (title, total, department, invoice.number, "20.00", "2.00", "10", "USD",
                              "Câble électrique € & <test>", "Nous disons : " + invoice.amount_words_fr,
                              invoice.succursale_snapshot["name"],
                              invoice.request_reference_snapshot, "Synthetic invoice"):
                    self.assertIn(re.sub(r"\s+", "", value), re.sub(r"\s+", "", text))
                self.assertNotIn(invoice.company_snapshot["company_name"], text)
                self.assertEqual(invoice.company_snapshot, before["invoice"][0]["company_snapshot"])
                self.assertEqual(hashlib.sha256(data).hexdigest(), artifact.checksum)
                self.assertEqual(artifact.rendering_version, RENDERER_VERSION)
                self.assertNotIn(b"/Subtype /Image",data)
                self.assertNotIn("2.0000",text)
                self.assertNotIn("10.00",text)
                self.assertEqual(artifact.created_by, self.user)
                (evidence / f"invoice-{language}.pdf").write_bytes(data)
                (evidence / f"invoice-{language}-text.txt").write_text(text, encoding="utf-8")
        self.assertEqual(self.financial_state(), before)

    def test_real_authorized_post_and_private_download(self):
        invoice = self.final_document()
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("invoicing:pdf", args=[invoice.pk,"en"])).status_code,405)
        response = self.client.post(reverse("invoicing:pdf", args=[invoice.pk,"en"]))
        self.assertEqual(response.status_code,302)
        download = self.client.get(response.url)
        data = b"".join(download.streaming_content)
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertTrue({"private", "no-store", "no-cache", "must-revalidate", "max-age=0"}.issubset(
            {part.strip() for part in download["Cache-Control"].split(",")}))
        self.assertEqual(download["Content-Type"],"application/pdf")
        self.assertNotIn(str(settings.INVOICE_DOCUMENT_ROOT),response.url)
        self.assertEqual(self.client.get(reverse("invoicing:download",args=[999999])).status_code,404)

    def test_unauthorized_and_unscoped_users_cannot_generate_or_download(self):
        invoice = self.final_document()
        artifact = generate_pdf(invoice.pk,self.user,language="en")
        self.other.user_permissions.add(Permission.objects.get(content_type__app_label="invoicing",codename="view_invoice"))
        for user in (self.other,):
            with self.assertRaises(PermissionDenied):
                generate_pdf(invoice.pk,user,language="en")
            with self.assertRaises(PermissionDenied):
                download_pdf(artifact.pk,user)
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("invoicing:download",args=[artifact.pk])).status_code,403)
            self.assertEqual(self.client.post(reverse("invoicing:pdf",args=[invoice.pk,"en"])).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("invoicing:download",args=[artifact.pk])).status_code,302)
        self.assertEqual(DocumentArtifact.objects.count(),1)

    def test_live_catalogue_company_branch_and_logo_are_not_read(self):
        invoice = self.final_document()
        frozen = _snapshot(invoice)
        self.material.name = "MUTATED MATERIAL"
        self.material.unit_price = 999
        self.material.currency = "USD"
        self.material.save()
        self.branch.name = "MUTATED BRANCH"
        self.branch.save()
        self.configuration.company_name = "MUTATED COMPANY"
        self.configuration.logo_reference = "images/does-not-exist.png"
        self.configuration.save()
        with patch("django.contrib.staticfiles.finders.find",side_effect=AssertionError("live logo read")):
            real_render = render_pdf
            def check(snapshot,language):
                self.assertEqual(snapshot,frozen)
                return real_render(snapshot,language)
            with patch("invoicing.documents.render_pdf",side_effect=check):
                artifact = generate_pdf(invoice.pk,self.user,language="en")
        text = pdf_text(artifact_bytes(artifact))
        self.assertNotIn("MUTATED",text)
        # The frozen asset remains intact, but the text-only renderer embeds no image.
        self.assertNotIn(b"/Subtype /Image",artifact_bytes(artifact))
        self.assertEqual(hashlib.sha256(base64.b64decode(frozen["branding"]["content_base64"])).hexdigest(),frozen["branding"]["sha256"])

    def test_failed_attempt_is_append_only_retry_changes_no_financial_state(self):
        invoice = self.final_document()
        before = self.financial_state()
        with patch("invoicing.documents.render_pdf",side_effect=RuntimeError("Synthetic failure")):
            with self.assertRaisesMessage(ValidationError,"PDF generation failed"):
                generate_pdf(invoice.pk,self.user,language="en")
        failed = DocumentArtifact.objects.get()
        self.assertEqual(failed.rendering_status,"FAILED")
        with self.assertRaises(ValidationError):
            failed.save()
        with self.assertRaises(ValidationError):
            download_pdf(failed.pk,self.user)
        ready = generate_pdf(invoice.pk,self.user,language="en")
        self.assertNotEqual(ready.pk,failed.pk)
        self.assertEqual(ready.rendering_status,"READY")
        self.assertEqual(self.financial_state(),before)

    def test_duplicate_and_concurrent_generation_reuse_one_ready_file(self):
        invoice = self.final_document()
        before = self.financial_state()
        barrier = Barrier(2)
        def render():
            close_old_connections()
            try:
                user = get_user_model().objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                return generate_pdf(invoice.pk,user,language="fr").pk
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:render(),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(generate_pdf(invoice.pk,self.user,language="fr").pk,results[0])
        self.assertEqual(DocumentArtifact.objects.count(),1)
        self.assertEqual(self.financial_state(),before)

    def test_uncommitted_invocation_is_rejected(self):
        invoice = self.final_document()
        with transaction.atomic(),self.assertRaisesMessage(ValidationError,"after invoice finalization has committed"):
            generate_pdf(invoice.pk,self.user,language="en")
        self.assertFalse(DocumentArtifact.objects.exists())

    def test_drafts_and_invalid_languages_are_rejected_bilingually(self):
        invoice = self.create()
        for language,message in (("en","Only finalized invoices"),("fr","Seules les factures finalisées")):
            with override(language),self.assertRaisesMessage(ValidationError,message):
                generate_pdf(invoice.pk,self.user,language=language)
        with self.assertRaises(ValidationError):
            generate_pdf(invoice.pk,self.user,language="../fr")
        self.assertFalse(DocumentArtifact.objects.exists())

    def test_tampering_or_missing_files_fail_closed_and_retry_recovers(self):
        invoice = self.final_document()
        first = generate_pdf(invoice.pk,self.user,language="en")
        (Path(settings.INVOICE_DOCUMENT_ROOT)/first.file_reference).write_bytes(b"%PDF-tampered")
        with self.assertRaises(ValidationError):
            download_pdf(first.pk,self.user)
        second = generate_pdf(invoice.pk,self.user,language="en")
        self.assertNotEqual(first.pk,second.pk)
        (Path(settings.INVOICE_DOCUMENT_ROOT)/second.file_reference).unlink()
        with self.assertRaises(ValidationError):
            download_pdf(second.pk,self.user)

    def test_public_storage_missing_storage_and_traversal_rejected(self):
        for path in (None, settings.MEDIA_ROOT, Path(settings.MEDIA_ROOT)/"invoices", settings.STATIC_ROOT):
            with override_settings(INVOICE_DOCUMENT_ROOT=path),self.assertRaises(ImproperlyConfigured):
                _private_root()
        invoice = self.final_document()
        artifact = DocumentArtifact.objects.create(invoice=invoice,document_type="INVOICE",language="en",
            rendering_version="synthetic-test",file_reference="../../secret.pdf",checksum="0"*64,
            rendering_status="READY",created_by=self.user)
        with self.assertRaises(ValidationError):
            download_pdf(artifact.pk,self.user)

    def test_incomplete_or_damaged_snapshot_never_falls_back_to_live_assets(self):
        invoice = self.final_document()
        snapshot = _snapshot(invoice)
        snapshot["branding"] = {**snapshot["branding"],"sha256":"0"*64}
        with self.assertRaises(ValidationError):
            render_pdf(snapshot,"fr")
        invoice.company_snapshot = {}
        with self.assertRaises(ValidationError):
            _snapshot(invoice)

    def test_multi_page_long_description_and_special_characters(self):
        self.material.description = ("Équipement réseau — sécurité, cœur, façade, câble € et $ ; " * 170) + "FIN-DESCRIPTION"
        self.material.save()
        invoice = self.final_document()
        for language in ("en","fr"):
            artifact = generate_pdf(invoice.pk,self.user,language=language)
            data = artifact_bytes(artifact)
            text = pdf_text(data)
            self.assertGreater(data.count(b"/Type /Page\n"),1)
            self.assertIn("FIN-DESCRIPTION",text)
            self.assertIn("20.00",text)
            self.assertIn("cœur",text)
            (Path(settings.STAGE1_EVIDENCE_ROOT)/f"invoice-multipage-{language}.pdf").write_bytes(data)

    def test_explicit_frozen_no_logo_and_unsupported_font_characters(self):
        invoice = self.final_document()
        snapshot = _snapshot(invoice)
        snapshot["branding"] = {"version":1,"strategy":"no-logo"}
        data = render_pdf(snapshot,"en")
        self.assertNotIn(b"/Subtype /Image",data)
        snapshot["note"] = "Unsupported \U0001f680"
        with self.assertRaisesMessage(ValidationError,"unsupported by the PDF font"):
            render_pdf(snapshot,"en")

    def test_many_real_lines_repeat_headings_and_retain_all_totals(self):
        request, item = self.make_request(1)
        for index in range(65):
            material = Material.objects.create(category=self.category, code=f"SYN-{index:03d}",
                name=f"Équipement synthétique {index:03d}", unit="pcs", stock_quantity=100)
            RequestMaterialItem.objects.create(request=request,material=material,quantity=1)
        approve_step(request.approvals.get(),self.user,classification="MICROCOM",succursale=self.branch)
        self.req = request
        invoice = self.create()
        self.price(invoice)
        self.verified_sequence()
        invoice = self.finalize(invoice)
        before = self.financial_state()
        artifact = generate_pdf(invoice.pk,self.user,language="fr")
        data = artifact_bytes(artifact)
        text = pdf_text(data)
        self.assertGreater(data.count(b"/Type /Page\n"),1)
        self.assertGreater(text.count("Prix unitaire"),1)
        for index in range(65):
            self.assertIn(f"SYN-{index:03d}",text)
        self.assertIn("132.00",text)
        self.assertEqual(self.financial_state(),before)
        (Path(settings.STAGE1_EVIDENCE_ROOT)/"invoice-many-lines-fr.pdf").write_bytes(data)

    def test_eur_currency_and_stored_words_and_zero_price(self):
        invoice = self.create(currency="EUR")
        self.price(invoice,"0")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        artifact = generate_pdf(invoice.pk,self.user,language="en")
        text = pdf_text(artifact_bytes(artifact))
        self.assertIn("0.00 EUR",text)
        self.assertIn("Nous disons : zéro euro",text)

    def test_storage_failure_is_retryable_without_changing_financial_state(self):
        invoice = self.final_document()
        before = self.financial_state()
        original = Path.open
        def fail_write(path,*args,**kwargs):
            if args and args[0] == "xb":
                raise OSError("Synthetic write failure")
            return original(path,*args,**kwargs)
        with patch.object(Path,"open",fail_write),self.assertRaises(ValidationError):
            generate_pdf(invoice.pk,self.user,language="en")
        self.assertEqual(DocumentArtifact.objects.get().rendering_status,"FAILED")
        ready = generate_pdf(invoice.pk,self.user,language="en")
        self.assertEqual(ready.rendering_status,"READY")
        self.assertEqual(self.financial_state(),before)

    def test_view_permission_is_sufficient_but_is_mandatory_and_post_requires_csrf(self):
        invoice = self.final_document()
        self.user.user_permissions.remove(*Permission.objects.filter(content_type__app_label="invoicing",
            codename__in=["add_invoice","change_invoice","finalize_invoice"]))
        user = get_user_model().objects.get(pk=self.user.pk)
        artifact = generate_pdf(invoice.pk,user,language="en")
        self.assertTrue(download_pdf(artifact.pk,user)[1].read().startswith(b"%PDF-"))
        protected_client = Client(enforce_csrf_checks=True)
        protected_client.force_login(user)
        self.assertEqual(protected_client.post(reverse("invoicing:pdf",args=[invoice.pk,"fr"])).status_code,403)
        self.assertEqual(DocumentArtifact.objects.count(),1)
        self.user.user_permissions.clear()
        user = get_user_model().objects.get(pk=self.user.pk)
        with self.assertRaises(PermissionDenied):
            generate_pdf(invoice.pk,user,language="en")
        with self.assertRaises(PermissionDenied):
            download_pdf(artifact.pk,user)

    def test_display_precision_never_rounds_or_mutates_snapshot_values(self):
        for value,expected in (("10.00","10"),("0.00","0"),("1.50","1.5"),("0.25","0.25")):
            self.assertEqual(display_decimal(value),expected)
        for value,expected in (("2.0000","2.00"),("2.1000","2.10"),("2.1234","2.1234"),("0.0001","0.0001")):
            self.assertEqual(display_decimal(value,minimum_places=2),expected)
        invoice = self.create()
        self.price(invoice,"2.1234")
        self.verified_sequence()
        invoice = self.finalize(invoice)
        before = self.financial_state()
        artifact = generate_pdf(invoice.pk,self.user,language="en")
        self.assertIn("2.1234",pdf_text(artifact_bytes(artifact)))
        self.assertEqual(self.financial_state(),before)

    def test_original_request_number_is_snapshotted_and_displayed_in_both_languages(self):
        original_reference = self.req.request_number
        self.assertRegex(original_reference,r"^REQ-SYN\d{3}$")
        invoice = self.final_document()
        self.assertEqual(invoice.request_reference_snapshot,original_reference)
        self.assertEqual(_snapshot(invoice)["request_reference"],original_reference)
        self.assertNotEqual(original_reference,str(self.req.pk))
        for language,label in (("en","Material request reference"),("fr","Référence de la demande de matériel")):
            artifact = generate_pdf(invoice.pk,self.user,language=language)
            text = pdf_text(artifact_bytes(artifact))
            self.assertIn(label+": "+original_reference,text)
            self.assertNotIn(label+": "+str(self.req.pk)+"\n",text)

    def test_final_reference_is_not_reconstructed_from_changed_live_request(self):
        invoice = self.final_document()
        frozen_reference = invoice.request_reference_snapshot
        # Persisted references are immutable. Prove the guard, then pass a stale
        # in-memory source object to catch accidental live-reference rendering.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Request.objects.filter(pk=self.req.pk).update(request_number="REQ-CHG001")
        self.req.refresh_from_db()
        self.assertEqual(self.req.request_number, frozen_reference)
        self.req.request_number = "REQ-CHG001"
        invoice.refresh_from_db()
        invoice.request = self.req
        self.assertEqual(invoice.request_reference_snapshot,frozen_reference)
        before = self.financial_state()
        for language in ("en","fr"):
            artifact = generate_pdf(invoice.pk,self.user,language=language)
            text = pdf_text(artifact_bytes(artifact))
            self.assertIn(frozen_reference,text)
            self.assertNotIn("REQ-CHG001",text)
        self.assertEqual(self.financial_state(),before)
