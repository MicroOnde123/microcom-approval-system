"""Private append-only return-note renditions, independent of issuance."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import errno
import hashlib
import io
import os
import re
from uuid import uuid4

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import DatabaseError, InterfaceError, OperationalError, connection, transaction
from django.utils.translation import gettext as _

from .documents import _private_root, MAX_PDF_BYTES
from .models import MaterialReturnNote, MaterialReturnNoteArtifact
from .permissions import authorize_return_note
from .return_note_access import require_ui
from .return_note_services import get_material_return_note
from .return_note_pdf import RENDERER_VERSION, render_pdf
from .return_note_recovery import pdf_error

_REFERENCE = re.compile(r"[0-9a-f]{32}\.pdf\Z")


def _temporary(error):
    if isinstance(error, (OperationalError, InterfaceError)):
        cause = error.__cause__
        code = getattr(cause, "pgcode", None) or getattr(cause, "sqlstate", None)
        # Authentication/configuration failures also use OperationalError.
        # Only positively identified connection/interruption states are retryable.
        return bool(code and (code.startswith("08") or code in {"40001", "40P01", "55P03", "57P01", "57014"}))
    return (isinstance(error, (TimeoutError, BlockingIOError)) or
            isinstance(error, OSError) and error.errno in {errno.EAGAIN, errno.EBUSY, errno.ETIMEDOUT, errno.EINTR})


def _root():
    root = _private_root() / "return-notes"
    if root.is_symlink() or root.is_junction():
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return root


def _path(reference):
    if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    path = _root() / reference
    if path.is_symlink() or path.is_junction():
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."))
    return path


def _artifact_bytes(artifact):
    """Internal only: public callers authorize the owner before opening bytes."""
    if artifact.rendering_status != "READY":
        raise pdf_error()
    try:
        with _path(artifact.file_reference).open("rb") as stream:
            content = stream.read(MAX_PDF_BYTES + 1)
    except OSError as error:
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."),
                              code="pdf_transient" if isinstance(error, FileNotFoundError) or _temporary(error) else "pdf_review_required") from None
    if (len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-") or
            hashlib.sha256(content).hexdigest() != artifact.checksum):
        raise ValidationError(_("The private PDF is unavailable or damaged. Generate it again."), code="pdf_transient")
    return content


def _snapshot(note):
    """Detach issued evidence only; no live material/company lookups or pricing."""
    company, branch, brand, original = note.company_snapshot, note.succursale_snapshot, note.branding_snapshot, note.original_invoice_snapshot
    valid = (note.status == "FINALIZED" and note.snapshot_version == 1 and
        note.rounding_policy == "RETURN_CUMULATIVE_HALF_UP_2_V1" and note.number and note.issue_date and
        note.amount_words_fr and note.request_reference_snapshot and note.currency in {"USD", "CDF", "EUR"} and
        isinstance(company, dict) and isinstance(branch, dict) and isinstance(brand, dict) and isinstance(original, dict) and
        all(isinstance(company.get(k), str) and company[k].strip() for k in ("company_name", "company_address", "contact_details")) and
        all(isinstance(branch.get(k), str) and branch[k].strip() for k in ("code", "name")) and
        original.get("version") == 1 and original.get("currency") == note.currency and
        original.get("number") and original.get("issue_date") and original.get("total") is not None and
        original.get("request_reference") == note.request_reference_snapshot and brand.get("version") == 1 and
        brand.get("strategy") in {"embedded-content", "no-logo"})
    if not valid:
        raise ValidationError(_("The finalized material return note snapshot is incomplete. Administrator review is required."))
    lines = list(note.lines.order_by("pk"))
    if not lines:
        raise ValidationError(_("The finalized material return note snapshot is incomplete. Administrator review is required."))
    try:
        amounts = [note.total, note.cumulative_returned_value, note.adjusted_net_value, Decimal(original["total"])]
        if any(not Decimal(value).is_finite() or Decimal(value) < 0 for value in amounts):
            raise ValueError
        for line in lines:
            if (not line.quantity.is_finite() or line.quantity <= 0 or not line.unit_price_snapshot.is_finite() or
                    line.unit_price_snapshot < 0 or not line.line_total.is_finite() or line.line_total < 0):
                raise ValueError
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise ValidationError(_("The finalized material return note snapshot is incomplete. Administrator review is required.")) from None
    # Formatting only. Monetary calculations remain exclusively in E-R2/E-R1.
    return deepcopy({"company": company, "branch": branch, "branding": brand,
        "number": note.number, "issue_date": note.issue_date.isoformat(),
        "request_reference": note.request_reference_snapshot, "original": original,
        "total": format(note.total, ".2f"), "currency": note.currency, "amount_words_fr": note.amount_words_fr,
        "cumulative_returned_value": format(note.cumulative_returned_value, ".2f"),
        "adjusted_net_value": format(note.adjusted_net_value, ".2f"), "reason": note.operation.reason,
        "lines": [{"movement": line.return_movement_id, "code": line.material_code_snapshot,
            "description": line.description_snapshot, "unit": line.unit_snapshot, "quantity": format(line.quantity, ".2f"),
            "price": format(line.unit_price_snapshot, ".4f"), "total": format(line.line_total, ".2f")} for line in lines]})


def _generate_pdf(note_id, user, *, language):
    require_ui()
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValidationError(_("Generate the PDF only after material return note issuance has committed."))
    if language not in {"en", "fr"}:
        raise ValidationError(_("Choose English or French for the PDF."))
    note = get_material_return_note(note_id, user)
    authorize_return_note(user, note.invoice.request_id, document=True)
    failure = None
    with transaction.atomic(durable=True):
        # Per-note serialization, separate from the financial issuance protocol.
        MaterialReturnNote.objects.select_for_update().get(pk=note_id, status="FINALIZED")
        note = get_material_return_note(note_id, user)
        actor = authorize_return_note(user, note.invoice.request_id, document=True)
        for existing in MaterialReturnNoteArtifact.objects.filter(note_id=note_id, language=language,
                rendering_version=RENDERER_VERSION, rendering_status="READY").order_by("-pk"):
            try:
                _artifact_bytes(existing)
                return existing
            except ValidationError:
                continue
        root = _root()
        reference = uuid4().hex + ".pdf"
        path = _path(reference)
        content = b""
        try:
            content = render_pdf(_snapshot(note), language)
            if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
                raise ValueError("Invalid renderer output")
            root.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as error:
            # Preserve FAILED attempts. A partial/orphan private file is never
            # downloadable without a matching READY row; no cleanup fallback.
            failure = pdf_error(transient=_temporary(error))
        artifact = MaterialReturnNoteArtifact.objects.create(note=note, language=language,
            rendering_version=RENDERER_VERSION, file_reference=reference, created_by=actor,
            checksum=hashlib.sha256(b"" if failure else content).hexdigest(),
            rendering_status="FAILED" if failure else "READY")
    if failure:
        raise failure
    return artifact


def generate_pdf(note_id, user, *, language):
    try:
        return _generate_pdf(note_id, user, language=language)
    except (DatabaseError, OSError, ImproperlyConfigured) as error:
        raise pdf_error(transient=_temporary(error)) from error


def download_pdf(artifact_id, user):
    require_ui()
    try:
        artifact = MaterialReturnNoteArtifact.objects.get(pk=artifact_id)
        note = get_material_return_note(artifact.note_id, user)
        authorize_return_note(user, note.invoice.request_id, document=True)
        return artifact, io.BytesIO(_artifact_bytes(artifact))
    except (DatabaseError, ImproperlyConfigured) as error:
        raise pdf_error(transient=_temporary(error)) from error
