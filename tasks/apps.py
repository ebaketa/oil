"""Django application configuration for measurement tasks."""

from django.apps import AppConfig


class TasksConfig(AppConfig):
    """Configure the Task application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"
    verbose_name = "Tasks"
