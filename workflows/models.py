from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ApprovalWorkflow(models.Model):
    name = models.CharField(max_length=255)
    request_type = models.ForeignKey("requests_app.RequestType", on_delete=models.CASCADE)
    department = models.ForeignKey("accounts.Department", on_delete=models.CASCADE, null=True, blank=True)
    min_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ApprovalWorkflowStep(models.Model):
    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.CASCADE, related_name="steps")
    step_order = models.PositiveIntegerField()
    approver_role = models.ForeignKey("accounts.Role", on_delete=models.SET_NULL, null=True, blank=True)
    approver_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    alternate_approver_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alternate_workflow_steps",
    )
    is_required = models.BooleanField(default=True)
    is_stock_review = models.BooleanField(
        _("Stock classification review"), default=False,
        help_text=_("Designate one step at any position in a material workflow. Steps keep their configured order."))

    def clean(self):
        super().clean()
        if self.is_stock_review:
            try:
                material_workflow = self.workflow.request_type.requires_materials
            except (ApprovalWorkflow.DoesNotExist, AttributeError):
                material_workflow = False
            if not material_workflow:
                raise ValidationError(_("Stock classification is only available for material workflows."))
            if not self.approver_user_id or not self.approver_user.is_active:
                raise ValidationError(_("Assign an active primary user to the central stock-review step."))
            if self.alternate_approver_user_id and not self.alternate_approver_user.is_active:
                raise ValidationError(_("The alternate stock reviewer must be active."))

    class Meta:
        ordering = ["step_order"]
        unique_together = ("workflow", "step_order")

    def __str__(self):
        return f"{self.workflow.name} - Step {self.step_order}"


def validate_stock_review_steps(steps):
    """Validate opt-in configuration without inserting/reordering any steps."""
    steps = list(steps)
    reviews = [step for step in steps if step.is_stock_review]
    if len(reviews) > 1:
        raise ValidationError(_("Only one stock-review step may be designated per workflow."))
