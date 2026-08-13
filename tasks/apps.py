"""Django application configuration for measurement tasks."""

import os

from django.apps import AppConfig


class TasksConfig(AppConfig):
    """Configure the Task application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "tasks"
    verbose_name = "Tasks"

    def ready(self):
        """Resume interrupted workers only in the designated server process."""
        if os.environ.get("OIL_RECOVER_TASKS") != "1":
            return
        from .runner import TaskRunner

        TaskRunner.recover_active_tasks()
