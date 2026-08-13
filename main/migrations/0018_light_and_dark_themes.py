from django.db import migrations, models


def migrate_themes(apps, schema_editor):
    UserPreference = apps.get_model("main", "UserPreference")
    UserPreference.objects.exclude(theme="dark").update(theme="light")


class Migration(migrations.Migration):
    dependencies = [("main", "0017_add_rpi_cpu_temperature")]

    operations = [
        migrations.RunPython(migrate_themes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userpreference",
            name="theme",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark")],
                default="light",
                max_length=16,
            ),
        ),
    ]
