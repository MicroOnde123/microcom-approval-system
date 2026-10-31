"""Append-only operational outcomes and nonfinancial receipts; no inventory writes."""
import hashlib
import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils.translation import gettext as _

from .models import (Request, RequestAuditLog, StockMovement, ReturnReceipt,
    ReturnReceiptLine, MaterialReconciliation, MaterialReconciliationLine,
    MaterialReconciliationReturnLink)
from .stock_services import material_return_totals

OUTCOMES = ("CLIENT", "MICROCOM", "RETAINED", "RETURNED")
MAX_COUNTER = 9223372036854775807


def authorize(user):
    actor = get_user_model().objects.filter(pk=getattr(user, "pk", None), is_active=True).first()
    if not (getattr(user, "is_authenticated", False) and actor and
            (actor.is_superuser or actor.can_manage_stock)):
        raise PermissionDenied(_("Only authorized stock personnel may manage material outcomes and return receipts."))
    return actor


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def token_value(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError(_("Invalid operation token. Reload the form.")) from None


def quantity(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal("99999999.99") or result != result.quantize(Decimal(".01")):
            raise ValueError
        return result
    except (ValueError, InvalidOperation, TypeError):
        raise ValidationError(_("Enter nonnegative quantities with at most two decimal places.")) from None


def _request(pk):
    req = Request.objects.select_for_update().select_related("request_type", "submitted_by").get(pk=pk)
    if req.status != "APPROVED" or not req.stock_deducted or not req.request_type.requires_materials:
        raise ValidationError(_("Material outcomes require an approved request with confirmed stock deduction."))
    return req


def _items(req):
    items = list(req.material_items.select_related("material").order_by("pk"))
    if not items:
        raise ValidationError(_("No issued material lines are available."))
    for item in items:
        material_return_totals(item)
    return items


def _replay(record, actor, signature):
    field = "issued_by_id" if isinstance(record, ReturnReceipt) else "recorded_by_id"
    if getattr(record, field) != actor.pk or record.payload_digest != signature:
        raise ValidationError(_("This operation token was already used with different details."))
    return record


@transaction.atomic
def issue_receipt(request_id, user, movement_ids, token):
    actor = authorize(user)
    token = token_value(token)
    if not isinstance(movement_ids, (list, tuple)) or not movement_ids or any(type(x) is not int or x <= 0 for x in movement_ids) or len(set(movement_ids)) != len(movement_ids):
        raise ValidationError(_("Select distinct recorded RETURN movements."))
    ids = sorted(movement_ids)
    signature = digest([request_id, ids])
    req = _request(request_id)
    actor = authorize(user)
    existing = ReturnReceipt.objects.filter(token=token).first()
    if existing:
        return _replay(existing, actor, signature)
    items = {item.material_id: item for item in _items(req)}
    movements = list(StockMovement.objects.select_for_update(of=("self",)).filter(pk__in=ids).select_related("performed_by").order_by("pk"))
    if len(movements) != len(ids) or ReturnReceiptLine.objects.filter(movement_id__in=ids).exists():
        raise ValidationError(_("A selected return is unavailable or already has a receipt. Open receipt history."))
    snapshots = []
    for movement in movements:
        if movement.request_id != req.pk or movement.movement_type != "RETURN" or movement.quantity <= 0 or movement.material_id not in items:
            raise ValidationError(_("The recorded return evidence is inconsistent. Administrator review is required."))
        item = items[movement.material_id]
        out = list(StockMovement.objects.filter(request=req, material_id=item.material_id, movement_type="OUT"))
        if any(movement.created_at < issued.created_at for issued in out):
            raise ValidationError(_("The recorded return evidence is inconsistent. Administrator review is required."))
        snapshots.append({"movement": movement.pk, "item": item.pk, "material": item.material.name,
            "code": item.material.code, "unit": item.material.unit or "", "quantity": str(movement.quantity),
            "returned_at": movement.created_at.isoformat(), "stock_employee": movement.performed_by.get_username() if movement.performed_by else None,
            "reason": movement.return_reason})
    with connection.cursor() as cursor:
        cursor.execute("""WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS t), allocation AS (
          INSERT INTO requests_app_returnreceiptsequence (year,last_counter)
          SELECT extract(year FROM t AT TIME ZONE 'Africa/Kinshasa')::integer,1 FROM instant
          ON CONFLICT(year) DO UPDATE SET last_counter=requests_app_returnreceiptsequence.last_counter+1
          WHERE requests_app_returnreceiptsequence.last_counter < %s RETURNING year,last_counter)
          SELECT year,last_counter,t FROM allocation CROSS JOIN instant""", [MAX_COUNTER])
        allocation = cursor.fetchone()
    if not allocation:
        raise ValidationError(_("The return receipt sequence is exhausted. Administrator review is required."))
    year, counter, moment = allocation
    snapshot = {"request": req.request_number, "lines": snapshots, "version": 1}
    receipt = ReturnReceipt.objects.create(request=req, reference=f"RCP/{counter:04d}/{year}", year=year,
        counter=counter, issued_at=moment, issued_by=actor, token=token, payload_digest=signature, snapshot=snapshot)
    for movement, row in zip(movements, snapshots):
        ReturnReceiptLine.objects.create(receipt=receipt, movement=movement, quantity=movement.quantity, snapshot=row)
    RequestAuditLog.objects.create(request=req, action="RETURN_RECEIPT", performed_by=actor, comment=receipt.reference)
    return receipt


@transaction.atomic
def reconcile(request_id, user, *, allocations, expected_revision, reported_by_id, reason, token):
    actor = authorize(user)
    token = token_value(token)
    if type(expected_revision) is not int or expected_revision < 0 or not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ValidationError(_("Enter a reason and a valid reconciliation revision."))
    if not isinstance(allocations, dict) or not allocations:
        raise ValidationError(_("Account for every issued material line."))
    clean = {}
    for item_id, values in allocations.items():
        if type(item_id) is not int or not isinstance(values, dict) or set(values) != set(OUTCOMES):
            raise ValidationError(_("Account for every issued material line."))
        clean[item_id] = {key: quantity(values[key]) for key in OUTCOMES}
    signature = digest([request_id, expected_revision, reported_by_id, reason.strip(),
                        {str(k): {o: str(v) for o,v in row.items()} for k,row in clean.items()}])
    req = _request(request_id)
    actor = authorize(user)
    existing = MaterialReconciliation.objects.filter(token=token).first()
    if existing:
        return _replay(existing, actor, signature)
    # The existing request owner is the reporting technician; stock staff record on their behalf.
    if reported_by_id != req.submitted_by_id:
        raise ValidationError(_("The reporting technician must be the original request owner."))
    previous = req.reconciliations.order_by("-revision").first()
    revision = previous.revision if previous else 0
    if revision != expected_revision:
        raise ValidationError(_("This reconciliation changed. Reload and review the latest revision."))
    items = _items(req)
    if set(clean) != {item.pk for item in items}:
        raise ValidationError(_("Account for every issued material line."))
    for item in items:
        totals = material_return_totals(item)
        row = clean[item.pk]
        if sum(row.values()) != totals["issued_quantity"] or row["RETURNED"] != totals["returned_quantity"]:
            raise ValidationError(_("Outcome quantities must equal issued quantities; returned quantities must match recorded physical returns."))
    record = MaterialReconciliation.objects.create(request=req, previous=previous, revision=revision+1,
        recorded_by=actor, reported_by_id=reported_by_id, reason=reason.strip(), token=token, payload_digest=signature)
    for item in items:
        for outcome, amount in clean[item.pk].items():
            if not amount:
                continue
            line = MaterialReconciliationLine.objects.create(reconciliation=record, item=item, outcome=outcome, quantity=amount,
                snapshot={"material": item.material.name, "code": item.material.code, "unit": item.material.unit or "",
                          "issued_quantity": str(item.quantity)})
            if outcome == "RETURNED":
                for movement in StockMovement.objects.filter(request=req, material_id=item.material_id, movement_type="RETURN").order_by("pk"):
                    if not MaterialReconciliationReturnLink.objects.filter(movement=movement).exists():
                        MaterialReconciliationReturnLink.objects.create(line=line, movement=movement)
    RequestAuditLog.objects.create(request=req, action="RECONCILIATION", performed_by=actor,
        comment=_("Material reconciliation revision %(revision)s.") % {"revision": record.revision})
    return record
