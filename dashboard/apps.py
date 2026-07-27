"""Django application configuration for the dashboard."""

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """Configure dashboard and informational pages."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"
