from django import forms
from django.utils.translation import gettext_lazy as _
from decimal import Decimal


class ReturnToStockForm(forms.Form):
    operation_token = forms.CharField(widget=forms.HiddenInput)

    quantity = forms.DecimalField(
        label=_("Returned Quantity"),
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
    )

    reason = forms.CharField(
        label=_("Return Reason"),
        widget=forms.Textarea(attrs={"rows": 3}),
    )
