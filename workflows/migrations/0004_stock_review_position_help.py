from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workflows", "0003_approvalworkflowstep_is_stock_review")]

    operations = [
        migrations.AlterField(
            model_name="approvalworkflowstep",
            name="is_stock_review",
            field=models.BooleanField(
                default=False,
                verbose_name="Stock classification review",
                help_text="Designate one step at any position in a material workflow. Steps keep their configured order.",
            ),
        ),
    ]
