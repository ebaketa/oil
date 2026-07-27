"""Django application configuration for accounts."""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configure account profile functionality."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
