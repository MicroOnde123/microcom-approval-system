from django.contrib import admin
from django import forms

from .models import (
    RequestType,
    Request,
    RequestApproval,
    RequestAttachment,
    RequestAuditLog,
    RequestMaterialItem,
    StockMovement,
)


class RequestAttachmentInline(admin.TabularInline):
    model = RequestAttachment
    extra = 0
    readonly_fields = ("original_name", "uploaded_by", "created_at")


class RequestApprovalInline(admin.TabularInline):
    model = RequestApproval
    extra = 0
    readonly_fields = (
        "workflow_step",
        "step_order",
        "display_approver_name",
        "status",
        "comment",
        "acted_at",
        "created_at",
        "requires_stock_classification",
    )


class HistoricalMaterialItemAdminForm(forms.ModelForm):
    class Meta:
        model = RequestMaterialItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.legacy_zero = (not self.instance._state.adding and self.instance.quantity == 0)
        if self.legacy_zero:
            for name in ("quantity", "material", "request"):
                if name in self.fields:
                    self.fields[name].disabled = True

    def _get_validation_exclusions(self):
        exclusions = super()._get_validation_exclusions()
        if self.legacy_zero:
            exclusions.add("quantity")
        return exclusions


class RequestMaterialItemInline(admin.TabularInline):
    model = RequestMaterialItem
    form = HistoricalMaterialItemAdminForm
    extra = 0


@admin.register(RequestType)
class RequestTypeAdmin(admin.ModelAdmin):
    def get_readonly_fields(self, request, obj=None):
        return ("reference_namespace",) if obj and obj.reference_namespace else ()

    list_display = (
        "name",
        "code",
        "is_active",
        "is_permission_request",
        "requires_materials",
        "requires_amount",
    )
    search_fields = ("name", "code")
    list_filter = (
        "is_active",
        "is_permission_request",
        "requires_materials",
        "requires_amount",
    )


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # All new requests must use the normal validated, idempotent flow.
        return False

    list_display = (
        "request_number",
        "request_type",
        "submitted_by",
        "department",
        "request_for_department",
        "status",
        "stock_deducted",
        "date_needed",
        "submitted_at",
        "finalized_at",
    )

    list_filter = (
        "request_type",
        "department",
        "request_for_department",
        "status",
        "stock_deducted",
        "date_needed",
        "submitted_at",
    )

    search_fields = (
        "request_number",
        "description",
        "submitted_by__username",
        "submitted_by__full_name",
        "submitted_by__email",
    )

    readonly_fields = (
        "request_number",
        "submitted_at",
        "finalized_at",
        "stock_deducted",
        "classification",
        "succursale",
        "classified_by",
        "classified_at",
    )

    inlines = [
        RequestMaterialItemInline,
        RequestAttachmentInline,
        RequestApprovalInline,
    ]


@admin.register(RequestApproval)
class RequestApprovalAdmin(admin.ModelAdmin):
    readonly_fields = ("requires_stock_classification",)
    list_display = (
        "request",
        "step_order",
        "display_approver_name",
        "status",
        "acted_at",
        "created_at",
    )

    list_filter = (
        "status",
        "step_order",
        "acted_at",
        "created_at",
    )

    search_fields = (
        "request__request_number",
        "approver_user__username",
        "approver_user__full_name",
        "approver_user__email",
    )


@admin.register(RequestAttachment)
class RequestAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "original_name",
        "uploaded_by",
        "created_at",
    )

    search_fields = (
        "request__request_number",
        "original_name",
        "uploaded_by__username",
        "uploaded_by__full_name",
    )


@admin.register(RequestMaterialItem)
class RequestMaterialItemAdmin(admin.ModelAdmin):
    form = HistoricalMaterialItemAdminForm

    list_display = (
        "request",
        "material",
        "quantity",
        "note",
    )

    search_fields = (
        "request__request_number",
        "material__name",
        "material__code",
        "note",
    )


@admin.register(RequestAuditLog)
class RequestAuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "action",
        "performed_by",
        "created_at",
    )

    list_filter = (
        "action",
        "created_at",
    )

    search_fields = (
        "request__request_number",
        "action",
        "performed_by__username",
        "performed_by__full_name",
        "comment",
    )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        "material",
        "movement_type",
        "quantity",
        "request",
        "performed_by",
        "created_at",
    )

    list_filter = (
        "movement_type",
        "created_at",
    )

    search_fields = (
        "material__name",
        "material__code",
        "request__request_number",
        "performed_by__username",
        "performed_by__full_name",
        "note",
    )

    readonly_fields = (
        "material",
        "request",
        "quantity",
        "movement_type",
        "performed_by",
        "note",
        "created_at",
        "return_reason",
        "return_operation_token",
    )
