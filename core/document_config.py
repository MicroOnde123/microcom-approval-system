"""Shared validation for document preferences; no document issuance here."""
import re
from string import Formatter

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class Currency(models.TextChoices):
    USD = "USD", _("US dollar (USD)")
    CDF = "CDF", _("Congolese franc (CDF)")
    EUR = "EUR", _("Euro (EUR)")


def validate_number_format(value):
    try:
        fields = []
        for literal, field, spec, conversion in Formatter().parse(value):
            if not re.fullmatch(r"[A-Za-z0-9 /_.-]*", literal):
                raise ValueError
            if field is None:
                continue
            if field not in {"number", "year"} or conversion:
                raise ValueError
            if spec and (not re.fullmatch(r"0?[1-9][0-9]?d", spec)
                         or int(spec[:-1]) > 12):
                raise ValueError
            fields.append(field)
        if fields.count("number") != 1 or fields.count("year") > 1:
            raise ValueError
    except ValueError:
        raise ValidationError(_("Use {number} once and optionally {year}, with a numeric width of at most 12."), code="invalid_number_format")


def validate_logo_reference(value):
    if not re.fullmatch(r"(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|webp)", value):
        raise ValidationError(_("Use a relative static image path without traversal or an external URL."), code="invalid_logo_reference")
