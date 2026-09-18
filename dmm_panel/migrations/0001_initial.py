import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("main", "0018_light_and_dark_themes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PanelLease",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("owner_token", models.CharField(max_length=64)),
                ("last_seen", models.DateTimeField()),
                ("latest_status", models.JSONField(blank=True, default=dict)),
                (
                    "instrument",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="panel_lease",
                        to="main.instrument",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
