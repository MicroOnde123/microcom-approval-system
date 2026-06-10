from django import forms
from django.utils.translation import gettext_lazy as _


class ReturnToStockForm(forms.Form):
    quantity = forms.DecimalField(
        label=_("Returned Quantity"),
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
    )

    reason = forms.CharField(
        label=_("Return Reason"),
        widget=forms.Textarea(attrs={"rows": 3}),
    )