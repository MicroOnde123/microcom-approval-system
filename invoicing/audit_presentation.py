"""Pure presentation of recorded audit values. Never queries or changes evidence."""
from decimal import Decimal, InvalidOperation

from django.utils.formats import number_format
from django.utils.translation import gettext as _


def _text(value):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError
    return value


def _decimal(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)) or len(str(value)) > 100:
        raise ValueError
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError from None
    if not result.is_finite() or result < 0 or result.adjusted() > 24 or result.as_tuple().exponent < -8:
        raise ValueError
    return result


def _amount(value):
    # Presentation only: preserve recorded precision; do not recompute money.
    return number_format(_decimal(value), use_l10n=True)


def _price(value, currency):
    return _("Not priced") if value is None else _("%(amount)s %(currency)s") % {
        "amount": _amount(value), "currency": currency}


def _currency(value):
    if value not in ("USD", "CDF", "EUR"):
        raise ValueError
    return value


def _identifier(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValueError
    return value


def _label(line_id, labels):
    name = labels.get(line_id)
    if isinstance(name, str) and name.strip():
        return _("Current invoice-line label: %(name)s (line #%(line)s)") % {
            "name": _text(name), "line": line_id}
    return _("Invoice line #%(line)s") % {"line": line_id}


def _state(value):
    if not isinstance(value, dict) or not isinstance(value.get("lines"), list) or len(value["lines"]) > 1000:
        raise ValueError
    note = _text(value.get("note", ""))
    lines = {}
    for row in value["lines"]:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError
        line_id = _identifier(row[0])
        if line_id in lines:
            raise ValueError
        quantity = _decimal(row[1])
        price = None if row[2] is None else _decimal(row[2])
        lines[line_id] = (quantity, price, _currency(row[3]))
    return note, lines


def format_event(event_type, payload, line_labels=None):
    """Return plain strings for autoescaped templates; labels are explicitly current.

    Payloads do not record historical material names. Never follow live materials
    or substitute current quantities, prices, currencies or notes.
    """
    labels = line_labels if isinstance(line_labels, dict) else {}
    titles = {"DRAFT_CREATED": _("Draft created"), "DRAFT_EDITED": _("Draft edited"),
              "DRAFT_REFRESHED": _("Draft quantities refreshed"), "FINALIZED": _("Invoice finalized")}
    title = titles.get(event_type, _("Other invoice event")) if isinstance(event_type, str) else _("Other invoice event")
    result = {"title": title, "description": "", "items": []}
    try:
        if not isinstance(payload, dict):
            raise ValueError
        if event_type == "DRAFT_CREATED":
            currency = _currency(payload.get("currency"))
            rows = payload.get("lines")
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ValueError
            result["description"] = _("Draft created in %(currency)s. Values below were recorded at creation.") % {"currency": currency}
            seen = set()
            for row in rows:
                if not isinstance(row, dict) or "price" not in row:
                    raise ValueError
                line_id = _identifier(row.get("line"))
                if line_id in seen:
                    raise ValueError
                seen.add(line_id)
                result["items"].append(_("%(material)s — Quantity: %(quantity)s; Unit price: %(price)s") % {
                    "material": _label(line_id, labels), "quantity": _amount(row.get("net")),
                    "price": _price(row["price"], currency)})
        elif event_type in ("DRAFT_EDITED", "DRAFT_REFRESHED"):
            before_note, before = _state(payload.get("before"))
            after_note, after = _state(payload.get("after"))
            result["description"] = _("Recorded changes (before → after).")
            for line_id in sorted(set(before) | set(after)):
                label = _label(line_id, labels)
                if line_id not in before or line_id not in after:
                    state = after.get(line_id) if line_id in after else before[line_id]
                    result["items"].append(_("%(material)s — %(change)s; Quantity: %(quantity)s; Unit price: %(price)s") % {
                        "material": label, "change": _("Line added") if line_id in after else _("Line removed"),
                        "quantity": _amount(state[0]), "price": _price(state[1], state[2])})
                    continue
                old, new = before[line_id], after[line_id]
                if old[0] != new[0]:
                    result["items"].append(_("%(material)s — Quantity: %(before)s → %(after)s") % {
                        "material": label, "before": _amount(old[0]), "after": _amount(new[0])})
                if old[1:] != new[1:]:
                    result["items"].append(_("%(material)s — Unit price: %(before)s → %(after)s") % {
                        "material": label, "before": _price(old[1], old[2]), "after": _price(new[1], new[2])})
                    if old[2] != new[2]:
                        result["items"].append(_("%(material)s — Currency: %(before)s → %(after)s") % {
                            "material": label, "before": old[2], "after": new[2]})
            if not result["items"]:
                result["description"] = (_("Refresh completed without recorded quantity or price changes.")
                    if event_type == "DRAFT_REFRESHED" else _("No recorded quantity or price changes."))
            if before_note != after_note:
                result["items"].append(_("Invoice note: %(before)s → %(after)s") % {
                    "before": before_note or _("Empty"), "after": after_note or _("Empty")})
        elif event_type == "FINALIZED":
            result["description"] = _("Invoice finalized with its recorded reference and total.")
            result["items"] = [_("Document number: %(number)s") % {"number": _text(payload.get("number"))},
                _("Issue date: %(date)s") % {"date": _text(payload.get("issue_date"))},
                _("Total: %(amount)s %(currency)s") % {"amount": _amount(payload.get("total")),
                    "currency": _currency(payload.get("currency"))}]
        else:
            raise ValueError
    except (ValueError, TypeError, InvalidOperation):
        result["description"] = _("Readable details are unavailable for this historical event. Original audit evidence is preserved.")
        result["items"] = []
    return result
