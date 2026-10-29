"""Stock operations. Lock request, then materials in ascending primary-key order."""
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.translation import gettext as _

from inventory.models import Material
from .models import Request, RequestMaterialItem, RequestAuditLog, StockMovement


RETURN_TOKEN_SALT = "requests_app.stock_return"
RETURN_TOKEN_MAX_AGE = 24 * 60 * 60


def validate_material_quantities(request):
    for item in request.material_items.all():
        item._meta.get_field("quantity").clean(item.quantity, item)


def material_return_totals(item):
    """Never infer line associations where legacy movements are ambiguous."""
    req = item.request
    if req.status != "APPROVED" or not req.stock_deducted:
        raise ValidationError(_("Stock has not been issued for this approved request."))
    if req.material_items.filter(material_id=item.material_id).count() != 1:
        raise ValidationError(_("Returns are blocked because this request has repeated material lines. Historical movements cannot be assigned safely."))
    movements = list(StockMovement.objects.filter(
        request_id=item.request_id, material_id=item.material_id,
        movement_type__in=["OUT", "RETURN"],
    ).values_list("movement_type", "quantity"))
    if any(quantity <= 0 for _, quantity in movements):
        raise ValidationError(_("Stock movement history is inconsistent. A stock administrator must review it before a return."))
    issued = sum((q for kind, q in movements if kind == "OUT"), Decimal("0"))
    returned = sum((q for kind, q in movements if kind == "RETURN"), Decimal("0"))
    if issued <= 0 or issued != item.quantity or returned > issued:
        raise ValidationError(_("Stock movement history is inconsistent. A stock administrator must review it before a return."))
    return {"issued_quantity": issued, "returned_quantity": returned,
            "remaining_quantity": issued - returned}


@transaction.atomic
def return_material_stock(item_id, user, quantity, reason, signed_token):
    if not user.is_authenticated or not (user.is_superuser or user.can_manage_stock):
        raise PermissionDenied(_("You are not allowed to return stock."))
    try:
        payload = signing.loads(signed_token, salt=RETURN_TOKEN_SALT, max_age=RETURN_TOKEN_MAX_AGE)
        operation_token = UUID(payload["operation"])
        if payload["item"] != item_id or payload["user"] != user.pk:
            raise ValueError
    except (signing.BadSignature, KeyError, ValueError, TypeError):
        raise ValidationError(_("This return form has expired or is invalid. Open a new return form."))

    request_id = RequestMaterialItem.objects.values_list("request_id", flat=True).get(pk=item_id)
    req = Request.objects.select_for_update().get(pk=request_id)
    item = RequestMaterialItem.objects.select_for_update().get(pk=item_id, request_id=req.pk)
    item.request = req
    if req.status != "APPROVED" or not req.stock_deducted:
        raise ValidationError(_("Stock has not been issued for this approved request."))
    existing = StockMovement.objects.filter(return_operation_token=operation_token).first()
    if existing:
        if (existing.request_id != req.pk or existing.material_id != item.material_id
                or existing.performed_by_id != user.pk or existing.movement_type != "RETURN"):
            raise ValidationError(_("This return form has expired or is invalid. Open a new return form."))
        return existing, False

    quantity = item._meta.get_field("quantity").clean(quantity, item)
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError(_("A return reason is required."))
    material = Material.objects.select_for_update().get(pk=item.material_id)
    totals = material_return_totals(item)
    if quantity > totals["remaining_quantity"]:
        raise ValidationError(_("Only %(quantity)s %(unit)s remain available to return.") % {
            "quantity": totals["remaining_quantity"], "unit": material.unit or ""})
    material.stock_quantity += quantity
    material._meta.get_field("stock_quantity").clean(material.stock_quantity, material)
    material.save(update_fields=["stock_quantity"])
    movement = StockMovement.objects.create(
        material=material, request=req, quantity=quantity, movement_type="RETURN",
        performed_by=user, note=_("Material returned to stock."), return_reason=reason,
        return_operation_token=operation_token,
    )
    RequestAuditLog.objects.create(
        request=req, action="STOCK_RETURNED", performed_by=user,
        comment=_("Returned %(quantity)s %(unit)s of %(material)s to stock. Reason: %(reason)s") % {
            "quantity": quantity, "unit": material.unit or "",
            "material": material.name, "reason": reason},
    )
    return movement, True


@transaction.atomic
def deduct_material_stock(request, user=None):
    # The passed instance may be stale after a previous successful approval.
    req = Request.objects.select_for_update().get(pk=request.pk)
    request.stock_deducted = req.stock_deducted
    if req.stock_deducted or not req.request_type.requires_materials:
        return
    items = list(req.material_items.order_by("material_id", "pk"))
    required = defaultdict(lambda: Decimal("0"))
    for item in items:
        item._meta.get_field("quantity").clean(item.quantity, item)
        required[item.material_id] += item.quantity
    materials = {m.pk: m for m in Material.objects.select_for_update().filter(
        pk__in=required).order_by("pk")}
    for material_id, quantity in required.items():
        material = materials[material_id]
        if quantity > material.stock_quantity:
            raise ValidationError(
                _("Insufficient stock for %(material)s. Available: %(available)s %(unit)s, requested: %(quantity)s %(unit)s.")
                % {"material": material.name, "available": material.stock_quantity,
                   "unit": material.unit or "", "quantity": quantity})
    for material_id, quantity in required.items():
        material = materials[material_id]
        material.stock_quantity -= quantity
        material.save(update_fields=["stock_quantity"])
    for item in items:
        StockMovement.objects.create(
            material=materials[item.material_id], request=req, quantity=item.quantity,
            movement_type="OUT", performed_by=user,
            note=_("Stock deducted after approval of request %(number)s.") % {"number": req.request_number})
    req.stock_deducted = True
    req.save(update_fields=["stock_deducted"])
    request.stock_deducted = True
