from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0003_succursale_material_currency_material_unit_price_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="succursale",
            name="physical_address",
            field=models.TextField(
                blank=True, verbose_name="Physical address",
                help_text="Required for new succursales and future invoice issuance. Existing blank addresses may be completed later.",
            ),
        ),
    ]
