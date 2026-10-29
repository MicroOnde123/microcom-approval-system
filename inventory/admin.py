from django.contrib import admin
from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import MaterialCategory, Material, Succursale


STOCK_CONFLICT = _("Stock has changed since this form was opened. Reload the page and review the current balance before saving.")
STOCK_TOKEN_SALT = "inventory.admin.stock_balance"


@admin.register(Succursale)
class SuccursaleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "physical_address")
    readonly_fields = ("created_at", "updated_at")


class MaterialAdminForm(forms.ModelForm):
    original_stock = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Material
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and self.instance.pk:
            self.initial["original_stock"] = signing.dumps(
                {"material": self.instance.pk, "stock": str(self.instance.stock_quantity)},
                salt=STOCK_TOKEN_SALT)

    def clean(self):
        cleaned = super().clean()
        if self.instance.pk:
            # Django admin wraps the whole POST (validation through save) in an
            # atomic transaction. Keep this lock until that transaction ends.
            current = Material.objects.select_for_update().get(pk=self.instance.pk)
            try:
                payload = signing.loads(cleaned.get("original_stock", ""), salt=STOCK_TOKEN_SALT)
                if payload != {"material": current.pk, "stock": str(current.stock_quantity)}:
                    raise signing.BadSignature
            except (signing.BadSignature, TypeError, ValueError):
                raise forms.ValidationError(STOCK_CONFLICT)
            self.original_stock_quantity = current.stock_quantity
        return cleaned


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    form = MaterialAdminForm

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            current = Material.objects.select_for_update().get(pk=obj.pk)
            if (not hasattr(form, "original_stock_quantity")
                    or current.stock_quantity != form.original_stock_quantity):
                raise ValidationError(STOCK_CONFLICT)
        super().save_model(request, obj, form, change)

    list_display = (
        "name",
        "code",
        "category",
        "unit",
        "is_active",
        "stock_quantity",
        "minimum_stock_level",
        "is_active",
        "unit_price",
        "currency",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "code", "description")
