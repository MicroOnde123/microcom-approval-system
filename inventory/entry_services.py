"""Central stock receipts. Never links incoming movements to technician requests."""
import hashlib
import json
from uuid import uuid4
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils.translation import gettext as _
from .entry_forms import ReceiptForm, NewMaterialForm
from .models import Material, MaterialReceipt, MaterialReceiptLine, MaterialEntryDraft
from requests_app.models import StockMovement

SALT = "inventory.material_receipt"


def authorize(user):
    if not user.is_authenticated or not user.is_active or not (user.is_superuser or user.can_manage_stock):
        raise PermissionDenied


def new_token(user, mode):
    return signing.dumps({"operation": str(uuid4()), "user": user.pk, "mode": mode}, salt=SALT)


def decode_token(user, mode, token):
    from uuid import UUID
    try:
        payload = signing.loads(token, salt=SALT)
        if payload["user"] != user.pk or payload["mode"] != mode:
            raise ValueError
        return UUID(payload["operation"])
    except (signing.BadSignature, ValueError, TypeError, KeyError):
        raise ValidationError(_("Invalid receipt form. Open a new form."))


def lock_receipt_operation(operation):
    """Serialize draft creation/finalization before either durable row exists.

    Keep the existing operation UUID authoritative. The advisory lock is only a
    PostgreSQL transaction lock, not a second idempotency key or persisted state.
    """
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)",
                           [int.from_bytes(operation.bytes[:8], "big", signed=True)])


@transaction.atomic
def receive_stock(*, user, mode, token, receipt_data, material_id=None, material_data=None, draft_id=None):
    authorize(user)
    operation = decode_token(user, mode, token)
    if mode not in ("new", "existing"):
        raise ValidationError(_("Invalid receipt form. Open a new form."))
    lock_receipt_operation(operation)
    draft = MaterialEntryDraft.objects.select_for_update().filter(operation_token=operation).first()
    if draft:
        if draft.status == MaterialEntryDraft.Status.CANCELLED:
            raise ValidationError(_("This draft was cancelled."))
        if (draft.pk != draft_id or draft.owner_id != user.pk or draft.mode != mode
                or draft.signed_token != token):
            raise ValidationError(_("Resume the saved draft before confirming this receipt."))
    elif draft_id is not None:
        raise ValidationError(_("Draft not found."))
    form = ReceiptForm({**receipt_data, "token": token})
    if not form.is_valid():
        raise ValidationError(form.errors.as_text())
    receipt_data = {k: v for k, v in form.cleaned_data.items() if k != "token"}
    quantity = receipt_data["quantity"]
    payload = {"mode": mode, "receipt": receipt_data, "material_id": material_id, "material": material_data}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    # Unique insert serializes even simultaneous retries before a new material exists.
    receipt, created = MaterialReceipt.objects.get_or_create(operation_token=operation, defaults={
        "reference": "IN-" + operation.hex.upper(), "payload_hash": digest,
        "transaction_type": mode,
        "created_by": user, "received_on": receipt_data.get("received_on"),
        "supplier": receipt_data.get("supplier", ""),
        "delivery_reference": receipt_data.get("delivery_reference", ""), "notes": receipt_data.get("notes", ""),
    })
    receipt = MaterialReceipt.objects.select_for_update().get(pk=receipt.pk)
    if not created:
        if receipt.created_by_id != user.pk or receipt.payload_hash != digest:
            raise ValidationError(_("This receipt form has already been used with different data."))
        return receipt, False
    if mode == "new":
        form = NewMaterialForm(material_data)
        if not form.is_valid():
            raise ValidationError(form.errors.as_text())
        material = form.save(commit=False)
        material.stock_quantity = 0
        material.save()
    else:
        try:
            material = Material.objects.select_for_update().get(pk=material_id)
        except Material.DoesNotExist:
            raise ValidationError(_("Select a valid material."))
    material.stock_quantity += quantity
    material._meta.get_field("stock_quantity").clean(material.stock_quantity, material)
    material.save(update_fields=["stock_quantity"])
    movement = StockMovement.objects.create(material=material, quantity=quantity, movement_type="IN", performed_by=user, note=receipt.reference)
    # Descriptive evidence only: excluded from the existing retry payload/hash.
    snapshot = {
        "version": 1, "name": material.name, "code": material.code, "unit": material.unit,
        "category_name": material.category.name, "category_code": material.category.code,
        "description": material.description, "minimum_stock_level": str(material.minimum_stock_level),
        "unit_price": str(material.unit_price) if material.unit_price is not None else None,
        "currency": material.currency, "is_active": material.is_active,
    }
    MaterialReceiptLine.objects.create(receipt=receipt, material=material, quantity=quantity,
        stock_after=material.stock_quantity, movement=movement, material_snapshot=snapshot)
    return receipt, True


class CategoryCodeConflict(ValidationError):
    pass


@transaction.atomic
def create_category(*, user, data):
    """The unique code is the retry key. Identical retries never create a second row."""
    from .entry_forms import CategoryForm
    from .models import MaterialCategory
    authorize(user)
    form = CategoryForm(data)
    if not form.is_valid():
        raise ValidationError({key: list(errors) for key, errors in form.errors.items()})
    values = form.cleaned_data
    category, created = MaterialCategory.objects.get_or_create(
        code=values["code"], defaults={"name": values["name"], "description": values["description"]})
    if not created and (category.name != values["name"] or category.description != values["description"]):
        raise CategoryCodeConflict({"code": _("A category with this code already exists. Choose a different code.")})
    return category, created
