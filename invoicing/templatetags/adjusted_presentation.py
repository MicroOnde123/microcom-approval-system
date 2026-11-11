"""Display-only helpers for frozen statement values; no database access."""
from decimal import Decimal
from uuid import UUID
from django import template
from invoicing.pdf import display_decimal

register = template.Library()

@register.filter
def statement_amount(value):
    # Preserve meaningful unit-price digits; never round a frozen value.
    number = display_decimal(value, minimum_places=2)
    whole, fraction = number.split('.')
    return format(int(whole), ',d') + '.' + fraction if Decimal(number) >= 0 else format(Decimal(number), ',f')

@register.filter
def readable_reference(value):
    try:
        UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return value
    return ''
