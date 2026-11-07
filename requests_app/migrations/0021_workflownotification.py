from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [("requests_app", "0020_material_reconciliation_return_receipts"),
                    ("accounts", "0004_user_receive_email_notifications"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="WorkflowNotification", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("event_type", models.CharField(max_length=50)), ("reference", models.CharField(max_length=150)),
        ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
        ("read_at", models.DateTimeField(null=True, blank=True)),
        ("actionable", models.BooleanField(default=False)), ("resolved_at", models.DateTimeField(null=True, blank=True)),
        ("event_key", models.CharField(max_length=150, unique=True)),
        ("recipient", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.CASCADE, related_name="workflow_notifications")),
        ("request", models.ForeignKey(to="requests_app.request", on_delete=django.db.models.deletion.CASCADE, related_name="workflow_notifications")),
        ("approval", models.ForeignKey(to="requests_app.requestapproval", on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="workflow_notifications")),
    ], options={"ordering":["-created_at","-pk"], "indexes":[models.Index(fields=["recipient","read_at","-id"], name="workflow_notice_unread_idx")]})]
