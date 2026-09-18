from django.db import migrations, models
from django.db.models import Count


def populate_sample_counts(apps, schema_editor):
    AutomationTask = apps.get_model("tasks", "AutomationTask")
    TaskSample = apps.get_model("tasks", "TaskSample")
    counts = (
        TaskSample.objects.exclude(status="acquiring")
        .values("task_id")
        .annotate(total=Count("id"))
    )
    for row in counts.iterator():
        AutomationTask.objects.filter(pk=row["task_id"]).update(
            sample_count=row["total"],
        )


class Migration(migrations.Migration):
    dependencies = [("tasks", "0011_alter_tasksample_status")]

    operations = [
        migrations.AddField(
            model_name="automationtask",
            name="sample_count",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.RunPython(populate_sample_counts, migrations.RunPython.noop),
    ]
