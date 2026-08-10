from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0015_alter_instrument_driver")]

    operations = [
        migrations.AlterField(
            model_name="instrument",
            name="address",
            field=models.CharField(
                help_text=(
                    "Device path such as /dev/ttyUSB0 or /dev/usbtmc0, "
                    "mock-dmm://default, mock-psu://default, or "
                    "mock-rnd-psu://default."
                ),
                max_length=255,
            ),
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
                    ("mock_rnd_320_3005p", "Mock RND Lab 320-3005P"),
                    ("rnd_ka3005p", "RND Lab 320-KA3005P"),
                ],
                max_length=32,
            ),
        ),
    ]
