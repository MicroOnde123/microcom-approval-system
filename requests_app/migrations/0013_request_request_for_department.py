from django.db import migrations, models
import django.db.models.deletion


def populate_request_for_department(apps, schema_editor):
    Request = apps.get_model("requests_app", "Request")
    Department = apps.get_model("accounts", "Department")
    fallback_department = None

    for request in Request.objects.select_related("submitted_by").iterator():
        department_id = request.submitted_by.department_id or request.department_id
        if not department_id:
            if fallback_department is None:
                fallback_department, _ = Department.objects.get_or_create(
                    code="UNASSIGNED",
                    defaults={"name": "Unassigned"},
                )
            department_id = fallback_department.pk
        request.request_for_department_id = department_id
        request.save(update_fields=["request_for_department"])


class Migration(migrations.Migration):
    dependencies = [
        ("requests_app", "0012_request_material_issue_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="request",
            name="request_for_department",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_requests",
                to="accounts.department",
            ),
        ),
        migrations.RunPython(
            populate_request_for_department,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="request",
            name="request_for_department",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_requests",
                to="accounts.department",
            ),
        ),
    ]
