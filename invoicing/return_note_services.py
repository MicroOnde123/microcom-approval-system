"""Internal return valuation only. Never calls a stock operation or renders files."""
import hashlib
import json
import time
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import UUID, uuid4

from django.core import signing
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils.translation import gettext as _

from requests_app.models import Request, StockMovement
from .configuration import business_date
from .models import (CreditAllocation, DocumentSequence, Invoice, InvoiceReturnExclusion, MaterialReturnNote,
                     MaterialReturnNoteAudit, MaterialReturnNoteLine)
from .permissions import authorize_return_note
from .services import database_now
from .words import amount_in_french

SALT = "invoicing.material_return_note.confirmation.v1"
MAX_AGE = 7200
POLICY = "RETURN_CUMULATIVE_HALF_UP_2_V1"
CENT = Decimal("0.01")
MAX_ID = 9223372036854775807


def _invalid():
    return ValidationError(_("The material return note confirmation is invalid, expired or changed. Preview it again."), code="preview_invalid")


def _unsafe():
    return ValidationError(_("The material return note could not be issued safely. Reload and ask an administrator to review the evidence or numbering."), code="outcome_uncertain")


def _ids(values):
    if (not isinstance(values, (list, tuple)) or not values or
            any(type(value) is not int or not 0 < value <= MAX_ID for value in values) or
            len(set(values)) != len(values)):
        raise ValidationError(_("Select distinct complete stock RETURN movements."))
    return sorted(values)


def _inputs(values, reason, series):
    ids = _ids(values)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValidationError(_("Enter a material return note reason of at most 2000 characters."))
    if not isinstance(series, str) or not series.strip() or len(series) > 30:
        raise ValidationError(_("Select a valid material return note numbering series."))
    return ids, reason.strip(), series.strip()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     default=str, ensure_ascii=False).encode()).hexdigest()


def _invoice_id(value):
    if type(value) is not int or not 0 < value <= MAX_ID:
        raise _invalid()
    return value


def _confirmation(value, *, max_age=None):
    # signing.loads assumes a string and can raise AttributeError for arbitrary
    # caller objects. Validate the public input before handing it to the signer.
    if not isinstance(value, str) or not value:
        raise _invalid()
    try:
        payload = signing.loads(value, salt=SALT, max_age=max_age)
    except (signing.BadSignature, TypeError, ValueError):
        raise _invalid()
    if not isinstance(payload, dict):
        raise _invalid()
    return payload


def _outermost():
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValidationError(_("Material return note services require their own outermost transaction."))


def _coordinator(invoice_id):
    _invoice_id(invoice_id)
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_isolation")
        if cursor.fetchone()[0] != "read committed":
            raise ValidationError(_("Material return note issuance requires READ COMMITTED isolation."))
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('microcom.credit:' || %s::text, 0))", [invoice_id])


def _locked(invoice_id, user, *, issue=False):
    # Check object scope before obtaining coordinator/document locks, then again
    # after waiting. Authorization never relies on a caller's permission cache.
    source = Invoice.objects.get(pk=invoice_id)
    authorize_return_note(user, source.request_id, issue=issue, preview=not issue)
    _coordinator(invoice_id)
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    Request.objects.select_for_update().get(pk=invoice.request_id)
    list(MaterialReturnNote.objects.select_for_update().filter(invoice=invoice).order_by("pk"))
    actor = authorize_return_note(user, invoice.request_id, issue=issue, preview=not issue)
    if invoice.status != "FINALIZED":
        raise ValidationError(_("Material return notes require a finalized internal invoice."))
    return invoice, actor


def _exclusive(invoice):
    if CreditAllocation.objects.filter(credit_note__invoice=invoice, released_at__isnull=True).exists():
        raise ValidationError(_("Active credit allocations block material return notes for this invoice. Administrator review is required."))


def _provenance(invoice, movement, line, now):
    """Mirror E-R1 without inferring missing or ambiguous historical associations."""
    try:
        allocation = line.issue_allocation
        out = allocation.out_movement
    except ObjectDoesNotExist:
        raise ValidationError(_("The RETURN movement has ineligible or ambiguous historical provenance. Administrator review is required."))
    returns = list(StockMovement.objects.filter(request_id=invoice.request_id,
                    material_id=line.material_id, movement_type="RETURN").order_by("pk"))
    exclusions = list(allocation.return_exclusions.select_related("return_movement").order_by("pk"))
    items = list(invoice.request.material_items.filter(material_id=line.material_id))
    if (movement.movement_type != "RETURN" or movement.quantity <= 0 or
            movement.request_id != invoice.request_id or movement.material_id != line.material_id or
            not invoice.finalized_at < movement.created_at <= now or movement.created_at < out.created_at or
            InvoiceReturnExclusion.objects.filter(return_movement_id=movement.pk).exists() or
            out.movement_type != "OUT" or out.quantity <= 0 or out.request_id != invoice.request_id or
            out.material_id != line.material_id or len(items) != 1 or items[0].quantity != out.quantity or
            StockMovement.objects.filter(request_id=invoice.request_id, material_id=line.material_id,
                                         movement_type="OUT").count() != 1 or
            any(m.quantity <= 0 or m.created_at < out.created_at for m in returns) or
            sum((m.quantity for m in returns), Decimal(0)) > out.quantity or
            out.quantity != allocation.quantity + sum((e.quantity for e in exclusions), Decimal(0)) or
            allocation.quantity != line.quantity or line.unit_price is None or line.line_total is None or
            line.currency != invoice.currency or
            any(e.return_movement.quantity != e.quantity or e.return_movement.movement_type != "RETURN" or
                e.return_movement.request_id != invoice.request_id or
                e.return_movement.material_id != line.material_id for e in exclusions)):
        raise ValidationError(_("The RETURN movement has ineligible or ambiguous historical provenance. Administrator review is required."))
    return {"out": [out.pk, out.quantity, out.created_at],
            "items": [[i.pk, i.quantity] for i in items],
            "returns": [[m.pk, m.quantity, m.created_at, m.return_operation_token,
                         m.performed_by_id, m.return_reason] for m in returns],
            "exclusions": [[e.pk, e.return_movement_id, e.quantity] for e in exclusions]}


def _calculate(invoice, ids):
    _exclusive(invoice)
    # Revalidate the existing ledger too; database functions remain authoritative.
    with connection.cursor() as cursor:
        cursor.execute("SELECT inv_rn_validate(%s)", [invoice.pk])
    movements = list(StockMovement.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(movements) != len(ids):
        raise ValidationError(_("Select distinct complete stock RETURN movements."))
    if MaterialReturnNoteLine.objects.filter(return_movement_id__in=ids).exists():
        raise ValidationError(_("A selected RETURN movement has already been documented."))
    lines = {line.material_id: line for line in invoice.lines.select_related(
        "issue_allocation__out_movement").order_by("position", "pk")}
    now = database_now()
    quantities, values, result, evidence = {}, {}, [], []
    with localcontext() as context:
        context.prec = 60
        for movement in movements:
            line = lines.get(movement.material_id)
            if line is None:
                raise ValidationError(_("The RETURN movement has ineligible or ambiguous historical provenance. Administrator review is required."))
            source = _provenance(invoice, movement, line, now)
            allocation = line.issue_allocation
            if allocation.pk not in quantities:
                previous = list(MaterialReturnNoteLine.objects.filter(issue_allocation=allocation))
                quantities[allocation.pk] = sum((a.quantity for a in previous), Decimal(0))
                values[allocation.pk] = sum((a.line_total for a in previous), Decimal(0))
            quantity = quantities[allocation.pk] + movement.quantity
            amount = min(line.line_total, (quantity * line.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)) - values[allocation.pk]
            if quantity > allocation.quantity or amount < 0 or values[allocation.pk] + amount > line.line_total:
                raise ValidationError(_("The selected returns exceed the original invoice quantity or value."))
            quantities[allocation.pk], values[allocation.pk] = quantity, values[allocation.pk] + amount
            result.append({"return_movement_id": movement.pk, "issue_allocation_id": allocation.pk,
                "quantity": str(movement.quantity), "unit_price_snapshot": str(line.unit_price),
                "line_total": str(amount.quantize(CENT)), "material_code_snapshot": line.material_code_snapshot,
                "description_snapshot": line.description_snapshot, "unit_snapshot": line.unit_snapshot})
            evidence.append(source)
        total = sum((Decimal(row["line_total"]) for row in result), Decimal("0.00"))
        prior = list(invoice.material_return_notes.order_by("finalized_at", "pk").values())
        cumulative = sum((n["total"] for n in prior), Decimal("0.00")) + total
        if cumulative > invoice.total:
            raise ValidationError(_("The selected returns exceed the original invoice quantity or value."))
        state = {"invoice": list(Invoice.objects.filter(pk=invoice.pk).values()),
                 "invoice_lines": list(invoice.lines.order_by("pk").values()),
                 "prior_notes": prior, "prior_lines": list(MaterialReturnNoteLine.objects.filter(
                     note__invoice=invoice).order_by("pk").values()), "provenance": evidence}
        return {"lines": result, "total": str(total), "currency": invoice.currency,
                "cumulative_returned_value": str(cumulative),
                "adjusted_net_value": str(invoice.total - cumulative),
                "original_invoice_snapshot": _original(invoice), "state_digest": _digest(state),
                "business_date": business_date(now, invoice.business_timezone).isoformat()}


def _original(invoice):
    return {"version": 1, "number": invoice.number, "issue_date": invoice.issue_date.isoformat(),
            "total": str(invoice.total), "currency": invoice.currency,
            "request_reference": invoice.request_reference_snapshot, "snapshot_version": invoice.snapshot_version,
            "rounding_policy": invoice.rounding_policy}


def eligible_return_movements(invoice_id, user):
    """Authorized candidates with translated exclusion reasons, no reservations."""
    _invoice_id(invoice_id)
    _outermost()
    try:
        with transaction.atomic(durable=True):
            invoice, _actor = _locked(invoice_id, user)
            result = []
            for movement in StockMovement.objects.filter(request_id=invoice.request_id,
                    movement_type="RETURN").order_by("pk"):
                try:
                    with transaction.atomic():
                        _calculate(invoice, [movement.pk])
                    error = None
                except ValidationError as exc:
                    error = exc.messages[0]
                result.append({"return_movement_id": movement.pk, "eligible": error is None, "reason": error})
            return result
    except DatabaseError as error:
        # An invalid existing ledger aborts the complete listing; it must not
        # return partially assessed candidates or expose a raw SQL exception.
        raise _unsafe() from error


def preview_material_return_note(invoice_id, user, *, return_movement_ids, reason, series="MAIN"):
    _invoice_id(invoice_id)
    _outermost()
    ids, reason, series = _inputs(return_movement_ids, reason, series)
    try:
        with transaction.atomic(durable=True):
            invoice, actor = _locked(invoice_id, user)
            preview = _calculate(invoice, ids)
            token = str(uuid4())
            binding = {"version": 1, "actor": actor.pk, "invoice": invoice.pk, "ids": ids,
                       "reason": reason, "series": series, "issuance_token": token,
                       "preview_digest": _digest(preview)}
            return {**preview, "company_snapshot": invoice.company_snapshot,
                    "succursale_snapshot": invoice.succursale_snapshot, "branding_snapshot": invoice.branding_snapshot,
                    "issuance_token": token, "confirmation": signing.dumps(binding, salt=SALT)}
    except DatabaseError as error:
        raise _unsafe() from error


def _issue(invoice_id, user, ids, reason, series, token, confirmation):
    with transaction.atomic(durable=True):
        invoice, actor = _locked(invoice_id, user, issue=True)
        binding = _confirmation(confirmation)
        expected = {"version": 1, "actor": actor.pk, "invoice": invoice.pk, "ids": ids,
                    "reason": reason, "series": series, "issuance_token": token}
        if any(binding.get(k) != v for k, v in expected.items()):
            raise _invalid()
        existing = MaterialReturnNote.objects.filter(issuance_operation_token=token).select_related("operation").first()
        payload = {**binding, "confirmation_digest": _digest(confirmation)}
        if existing:
            if (existing.status != "FINALIZED" or existing.invoice_id != invoice.pk or
                    existing.created_by_id != actor.pk or existing.operation.payload != payload):
                raise _invalid()
            return existing
        _confirmation(confirmation, max_age=MAX_AGE)
        _exclusive(invoice)
        operation = MaterialReturnNoteAudit.objects.create(invoice=invoice, actor=actor, reason=reason, payload=payload)
        preview = _calculate(invoice, ids)
        if binding.get("preview_digest") != _digest(preview):
            raise _invalid()
        note = MaterialReturnNote.objects.create(invoice=invoice, operation=operation, created_by=actor,
                    currency=invoice.currency, business_timezone=invoice.business_timezone,
                    issuance_operation_token=token)
        # INSERT guards stamp immutable DB time; retain that exact identity on
        # the subsequent finalization UPDATE rather than Django's local time.
        note.refresh_from_db()
        for row in preview["lines"]:
            MaterialReturnNoteLine.objects.create(note=note, **row)
        # Numbering is the last lock scope. No sequence is auto-created/attested.
        day = business_date(database_now(), invoice.business_timezone)
        try:
            sequence = DocumentSequence.objects.select_for_update().get(document_type="RETURN_NOTE", year=day.year, series=series)
        except DocumentSequence.DoesNotExist:
            raise ValidationError(_("An administrator must configure and verify the material return note sequence for this business year and series."))
        sequence.full_clean()
        if not sequence.is_verified:
            raise ValidationError(_("The material return note numbering sequence requires administrator verification."))
        authorize_return_note(user, invoice.request_id, issue=True)
        _confirmation(confirmation, max_age=MAX_AGE)
        moment = database_now()
        day = business_date(moment, invoice.business_timezone)
        if day.isoformat() != preview["business_date"] or day.year != sequence.year:
            raise _invalid()
        counter = sequence.next_counter
        if counter >= 9223372036854775807:
            raise ValidationError(_("The document sequence has reached its supported limit. Administrator review is required."))
        note.number = sequence.number_format.format(number=counter, year=day.year)
        note.sequence, note.sequence_counter = sequence, counter
        note.company_snapshot, note.succursale_snapshot = invoice.company_snapshot, invoice.succursale_snapshot
        note.branding_snapshot, note.request_reference_snapshot = invoice.branding_snapshot, invoice.request_reference_snapshot
        note.original_invoice_snapshot = preview["original_invoice_snapshot"]
        note.rounding_policy, note.snapshot_version = POLICY, 1
        for field in ("total", "cumulative_returned_value", "adjusted_net_value"):
            setattr(note, field, Decimal(preview[field]))
        note.amount_words_fr = amount_in_french(note.total, invoice.currency)
        note.audit_metadata = {"service_version": 1, "payload_digest": _digest(payload),
                               "sequence_snapshot": {f.name: str(getattr(sequence, f.attname))
                                                     for f in sequence._meta.concrete_fields}}
        note.status, note.finalized_by, note.finalized_at, note.issue_date = "FINALIZED", actor, moment, day
        sequence.next_counter = counter + 1
        sequence.save(update_fields=["next_counter"])
        note.save()
        note.refresh_from_db()
        return note


def issue_material_return_note(invoice_id, user, *, return_movement_ids, reason, series="MAIN",
                               issuance_token, confirmation):
    _invoice_id(invoice_id)
    if not isinstance(confirmation, str) or not confirmation:
        raise _invalid()
    _outermost()
    ids, reason, series = _inputs(return_movement_ids, reason, series)
    try:
        token = str(UUID(str(issuance_token)))
    except (ValueError, TypeError, AttributeError):
        raise _invalid()
    for attempt in range(3):
        try:
            return _issue(invoice_id, user, ids, reason, series, token, confirmation)
        except DatabaseError as error:
            code = getattr(error.__cause__, "pgcode", None) or getattr(error.__cause__, "sqlstate", None)
            if code not in {"40P01", "40001"} or attempt == 2:
                raise _unsafe() from error
            time.sleep(0.025 * (attempt + 1))


def get_material_return_note(note_id, user):
    _invoice_id(note_id)
    note = MaterialReturnNote.objects.select_related("invoice").get(pk=note_id, status="FINALIZED")
    authorize_return_note(user, note.invoice.request_id)
    return note
