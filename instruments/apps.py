"""Django application configuration for instruments."""

from django.apps import AppConfig


class InstrumentsConfig(AppConfig):
    """Configure instrument inventory functionality."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "instruments"
