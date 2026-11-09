from django.contrib import admin
from django import forms
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils.formats import localize
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.html import format_html
from .models import MaterialCategory, Material, Succursale, MaterialPriceChange
from core.document_config import Currency
from .pricing import PRICE_CONFLICT, price_state, price_change_context


STOCK_CONFLICT = _("Stock has changed since this form was opened. Reload the page and review the current balance before saving.")
STOCK_TOKEN_SALT = "inventory.admin.stock_balance"
PRICE_TOKEN_SALT = "inventory.admin.price_revision.v1"
CATALOGUE_TOKEN_SALT = "inventory.admin.catalogue_revision.v1"
CATALOGUE_CONFLICT = _("Catalogue information has changed since this form was opened. Reload the page and review the current values before saving.")


def catalogue_state(material):
    # Cover every persisted catalogue field, including future editable fields.
    # Price and stock retain their existing, separate revision checks.
    return {field.attname: str(getattr(material, field.attname))
            for field in material._meta.concrete_fields
            if field.name not in {"unit_price", "currency", "stock_quantity"}}


@admin.register(Succursale)
class SuccursaleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "physical_address")
    readonly_fields = ("created_at", "updated_at")


class MaterialAdminForm(forms.ModelForm):
    original_stock = forms.CharField(widget=forms.HiddenInput, required=False)
    original_price = forms.CharField(widget=forms.HiddenInput, required=False)
    original_catalogue = forms.CharField(widget=forms.HiddenInput, required=False)
    price_change_reason = forms.CharField(label=_("Price change reason"), required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text=_("Required when changing an existing material's price or currency."))

    class Meta:
        model = Material
        fields = "__all__"
        labels = {"name": _("Material name"), "code": _("Unique material code"),
                  "category": _("Category"), "unit": _("Unit of measurement"),
                  "description": _("Description"), "is_active": _("Active status"),
                  "stock_quantity": _("Stock quantity"), "minimum_stock_level": _("Minimum stock level")}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("currency"):
            from core.models import CompanyDocumentSettings

            self.initial["currency"] = (
                self.instance.currency
                or CompanyDocumentSettings.objects.values_list(
                    "default_currency", flat=True
                ).first()
                or Currency.USD
            )
        if not self.is_bound and self.instance.pk:
            self.initial["original_catalogue"] = signing.dumps(catalogue_state(self.instance), salt=CATALOGUE_TOKEN_SALT)
            self.initial["original_price"] = signing.dumps(price_state(self.instance), salt=PRICE_TOKEN_SALT)
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
            try:
                if signing.loads(cleaned.get("original_price", ""), salt=PRICE_TOKEN_SALT) != price_state(current):
                    raise signing.BadSignature
            except (signing.BadSignature, TypeError, ValueError):
                raise forms.ValidationError(PRICE_CONFLICT)
            self.original_price_state = price_state(current)
            try:
                if signing.loads(cleaned.get("original_catalogue", ""), salt=CATALOGUE_TOKEN_SALT) != catalogue_state(current):
                    raise signing.BadSignature
            except (signing.BadSignature, TypeError, ValueError):
                raise forms.ValidationError(CATALOGUE_CONFLICT)
            self.original_catalogue_state = catalogue_state(current)
            # Model.clean supplies the existing default currency for a non-null price.
            proposed_currency = cleaned.get("currency") or None
            if cleaned.get("unit_price") is not None and not proposed_currency:
                from core.models import CompanyDocumentSettings
                proposed_currency = CompanyDocumentSettings.objects.values_list("default_currency", flat=True).first() or Currency.USD
            if ((current.unit_price, current.currency) != (cleaned.get("unit_price"), proposed_currency)
                    and not cleaned.get("price_change_reason", "").strip()):
                self.add_error("price_change_reason", _("Enter a reason for the price or currency change."))
        return cleaned


@admin.register(MaterialCategory)
class MaterialCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class MaterialCategoryFilter(admin.RelatedFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = _("Category")


class MaterialActiveFilter(admin.BooleanFieldListFilter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = _("Active status")


class MaterialStockStatusFilter(admin.SimpleListFilter):
    title = _("Stock status")
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (("out", _("Out of stock")), ("low", _("Low stock")), ("available", _("Above minimum")))

    def queryset(self, request, queryset):
        # Display-only classification: nonpositive; positive at/below minimum; above minimum.
        if self.value() == "out":
            return queryset.filter(stock_quantity__lte=0)
        if self.value() == "low":
            return queryset.filter(stock_quantity__gt=0, stock_quantity__lte=F("minimum_stock_level"))
        if self.value() == "available":
            return queryset.filter(stock_quantity__gt=0).filter(stock_quantity__gt=F("minimum_stock_level"))
        return queryset


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    form = MaterialAdminForm
    readonly_fields = ("price_history",)

    @admin.display(description=_("Material price history"))
    def price_history(self, obj):
        if not obj or not obj.pk:
            return "—"
        return format_html('<a href="{}?material__id__exact={}">{}</a>',
            reverse("admin:inventory_materialpricechange_changelist"), obj.pk, _("View price history"))

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        if change:
            current = Material.objects.select_for_update().get(pk=obj.pk)
            if (not hasattr(form, "original_stock_quantity")
                    or current.stock_quantity != form.original_stock_quantity):
                raise ValidationError(STOCK_CONFLICT)
            if catalogue_state(current) != getattr(form, "original_catalogue_state", None):
                raise ValidationError(CATALOGUE_CONFLICT)
            if price_state(current) != getattr(form, "original_price_state", None):
                raise ValidationError(PRICE_CONFLICT)
            if (current.unit_price, current.currency) != (obj.unit_price, obj.currency):
                with price_change_context(request.user, form.cleaned_data.get("price_change_reason"), "admin"):
                    super().save_model(request, obj, form, change)
                return
        super().save_model(request, obj, form, change)

    list_display = ("material_name", "material_code", "material_category", "stock_balance",
                    "minimum_level", "stock_status", "active_status", "unit_price", "currency")
    list_display_links = ("material_name", "material_code")
    list_filter = (MaterialStockStatusFilter, ("category", MaterialCategoryFilter), ("is_active", MaterialActiveFilter))
    search_fields = ("name", "code", "description")
    search_help_text = _("Search by material name, code or description.")
    list_select_related = ("category",)
    ordering = ("name", "code", "pk")
    fieldsets = (
        (_("Material Information"), {"fields": ("name", "code", "category", "unit", "description", "is_active")}),
        (_("Stock settings"), {"fields": ("stock_quantity", "minimum_stock_level"),
            "description": _("Stock status compares the current quantity with the minimum stock level.")}),
        (_("Catalogue price"), {"fields": ("unit_price", "currency", "price_change_reason", "price_history"),
            "description": _("Required when changing an existing material's price or currency.")}),
        (None, {"fields": ("original_stock", "original_price", "original_catalogue"), "classes": ("material-revisions",)}),
    )

    class Media:
        css = {"all": ("css/admin_material.css",)}

    @admin.display(description=_("Material name"), ordering="name")
    def material_name(self, obj):
        return obj.name

    @admin.display(description=_("Unique material code"), ordering="code")
    def material_code(self, obj):
        return obj.code

    @admin.display(description=_("Category"), ordering="category__name")
    def material_category(self, obj):
        return obj.category.name

    @admin.display(description=_("Stock quantity"), ordering="stock_quantity")
    def stock_balance(self, obj):
        return format_html('<span class="material-quantity">{}</span> <span class="material-unit">{}</span>', localize(obj.stock_quantity), obj.unit)

    @admin.display(description=_("Minimum stock level"), ordering="minimum_stock_level")
    def minimum_level(self, obj):
        return format_html('{} <span class="material-unit">{}</span>', localize(obj.minimum_stock_level), obj.unit)

    @admin.display(description=_("Active status"), boolean=True, ordering="is_active")
    def active_status(self, obj):
        return obj.is_active

    @admin.display(description=_("Stock status"), ordering="stock_quantity")
    def stock_status(self, obj):
        if obj.stock_quantity <= 0:
            status, label = "out", _("Out of stock")
        elif obj.stock_quantity <= obj.minimum_stock_level:
            status, label = "low", _("Low stock")
        else:
            status, label = "available", _("Above minimum")
        return format_html('<span class="material-stock-status material-stock-status--{}">{}</span>', status, label)



@admin.register(MaterialPriceChange)
class MaterialPriceChangeAdmin(admin.ModelAdmin):
    list_display = ("material_label", "old_price", "old_currency", "new_price", "new_currency", "user", "changed_at", "source", "reason")
    empty_value_display = _("Unknown")
    list_select_related = ("material", "material__category", "user")
    list_filter = ("source", "new_currency", "changed_at")
    search_fields = ("material__code", "material__name", "reason", "user__username")
    readonly_fields = ("material", "old_price", "old_currency", "new_price", "new_currency", "user", "changed_at", "reason", "source")
    list_per_page = 50

    @admin.display(description=_("Material"), ordering="material__code")
    def material_label(self, obj):
        return f"{obj.material.code} — {obj.material.name}"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
