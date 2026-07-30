"""Admin configuration for automation tasks."""

from django.contrib import admin

from .models import (
    AutomationTask,
    TaskInstrument,
    TaskReading,
    TaskSample,
)


class TaskSampleInline(admin.TabularInline):
    """Show stored samples within an automation task."""

    model = TaskSample
    extra = 0
    readonly_fields = (
        "index",
        "voltage_setpoint",
        "measured_voltage",
        "temperature",
        "timestamp",
    )


class TaskInstrumentInline(admin.TabularInline):
    """Show selected instruments and their JSON configuration."""

    model = TaskInstrument
    extra = 0


@admin.register(AutomationTask)
class AutomationTaskAdmin(admin.ModelAdmin):
    """Inspect persistent task configuration and lifecycle."""

    list_display = (
        "name",
        "user",
        "measurement_mode",
        "power_supply",
        "voltage_mode",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        "measurement_mode",
        "voltage_mode",
        "voltage_source",
    )
    search_fields = ("name", "description", "user__username")
    inlines = (TaskInstrumentInline, TaskSampleInline)


admin.site.register(TaskReading)
