from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0008_automationtask_start_delay_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="tasksample",
            name="acquisition_time_seconds",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=10,
                null=True,
            ),
        ),
    ]
