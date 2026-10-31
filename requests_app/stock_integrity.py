"""Read-only presentation/diagnostics mirroring stock_services.material_return_totals.

This never authorizes a return. The locked stock service remains authoritative.
"""
from collections import Counter, defaultdict
from decimal import Decimal
from django.utils.translation import gettext as _
from .models import StockMovement


def describe_ledger(request, item, line_count, movements):
    relevant = [m for m in movements if m.movement_type in {"OUT", "RETURN"}]
    outs = [m for m in relevant if m.movement_type == "OUT"]
    issued = sum((m.quantity for m in outs), Decimal("0"))
    returned = sum((m.quantity for m in relevant if m.movement_type == "RETURN"), Decimal("0"))
    issues = []
    if request.status != "APPROVED" or not request.stock_deducted:
        issues.append("stock_not_issued")
    if line_count != 1:
        issues.append("ambiguous_material_lines")
    if any(m.quantity <= 0 for m in relevant):
        issues.append("nonpositive_movement")
    if issued <= 0:
        issues.append("missing_positive_out")
    if issued != item.quantity:
        issues.append("issue_quantity_mismatch")
    if returned > issued:
        issues.append("over_return")
    remaining = None if issues else issued - returned
    return {"issued_quantity": issued if outs else None, "returned_quantity": returned,
            "remaining_quantity": remaining, "issues": issues, "consistent": not issues,
            "status": _("Historical discrepancy") if issues else _("Returnable") if remaining > 0 else _("Fully returned"),
            "warning": _("Historical stock discrepancy — review required.") if issues else "",
            "can_return": not issues and remaining > 0}


def annotate_return_ledgers(requests):
    """Use prefetched related rows; do not evaluate a query per material line."""
    for request in requests:
        items = list(request.material_items.all())
        counts = Counter(item.material_id for item in items)
        grouped = defaultdict(list)
        for movement in request.stock_movements.all():
            grouped[movement.material_id].append(movement)
        for item in items:
            item.return_history = grouped[item.material_id]
            item.return_ledger = describe_ledger(request, item, counts[item.material_id], item.return_history)
    return requests


def movement_prefetch(using=None):
    from django.db.models import Prefetch
    return Prefetch("stock_movements", queryset=StockMovement.objects.using(using).filter(
        movement_type__in=["OUT", "RETURN"]).only("id", "request_id", "material_id", "movement_type", "quantity", "created_at").order_by("created_at", "pk"))
