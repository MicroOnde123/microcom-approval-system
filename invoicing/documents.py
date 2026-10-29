"""Private, append-only PDF attempts, separate from financial finalization."""
import hashlib
import io
import os
from pathlib import Path
import re
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import connection, transaction
from django.utils.translation import gettext as _

from .models import DocumentArtifact, Invoice
from .permissions import authorize
from .pdf import RENDERER_VERSION, render_pdf

MAX_PDF_BYTES = 25 * 1024 * 1024
_REFERENCE = re.compile(r"[0-9a-f]{32}\.pdf\Z")


def _private_root():
    configured = getattr(settings, "INVOICE_DOCUMENT_ROOT", None)
    if not configured or not Path(configured).is_absolute():
        raise ImproperlyConfigured("Configure an absolute private INVOICE_DOCUMENT_ROOT outside public media/static paths.")
    raw = Path(configured)
    if any(p.is_symlink() or p.is_junction() for p in (raw, *raw.parents)):
        raise ImproperlyConfigured("Invoice storage cannot use links or junctions.")
    root = raw.resolve()
    if not root.is_dir():
        raise ImproperlyConfigured("An operator must create and secure the private invoice storage directory before PDF generation.")
    public = [getattr(settings, key, None) for key in ("MEDIA_ROOT", "STATIC_ROOT")]
    public.extend(getattr(settings, "STATICFILES_DIRS", []))
    for entry in public:
        entry = entry[1] if isinstance(entry, (list, tuple)) else entry
        if entry:
            path = Path(entry).resolve()
            if root == path or path in root.parents or root in path.parents:
                raise ImproperlyConfigured("Invoice storage must be separate from public media/static paths.")
    return root


def _path(reference):
    if not _REFERENCE.fullmatch(reference):
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    path = _private_root() / reference
    if path.is_symlink() or path.is_junction():
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return path


def artifact_bytes(artifact):
    """Internal only: callers must perform object authorization first."""
    if artifact.rendering_status != "READY":
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    try:
        path = _path(artifact.file_reference)
        with path.open("rb") as stream:
            content = stream.read(MAX_PDF_BYTES + 1)
    except OSError:
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again.")) from None
    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-") or hashlib.sha256(content).hexdigest() != artifact.checksum:
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return content


def _snapshot(invoice):
    """Detach values, without following mutable company/material/user relations."""
    company, branch, brand = invoice.company_snapshot, invoice.succursale_snapshot, invoice.branding_snapshot
    valid = (invoice.status == "FINALIZED" and invoice.snapshot_version == 1 and invoice.number and invoice.issue_date
             and invoice.total is not None and invoice.currency in {"USD", "CDF", "EUR"}
             and invoice.amount_words_fr and isinstance(company, dict) and isinstance(branch, dict)
             and all(isinstance(company.get(k), str) and company[k].strip() for k in ("company_name", "company_address", "contact_details"))
             and all(isinstance(branch.get(k), str) and branch[k].strip() for k in ("code", "name"))
             and invoice.request_reference_snapshot and isinstance(brand, dict) and brand.get("version") == 1
             and brand.get("strategy") in {"embedded-content", "no-logo"})
    if not valid:
        raise ValidationError(_("The finalized invoice snapshot is incomplete. Administrator review is required."))
    if brand["strategy"] == "embedded-content" and not all(brand.get(k) for k in ("content_base64", "sha256", "content_type")):
        raise ValidationError(_("The frozen company logo is incomplete or damaged. Administrator review is required."))
    lines = list(invoice.lines.order_by("position", "pk"))
    if not lines or any(line.unit_price is None or line.line_total is None or line.currency != invoice.currency for line in lines):
        raise ValidationError(_("The finalized invoice snapshot is incomplete. Administrator review is required."))
    return {"company":company, "branch":branch, "branding":brand, "number":invoice.number,
            "issue_date":invoice.issue_date.isoformat(), "request_reference":invoice.request_reference_snapshot,
            "total":format(invoice.total, ".2f"), "currency":invoice.currency, "amount_words_fr":invoice.amount_words_fr,
            "note":invoice.audit_metadata.get("note", ""), "lines":[{
                "code":line.material_code_snapshot, "description":line.description_snapshot, "unit":line.unit_snapshot,
                "quantity":format(line.quantity, ".2f"), "price":format(line.unit_price, ".4f"),
                "total":format(line.line_total, ".2f")} for line in lines]}


def generate_pdf(invoice_id, user, *, language):
    # Refuse invocation inside finalization, ATOMIC_REQUESTS, or any outer transaction.
    if not connection.get_autocommit() or connection.in_atomic_block:
        raise ValidationError(_("Generate the PDF only after invoice finalization has committed."))
    if language not in {"en", "fr"}:
        raise ValidationError(_("Choose English or French for the PDF."))
    failure = None
    with transaction.atomic(durable=True):
        invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
        authorize(user, "view_invoice", invoice.request_id)
        if invoice.status != "FINALIZED":
            raise ValidationError(_("Only finalized invoices have PDFs."))
        # Invoice lock serializes renditions across processes, including failed retries.
        for existing in DocumentArtifact.objects.filter(invoice=invoice, language=language,
                rendering_version=RENDERER_VERSION, rendering_status="READY").order_by("-pk"):
            try:
                artifact_bytes(existing)
                return existing
            except ValidationError:
                continue
        root = _private_root()  # Fail configuration before recording an attempt.
        reference = uuid4().hex + ".pdf"
        path = _path(reference)
        content = b""
        created = False
        try:
            content = render_pdf(_snapshot(invoice), language)
            if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
                raise ValueError("Invalid renderer output")
            root.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                created = True
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as error:
            # No error details/paths/secrets in user-facing messages or metadata.
            if created:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # A private orphan is never downloadable without a READY row.
                    # Filesystem recovery must not prevent recording FAILED.
                    pass
            failure = error if isinstance(error, ValidationError) else ValidationError(_("PDF generation failed. Retry rendering; the finalized invoice is unchanged."))
        artifact = DocumentArtifact.objects.create(invoice=invoice, document_type="INVOICE", language=language,
            rendering_version=RENDERER_VERSION, file_reference=reference,
            checksum=hashlib.sha256(content if failure is None else b"").hexdigest(),
            rendering_status="FAILED" if failure else "READY", created_by=user)
    if failure:
        raise failure
    return artifact


def download_pdf(artifact_id, user):
    artifact = DocumentArtifact.objects.select_related("invoice").get(pk=artifact_id, document_type="INVOICE")
    if artifact.invoice:
        authorize(user, "view_invoice", artifact.invoice.request_id)
    if not artifact.invoice or artifact.invoice.status != "FINALIZED":
        raise ValidationError(_("Only finalized invoices have PDFs."))
    return artifact, io.BytesIO(artifact_bytes(artifact))
