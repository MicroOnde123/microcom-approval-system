from django.conf import settings
from django.db import models


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
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ["step_order"]
        unique_together = ("workflow", "step_order")

    def __str__(self):
        return f"{self.workflow.name} - Step {self.step_order}"