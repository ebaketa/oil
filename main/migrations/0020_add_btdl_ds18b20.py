from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("main", "0019_alter_instrument_driver")]

    operations = [
        migrations.AlterField(
            model_name="instrument",
            name="driver",
            field=models.CharField(
                choices=[
                    ("agilent_34401a", "Agilent 34401A"),
                    ("btdl_ntc", "Baketa BTDL-NTC"),
                    ("btdl_ds18b20", "Baketa BTDL-DS18B20"),
                    ("keysight_34461a", "Keysight 34461A"),
                    ("mock-dmm", "Mock DMM"),
                    ("mock_dc_power_supply", "Mock DC Power Supply"),
                    ("mock_rnd_320_3005p", "Mock RND Lab 320-3005P"),
                    ("rnd_ka3005p", "RND Lab 320-KA3005P"),
                    ("rpi_cpu_temperature", "Raspberry Pi CPU Temperature"),
                ],
                max_length=32,
            ),
        ),
    ]
