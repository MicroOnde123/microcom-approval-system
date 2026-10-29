"""Explicit business-calendar and content-bound attestation helpers. No issuance."""
import hashlib
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_business_timezone(value):
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValidationError(_("Select a valid IANA business timezone."))


def configuration_digest(configuration):
    # Includes every persisted business field: changing any preference invalidates
    # the attestation, including changes made through QuerySet.update().
    values = {field.name: getattr(configuration, field.attname)
              for field in configuration._meta.concrete_fields
              if field.name not in {"id", "updated_at"}}
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def business_date(timestamp, timezone_name):
    validate_business_timezone(timezone_name)
    if timestamp.utcoffset() is None:
        raise ValidationError(_("An aware finalization timestamp is required."))
    return timestamp.astimezone(ZoneInfo(timezone_name)).date()
