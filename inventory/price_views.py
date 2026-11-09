"""Independent, CSRF-protected catalogue pricing within Material Entries."""
from decimal import Decimal
from django import forms
from django.core import signing
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from core.document_config import Currency
from .models import Material
from .pricing import authorize_price, price_state, update_price, PRICE_CONFLICT

SALT = "inventory.entries.price_revision.v1"


class PriceForm(forms.Form):
    price = forms.DecimalField(label=gettext_lazy("New Price"), required=False,
        max_digits=12, decimal_places=2, min_value=Decimal("0"))
    currency = forms.ChoiceField(label=gettext_lazy("Currency"), choices=Currency.choices)
    reason = forms.CharField(label=gettext_lazy("Reason"), widget=forms.Textarea(attrs={"rows": 3}))
    revision = forms.CharField(widget=forms.HiddenInput)


def price_data(material):
    return {"price": format(material.unit_price, ".2f") if material.unit_price is not None else None,
            "currency": material.currency, "revision": signing.dumps(price_state(material), salt=SALT)}


@never_cache
@require_http_methods(["GET", "POST"])
@csrf_protect
def material_price(request, material_id):
    try:
        authorize_price(request.user)
    except PermissionDenied:
        return JsonResponse({"errors": {"__all__": [_("You do not have permission to change material prices.")]}}, status=403)
    # The revision and price must describe the same locked row.
    if request.method == "GET":
        with transaction.atomic():
            material = get_object_or_404(Material.objects.select_for_update(), pk=material_id)
            return JsonResponse(price_data(material))
    form = PriceForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": dict(form.errors)}, status=400)
    try:
        expected = signing.loads(form.cleaned_data["revision"], salt=SALT)
        with transaction.atomic():
            material = update_price(material_id, request.user, price=form.cleaned_data["price"],
                currency=form.cleaned_data["currency"], reason=form.cleaned_data["reason"], expected_state=expected)
            data = price_data(material)
    except (signing.BadSignature, Material.DoesNotExist):
        return JsonResponse({"errors": {"__all__": [str(PRICE_CONFLICT)]}}, status=409)
    except ValidationError as error:
        return JsonResponse({"errors": error.message_dict if hasattr(error, "message_dict") else {"__all__": error.messages}}, status=409)
    except IntegrityError:
        return JsonResponse({"errors": {"__all__": [_("Unable to save the price. Reload and retry.")]}}, status=409)
    data["message"] = _("Catalogue price saved successfully.")
    return JsonResponse(data)
