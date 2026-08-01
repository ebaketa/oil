from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0009_tasksample_acquisition_time_seconds"),
    ]

    operations = [
        migrations.AddField(
            model_name="tasksample",
            name="error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="tasksample",
            name="status",
            field=models.CharField(
                choices=[("completed", "Completed"), ("failed", "Failed")],
                default="completed",
                max_length=16,
            ),
        ),
    ]
