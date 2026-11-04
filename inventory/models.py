from django.db import models
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from core.document_config import Currency
from django.core.exceptions import ValidationError


class Succursale(models.Model):
    code = models.CharField(_("Succursale code"), max_length=30, unique=True)
    name = models.CharField(_("Succursale name"), max_length=100)
    physical_address = models.TextField(
        _("Physical address"), blank=True,
        help_text=_("Required for new succursales and future invoice issuance. Existing blank addresses may be completed later."))
    is_active = models.BooleanField(_("Active"), default=True)
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated at"), auto_now=True)

    class Meta:
        verbose_name = _("Succursale")
        verbose_name_plural = _("Succursales")
        ordering = ["name", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        super().clean()
        self.physical_address = (self.physical_address or "").strip()
        if self._state.adding and not self.physical_address:
            raise ValidationError({"physical_address": _("Enter a physical address for a new succursale.")})


class MaterialCategory(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Material categories"

    def __str__(self):
        return self.name


class Material(models.Model):
    category = models.ForeignKey(
        MaterialCategory,
        on_delete=models.PROTECT,
        related_name="materials"
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(
        _("Unit price"), max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"), message=_("Unit price cannot be negative."))],
        help_text=_("Leave blank when the price is unknown. Zero is an explicit price."))
    currency = models.CharField(
        _("Price currency"), max_length=3, null=True, blank=True, choices=Currency.choices,
        error_messages={"invalid_choice": _("Select a supported currency: USD, CDF or EUR.")},
        help_text=_("For a new price, defaults to the document currency, or USD when settings are absent."))

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(unit_price__isnull=True) | models.Q(unit_price__gte=0), name="inventory_material_nonnegative_price"),
            models.CheckConstraint(condition=models.Q(currency__isnull=True) | models.Q(currency__in=Currency.values), name="inventory_material_supported_currency"),
            models.CheckConstraint(condition=models.Q(unit_price__isnull=True) | models.Q(currency__isnull=False), name="inventory_material_priced_currency"),
        ]

    def clean(self):
        super().clean()
        if self.unit_price is not None and not self.currency:
            from core.models import CompanyDocumentSettings
            configured = CompanyDocumentSettings.objects.values_list("default_currency", flat=True).first()
            self.currency = configured or Currency.USD

    def __str__(self):
        stock = f"{self.stock_quantity:g}" if self.stock_quantity is not None else "0"
        Unit = self.unit or ""
        return f"{self.name} | Code: {self.code} | Category: {self.category.name} | Stock: {stock} {Unit}"
    


class MaterialReceipt(models.Model):
    """A durable receipt and idempotency claim, committed with its stock movement."""
    operation_token = models.UUIDField(unique=True, editable=False)
    reference = models.CharField(max_length=40, unique=True, editable=False)
    payload_hash = models.CharField(max_length=64, editable=False)
    received_on = models.DateField()
    supplier = models.CharField(max_length=200, blank=True)
    delivery_reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    transaction_type = models.CharField(
        max_length=10, choices=[("new", _("New material")), ("existing", _("Existing material"))],
        null=True, blank=True, editable=False)

    class Meta:
        indexes = [models.Index(fields=["-received_on", "-id"], name="receipt_date_order_idx")]
        constraints = [models.CheckConstraint(
            condition=models.Q(transaction_type__isnull=True) | models.Q(transaction_type__in=["new", "existing"]),
            name="receipt_transaction_type_valid")]


class MaterialReceiptLine(models.Model):
    receipt = models.ForeignKey(MaterialReceipt, on_delete=models.PROTECT, related_name='lines')
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    stock_after = models.DecimalField(max_digits=10, decimal_places=2)
    movement = models.OneToOneField('requests_app.StockMovement', on_delete=models.PROTECT)
    material_snapshot = models.JSONField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name='material_receipt_positive_quantity')]
