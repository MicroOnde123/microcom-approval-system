"""Nonfinancial BC/BS references. This module never operates on inventory."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.models import Q
from django.utils.translation import gettext as _

from .models import MaterialDocument, Request

MAX_COUNTER = 9223372036854775807


def format_reference(kind, year, counter):
    if kind not in {"BC", "BS"} or not 1 <= year <= 9999 or not 1 <= counter <= MAX_COUNTER:
        raise ValidationError(_("Invalid material document reference."))
    return f"{kind}/{counter:04d}/{year}"


def validate_access(request, user):
    if not user.is_authenticated or not (
        user.pk == request.submitted_by_id or user.is_superuser
        or getattr(user, "can_manage_stock", False)
        or request.approvals.filter(Q(approver_user=user) | Q(alternate_approver_user=user)).exists()
    ):
        raise PermissionDenied(_("You are not allowed to view this document."))
    if request.status != "APPROVED" or not request.stock_deducted or not request.request_type.requires_materials or not request.material_items.exists():
        raise ValidationError(_("Material documents require final approval and confirmed stock deduction."))


@transaction.atomic
def issue_document(request_id, kind, user):
    if kind not in {"BC", "BS"}:
        raise ValidationError(_("Invalid material document reference."))
    if connection.vendor != "postgresql":
        raise ValidationError(_("Material document numbering requires PostgreSQL."))
    request = Request.objects.select_for_update().select_related("request_type").get(pk=request_id)
    validate_access(request, user)
    existing = MaterialDocument.objects.filter(request=request, kind=kind).first()
    if existing:
        return existing
    # Lock request first, then the one type/year sequence. The unique upsert
    # serializes first use across requests. A failure rolls back its increment.
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS allocated_at),
            allocation AS (
                INSERT INTO requests_app_materialdocumentsequence (kind, year, last_counter)
                SELECT %s, extract(year FROM allocated_at AT TIME ZONE 'Africa/Kinshasa')::integer, 1 FROM instant
                ON CONFLICT (kind, year) DO UPDATE
                SET last_counter = requests_app_materialdocumentsequence.last_counter + 1
                WHERE requests_app_materialdocumentsequence.last_counter < %s
                RETURNING year, last_counter
            ) SELECT year, last_counter, allocated_at FROM allocation CROSS JOIN instant
        """, [kind, MAX_COUNTER])
        allocation = cursor.fetchone()
    if allocation is None:
        raise ValidationError(_("The material document sequence is exhausted. Ask an administrator."))
    year, counter, allocated_at = allocation
    return MaterialDocument.objects.create(request=request, kind=kind, year=year, counter=counter,
        allocated_at=allocated_at, reference=format_reference(kind, year, counter))
