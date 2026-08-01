from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0010_tasksample_status_tasksample_error"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tasksample",
            name="status",
            field=models.CharField(
                choices=[
                    ("acquiring", "Acquiring"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                ],
                default="completed",
                max_length=16,
            ),
        ),
    ]
