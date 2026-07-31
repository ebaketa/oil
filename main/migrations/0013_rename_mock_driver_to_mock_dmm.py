from django.db import migrations, models


def rename_mock_driver(apps, schema_editor):
    """Rename the persisted Mock DMM driver key."""
    Instrument = apps.get_model("main", "Instrument")
    Instrument.objects.filter(driver="mock").update(driver="mock-dmm")


def restore_mock_driver_name(apps, schema_editor):
    """Restore the former persisted mock driver key."""
    Instrument = apps.get_model("main", "Instrument")
    Instrument.objects.filter(driver="mock-dmm").update(driver="mock")


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0012_userpreference_sidebar_position"),
    ]

    operations = [
        migrations.RunPython(
            rename_mock_driver,
            restore_mock_driver_name,
        ),
        migrations.AlterField(
            model_name="instrument",
            name="driver",
            field=models.CharField(
                choices=[
                    ("agilent_34401a", "Agilent 34401A"),
                    ("keysight_34461a", "Keysight 34461A"),
                    ("mock-dmm", "Mock DMM"),
                    ("mock_dc_power_supply", "Mock DC Power Supply"),
                ],
                max_length=32,
            ),
        ),
    ]
