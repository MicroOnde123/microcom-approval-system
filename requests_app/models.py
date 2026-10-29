from django.conf import settings
from django.db import models, router, transaction
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from .reference_namespaces import validate_namespace_owner


class RequestType(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_permission_request = models.BooleanField(default=False)
    requires_materials = models.BooleanField(default=False)
    requires_amount = models.BooleanField(default=False)
    reference_namespace = models.CharField(
        _("Reference namespace"), max_length=16, unique=True, null=True, blank=True,
        validators=[RegexValidator(r"\A[A-Z][A-Z0-9]{0,15}\Z", _("Use 1–16 uppercase letters or digits, starting with a letter."))],
        help_text=_("Assigned automatically on first creation; immutable once assigned. ADM and MAT are reserved."))

    def clean(self):
        super().clean()
        self.reference_namespace = self.reference_namespace or None
        validate_namespace_owner(self.code, self.reference_namespace)
        if not self._state.adding:
            original = type(self).objects.filter(pk=self.pk).values_list("reference_namespace", flat=True).first()
            if original is not None and self.reference_namespace != original:
                raise ValidationError(_("An assigned request reference namespace cannot be changed."))

    def __str__(self):
        return self.name


class Request(models.Model):
    class Classification(models.TextChoices):
        CLIENT = "CLIENT", _("Client")
        MICROCOM = "MICROCOM", _("Microcom")

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending"),
        ("IN_REVIEW", "In Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("RETURNED", "Returned"),
        ("CANCELLED", "Cancelled"),
    ]

    request_number = models.CharField(max_length=50, unique=True)
    reference_namespace_snapshot = models.CharField(max_length=16, null=True, blank=True, editable=False)
    reference_year = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    reference_counter = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    reference_allocated_at = models.DateTimeField(null=True, blank=True, editable=False)
    request_type = models.ForeignKey(RequestType, on_delete=models.PROTECT)

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_requests",
    )

    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
    )

    request_for_department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="owned_requests",
        db_index=True,
    )

    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    date_needed = models.DateField(null=True, blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    current_step_order = models.PositiveIntegerField(null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    finalized_at = models.DateTimeField(null=True, blank=True)

    stock_deducted = models.BooleanField(
        default=False,
        help_text="Prevents deducting stock more than once for the same request.",
    )

    stock_returned = models.BooleanField(
        default=False,
        help_text="Indicates whether stock has been returned for this request.",
    )

    stock_returned_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    material_issue_note = models.TextField(blank=True)
    classification = models.CharField(_("Stock classification"), max_length=10, choices=Classification.choices, null=True, blank=True)
    succursale = models.ForeignKey("inventory.Succursale", verbose_name=_("Succursale"), on_delete=models.PROTECT, null=True, blank=True)
    classified_by = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("Classified by"), on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name="classified_stock_requests")
    classified_at = models.DateTimeField(_("Classified at"), null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(
            condition=(models.Q(reference_namespace_snapshot__isnull=True, reference_year__isnull=True,
                                reference_counter__isnull=True, reference_allocated_at__isnull=True)
                       | (models.Q(reference_namespace_snapshot__isnull=False, reference_year__gte=1, reference_year__lte=9999,
                                   reference_year__isnull=False, reference_counter__gte=1, reference_counter__isnull=False,
                                   reference_allocated_at__isnull=False) & ~models.Q(reference_namespace_snapshot=""))),
            name="request_reference_metadata_complete"), models.UniqueConstraint(
                fields=["reference_namespace_snapshot", "reference_year", "reference_counter"],
                name="request_reference_allocation_unique"), models.CheckConstraint(
            condition=(models.Q(classification__isnull=True, succursale__isnull=True)
                       | (models.Q(classification__isnull=False)
                          & (models.Q(classification="CLIENT", succursale__isnull=True)
                             | models.Q(classification="MICROCOM", succursale__isnull=False)))),
            name="requests_valid_stock_classification")]

    def save(self, *args, **kwargs):
        if not self.request_for_department_id and self.department_id:
            self.request_for_department_id = self.department_id
        super().save(*args, **kwargs)

    def __str__(self):
        return self.request_number


class RequestReferenceSequence(models.Model):
    """Ordinary numbering only; independent of verified financial sequences."""
    request_type = models.ForeignKey(RequestType, on_delete=models.PROTECT)
    year = models.PositiveSmallIntegerField()
    last_counter = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["request_type", "year"], name="request_sequence_scope"),
                       models.CheckConstraint(condition=models.Q(year__gte=1, year__lte=9999), name="request_sequence_year")]


class MaterialDocumentSequence(models.Model):
    kind = models.CharField(max_length=2, choices=[("BC", "BC"), ("BS", "BS")])
    year = models.PositiveSmallIntegerField()
    last_counter = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "year"], name="material_document_sequence_scope"),
            models.CheckConstraint(condition=models.Q(kind__in=["BC", "BS"], year__gte=1, year__lte=9999), name="material_document_sequence_valid"),
        ]


class MaterialDocument(models.Model):
    request = models.ForeignKey(Request, on_delete=models.PROTECT, related_name="material_documents")
    kind = models.CharField(max_length=2, choices=[("BC", "BC"), ("BS", "BS")])
    year = models.PositiveSmallIntegerField()
    counter = models.PositiveBigIntegerField()
    reference = models.CharField(max_length=32, unique=True, editable=False)
    allocated_at = models.DateTimeField(editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "kind"], name="material_document_request_kind"),
            models.UniqueConstraint(fields=["kind", "year", "counter"], name="material_document_allocation"),
            models.CheckConstraint(condition=models.Q(kind__in=["BC", "BS"], year__gte=1, year__lte=9999, counter__gte=1), name="material_document_valid"),
        ]


class RequestCreationReceipt(models.Model):
    token = models.UUIDField(primary_key=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    payload_digest = models.CharField(max_length=64)
    request = models.OneToOneField(Request, on_delete=models.PROTECT, null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)


class RequestAttachment(models.Model):
    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    file = models.FileField(upload_to="request_attachments/")
    original_name = models.CharField(max_length=255)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name


class RequestMaterialItem(models.Model):
    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name="material_items",
    )

    material = models.ForeignKey(
        "inventory.Material",
        on_delete=models.PROTECT,
    )

    quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"), message=_("Quantity must be greater than zero."))],
    )
    note = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        field = self._meta.get_field("quantity")
        quantity = field.to_python(self.quantity)
        if quantity == 0 and not self._state.adding and not kwargs.get("force_insert"):
            using = kwargs.get("using") or router.db_for_write(type(self), instance=self)
            with transaction.atomic(using=using):
                original = type(self).objects.using(using).select_for_update().get(pk=self.pk)
                if (original.quantity == 0 and original.request_id == self.request_id
                        and original.material_id == self.material_id
                        and (kwargs.get("update_fields") is None
                             or set(kwargs["update_fields"]) <= {"note"})):
                    # The exception is only for notes on an unchanged legacy pair.
                    # Never include its quantity or references in the SQL UPDATE.
                    kwargs["update_fields"] = ["note"]
                    super().save(*args, **kwargs)
                    return
        self.quantity = field.clean(quantity, self)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.material} - {self.quantity}"


class RequestApproval(models.Model):
    requires_stock_classification = models.BooleanField(
        _("Requires stock classification"), default=False, editable=False)
    STEP_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("RETURNED", "Returned"),
        ("SKIPPED", "Skipped"),
    ]

    request = models.ForeignKey(
        Request,
        on_delete=models.CASCADE,
        related_name="approvals",
    )

    workflow_step = models.ForeignKey(
        "workflows.ApprovalWorkflowStep",
        on_delete=models.PROTECT,
    )

    step_order = models.PositiveIntegerField()

    approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
    )
    
    alternate_approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alternate_request_approvals",
    )

    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acted_request_approvals",
    )

    status = models.CharField(
        max_length=20,
        choices=STEP_STATUS_CHOICES,
        default="PENDING",
    )

    comment = models.TextField(blank=True)
    acted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.request.request_number} - Step {self.step_order}"

    @property
    def display_approver(self):
        return self.acted_by or self.approver_user

    @property
    def display_approver_name(self):
        approver = self.display_approver
        if not approver:
            return ""
        return approver.full_name or approver.username


class RequestAuditLog(models.Model):
    request = models.ForeignKey(
        "Request",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )

    action = models.CharField(max_length=50)

    performed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
    )

    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} - {self.request.request_number}"


class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ("OUT", "Stock Out"),
        ("IN", "Stock In"),
        ("RETURN", "Return to Stock"),
    ]

    material = models.ForeignKey(
        "inventory.Material",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )

    request = models.ForeignKey(
        "Request",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    movement_type = models.CharField(
        max_length=10,
        choices=MOVEMENT_TYPES,
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    note = models.TextField(blank=True)

    return_reason = models.TextField(
        blank=True,
        help_text="Reason why material was returned to stock.",
    )

    # NULL preserves all legacy movements; new return operations are durable retries.
    return_operation_token = models.UUIDField(null=True, blank=True, unique=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.material} - {self.movement_type} - {self.quantity}"
