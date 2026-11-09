"""Authorized catalogue updates; PostgreSQL records old/new values atomically.

Creation prices remain part of material creation. All later price/currency writes
must use this context, including Admin. Stock-only writes require no context.
"""
from contextlib import contextmanager
import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import Material


PRICE_CONFLICT = gettext_lazy("The material price has changed. Reload the page and review the current price before saving.")


def price_state(material):
    return {"material": material.pk,
            "price": format(material.unit_price, ".2f") if material.unit_price is not None else None,
            "currency": material.currency,
            "revision": material.price_changes.order_by("-pk").values_list("pk", flat=True).first()}


def can_change_price(user):
    """Price editing grants no Admin access or additional stock permissions."""
    return bool(user.is_authenticated and user.is_active and
                (user.can_manage_stock or user.has_perm("inventory.change_material")))


def authorize_price(user):
    if not can_change_price(user):
        raise PermissionDenied(_("You do not have permission to change material prices."))


@contextmanager
def price_change_context(user, reason, source):
    authorize_price(user)
    if source == "admin" and not user.has_perm("inventory.change_material"):
        raise PermissionDenied(_("You do not have permission to change material prices."))
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError(_("Enter a reason for the price or currency change."))
    if source not in {"admin", "service"}:
        raise ValidationError(_("Invalid price change source."))
    if not connection.in_atomic_block:
        raise RuntimeError("Price updates require an atomic transaction.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('inventory.price_change', true)")
        previous = cursor.fetchone()[0] or ""
        cursor.execute("SELECT set_config('inventory.price_change', %s, true)",
                       [json.dumps({"user": user.pk, "reason": reason, "source": source})])
    try:
        yield
    finally:
        # A failed SQL statement leaves the transaction unusable until rollback.
        if not connection.needs_rollback:
            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('inventory.price_change', %s, true)", [previous])


@transaction.atomic
def update_price(material_id, user, *, price, currency, reason, expected_state):
    """Fail on stale evidence, including a price changed and subsequently restored."""
    authorize_price(user)
    material = Material.objects.select_for_update().get(pk=material_id)
    if price_state(material) != expected_state:
        raise ValidationError(PRICE_CONFLICT)
    material.unit_price, material.currency = price, currency
    material.full_clean()
    with price_change_context(user, reason, "service"):
        material.save(update_fields=["unit_price", "currency"])
    return material
