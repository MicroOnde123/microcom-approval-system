from django.contrib import admin
from .models import ApprovalWorkflow, ApprovalWorkflowStep


class ApprovalWorkflowStepInline(admin.TabularInline):
    model = ApprovalWorkflowStep
    extra = 1


@admin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "request_type", "department", "min_amount", "max_amount", "is_active")
    list_filter = ("request_type", "department", "is_active")
    inlines = [ApprovalWorkflowStepInline]


@admin.register(ApprovalWorkflowStep)
class ApprovalWorkflowStepAdmin(admin.ModelAdmin):
    list_display = ("workflow", "step_order", "approver_role", "approver_user", "is_required")
    list_filter = ("workflow", "is_required")