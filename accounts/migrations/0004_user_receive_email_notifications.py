from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_user_can_view_administration_reports")]
    operations = [migrations.AddField(
        model_name="user", name="receive_email_notifications",
        field=models.BooleanField(default=True, db_default=True, verbose_name="Receive email notifications",
            help_text="Receive optional workflow emails. Security and account emails are unaffected."))]
