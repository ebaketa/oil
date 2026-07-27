"""Django application configuration for the JSON API."""

from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Configure the OIL JSON API."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "api"
