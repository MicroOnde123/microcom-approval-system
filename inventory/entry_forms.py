from decimal import Decimal
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .models import Material
from .entry_dates import EntryDateField
from core.document_config import Currency


class ReceiptForm(forms.Form):
    token = forms.CharField(label=_("Receipt form token"), widget=forms.HiddenInput)
    quantity = forms.DecimalField(label=_("Quantity received"), max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    received_on = EntryDateField(label=_("Receipt date"), initial=timezone.localdate)
    supplier = forms.CharField(label=_("Supplier"), max_length=200, required=False)
    delivery_reference = forms.CharField(label=_("Delivery/reference number"), max_length=200, required=False)
    notes = forms.CharField(label=_("Notes"), required=False, widget=forms.Textarea(attrs={"rows": 3}))


class MaterialChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, material):
        return f"{material.name} ({material.code}) - {material.stock_quantity} {material.unit}"


class ExistingReceiptForm(ReceiptForm):
    field_order = ["material", "token", "quantity", "received_on", "supplier", "delivery_reference", "notes"]
    material = MaterialChoiceField(label=_("Material"), queryset=Material.objects.select_related("category").order_by("name"))


class NewMaterialForm(forms.ModelForm):
    def __init__(self, *args, defer_unique_validation=False, **kwargs):
        self.defer_unique_validation = defer_unique_validation
        super().__init__(*args, **kwargs)

    def validate_unique(self):
        # The receipt service must compare retry payloads before checking code
        # uniqueness: a completed registration already owns its material code.
        # Fresh registrations still run normal uniqueness validation in the service.
        if not self.defer_unique_validation:
            super().validate_unique()

    currency = forms.ChoiceField(label=_("Currency"), choices=Currency.choices, initial=Currency.USD)
    minimum_stock_level = forms.DecimalField(label=_("Minimum stock level"), max_digits=10, decimal_places=2, min_value=0, initial=0)
    unit = forms.CharField(label=_("Unit of measurement"), max_length=30)
    class Meta:
        model = Material
        fields = ["name", "code", "category", "description", "unit", "minimum_stock_level", "unit_price", "currency", "is_active"]
        labels = {"name": _("Material name"), "code": _("Unique material code"), "category": _("Category"), "description": _("Description"), "currency": _("Currency"), "is_active": _("Active status")}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
        error_messages = {"code": {"unique": _("A material with this code already exists.")}}


class CategoryForm(forms.Form):
    name = forms.CharField(label=_("Category name"), max_length=100)
    code = forms.CharField(label=_("Unique category code"), max_length=30)
    description = forms.CharField(label=_("Description"), required=False,
                                  widget=forms.Textarea(attrs={"rows": 3}))
