"""Authorized, checksum-verified private receipt artifacts. Never restores stock."""
import hashlib
import os
import re
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext as _
from invoicing.documents import _private_root, MAX_PDF_BYTES
from .models import ReturnReceipt, ReturnReceiptArtifact
from .material_outcomes import authorize
from .return_receipt_pdf import render_receipt, RENDERER_VERSION


def _path(reference):
    if not re.fullmatch(r"[0-9a-f]{32}\.pdf", reference):
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    root = _private_root() / "physical-return-receipts"
    path = root / reference
    if root.is_symlink() or root.is_junction() or path.is_symlink() or path.is_junction():
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return path


def read_artifact(artifact, user):
    authorize(user)
    with _path(artifact.file_reference).open("rb") as stream:
        content = stream.read(MAX_PDF_BYTES+1)
    if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-") or hashlib.sha256(content).hexdigest() != artifact.checksum:
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return content


@transaction.atomic
def generate_receipt_pdf(receipt_id, user, language):
    actor = authorize(user)
    if language not in {"en", "fr"}:
        raise ValidationError(_("Choose English or French for the PDF."))
    receipt = ReturnReceipt.objects.select_for_update().get(pk=receipt_id)
    authorize(user)
    for artifact in receipt.artifacts.filter(language=language, renderer_version=RENDERER_VERSION).order_by("-pk"):
        try:
            read_artifact(artifact, user)
            return artifact
        except (OSError, ValidationError):
            pass
    snapshot = dict(receipt.snapshot, reference=receipt.reference)
    content = render_receipt(snapshot, language)
    if not content.startswith(b"%PDF-") or len(content) > MAX_PDF_BYTES:
        raise ValidationError(_("The PDF could not be generated. Return to receipt history and retry."))
    reference = uuid4().hex + ".pdf"
    path = _path(reference)
    path.parent.mkdir(exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    # A failed metadata commit can leave a private orphan; never publish or delete it automatically.
    return ReturnReceiptArtifact.objects.create(receipt=receipt, language=language,
        renderer_version=RENDERER_VERSION, file_reference=reference,
        checksum=hashlib.sha256(content).hexdigest(), created_by=actor)
