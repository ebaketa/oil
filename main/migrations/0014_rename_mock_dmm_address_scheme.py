from django.db import migrations, models


def rename_mock_dmm_addresses(apps, schema_editor):
    """Rename the address scheme used by Mock DMM instruments."""
    Instrument = apps.get_model("main", "Instrument")
    for instrument in Instrument.objects.filter(
        driver="mock-dmm",
        address__startswith="mock://",
    ):
        instrument.address = instrument.address.replace(
            "mock://",
            "mock-dmm://",
            1,
        )
        instrument.save(update_fields=["address"])


def restore_mock_dmm_addresses(apps, schema_editor):
    """Restore the former Mock DMM address scheme."""
    Instrument = apps.get_model("main", "Instrument")
    for instrument in Instrument.objects.filter(
        driver="mock-dmm",
        address__startswith="mock-dmm://",
    ):
        instrument.address = instrument.address.replace(
            "mock-dmm://",
            "mock://",
            1,
        )
        instrument.save(update_fields=["address"])


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0013_rename_mock_driver_to_mock_dmm"),
    ]

    operations = [
        migrations.RunPython(
            rename_mock_dmm_addresses,
            restore_mock_dmm_addresses,
        ),
        migrations.AlterField(
            model_name="instrument",
            name="address",
            field=models.CharField(
                help_text=(
                    "Device path such as /dev/ttyUSB0 or /dev/usbtmc0, "
                    "mock-dmm://default, or mock-psu://default."
                ),
                max_length=255,
            ),
        ),
    ]
