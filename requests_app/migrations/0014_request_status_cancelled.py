from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("requests_app", "0013_request_request_for_department"),
    ]

    operations = [
        migrations.AlterField(
            model_name="request",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("PENDING", "Pending"),
                    ("IN_REVIEW", "In Review"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("RETURNED", "Returned"),
                    ("CANCELLED", "Cancelled"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
    ]
