from django.contrib import admin

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
        "approver_user",
        "status",
        "comment",
        "acted_at",
        "created_at",
    )


class RequestMaterialItemInline(admin.TabularInline):
    model = RequestMaterialItem
    extra = 0


@admin.register(RequestType)
class RequestTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "is_active",
        "requires_materials",
        "requires_amount",
    )
    search_fields = ("name", "code")
    list_filter = ("is_active", "requires_materials", "requires_amount")


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = (
        "request_number",
        "request_type",
        "submitted_by",
        "department",
        "status",
        "stock_deducted",
        "date_needed",
        "submitted_at",
        "finalized_at",
    )

    list_filter = (
        "request_type",
        "department",
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
    )

    inlines = [
        RequestMaterialItemInline,
        RequestAttachmentInline,
        RequestApprovalInline,
    ]


@admin.register(RequestApproval)
class RequestApprovalAdmin(admin.ModelAdmin):
    list_display = (
        "request",
        "step_order",
        "approver_user",
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
    )