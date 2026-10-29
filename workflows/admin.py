from django.contrib import admin
from django import forms
from django.forms.models import BaseInlineFormSet
from types import SimpleNamespace
from .models import ApprovalWorkflow, ApprovalWorkflowStep, validate_stock_review_steps


class WorkflowStepInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        validate_stock_review_steps(form.instance for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE"))


class WorkflowStepAdminForm(forms.ModelForm):
    class Meta:
        model = ApprovalWorkflowStep
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if data.get("workflow") and data.get("step_order") is not None:
            others = list(data["workflow"].steps.exclude(pk=self.instance.pk))
            candidate = SimpleNamespace(step_order=data["step_order"], is_stock_review=data.get("is_stock_review", False))
            validate_stock_review_steps(others + [candidate])
        return data


class ApprovalWorkflowStepInline(admin.TabularInline):
    model = ApprovalWorkflowStep
    extra = 1
    formset = WorkflowStepInlineFormSet


@admin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(admin.ModelAdmin):
    list_display = ("name", "request_type", "department", "min_amount", "max_amount", "is_active")
    list_filter = ("request_type", "department", "is_active")
    inlines = [ApprovalWorkflowStepInline]


@admin.register(ApprovalWorkflowStep)
class ApprovalWorkflowStepAdmin(admin.ModelAdmin):
    form = WorkflowStepAdminForm
    list_display = ("workflow", "step_order", "approver_role", "approver_user", "is_required", "is_stock_review")
    list_filter = ("workflow", "is_required")
