"""Presentation-only date widget. Services continue to receive Python dates."""
import re
from datetime import date

from django import forms
from django.utils.translation import get_language


def canonical_date(value):
    """Accept unambiguous ISO and French dates; preserve invalid input for errors."""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        day, month, year = value.split("/")
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            pass
    return value


class EntryDateInput(forms.TextInput):
    template_name = "inventory/widgets/entry_date.html"

    def value_from_datadict(self, data, files, name):
        return canonical_date(super().value_from_datadict(data, files, name))

    def format_value(self, value):
        if isinstance(value, date):
            value = value.isoformat()
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                return value
            return parsed.strftime("%d/%m/%Y") if (get_language() or "en").startswith("fr") else value
        return value

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        french = (get_language() or "en").startswith("fr")
        context["date_language"] = "fr" if french else "en"
        context["date_format"] = "DD/MM/YYYY" if french else "YYYY-MM-DD"
        context["widget"]["attrs"].update({"placeholder": context["date_format"], "autocomplete": "off"})
        widget_attrs = context["widget"]["attrs"]
        hint_id = widget_attrs.get("id", name) + "-format"
        widget_attrs["aria-describedby"] = (widget_attrs.get("aria-describedby", "") + " " + hint_id).strip()
        context["date_hint_id"] = hint_id
        return context


class EntryDateField(forms.DateField):
    widget = EntryDateInput

    def __init__(self, *args, **kwargs):
        # Widget normalization makes browser and no-JS submissions consistent.
        kwargs["input_formats"] = ["%Y-%m-%d"]
        super().__init__(*args, **kwargs)
