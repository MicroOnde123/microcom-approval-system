from django.conf import settings
from django.db import models


class RequestType(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_permission_request = models.BooleanField(default=False)
    requires_materials = models.BooleanField(default=False)
    requires_amount = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Request(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PENDING", "Pending"),
        ("IN_REVIEW", "In Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("RETURNED", "Returned"),
    ]

    request_number = models.CharField(max_length=50, unique=True)
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

    def __str__(self):
        return self.request_number


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

    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.material} - {self.quantity}"


class RequestApproval(models.Model):
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
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    request = models.ForeignKey(
        "Request",
        on_delete=models.SET_NULL,
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

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.material} - {self.movement_type} - {self.quantity}"
