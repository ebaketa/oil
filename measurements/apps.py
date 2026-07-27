"""Django application configuration for measurements."""

from django.apps import AppConfig


class MeasurementsConfig(AppConfig):
    """Configure measurement workflow functionality."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "measurements"
