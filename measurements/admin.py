"""Django admin configuration for measurements and runs."""

from django.contrib import admin

from .models import Measurement, MeasurementRun


@admin.register(Measurement)
class MeasurementAdmin(admin.ModelAdmin):
    """Display captured measurements in Django admin."""

    list_display = (
        "instrument",
        "run",
        "parameter",
        "value",
        "unit",
        "timestamp",
    )
    list_filter = ("parameter", "unit", "timestamp")
    search_fields = ("instrument__name", "parameter", "notes")
    ordering = ("-timestamp",)


@admin.register(MeasurementRun)
class MeasurementRunAdmin(admin.ModelAdmin):
    """Display measurement run lifecycle and configuration in Django admin."""

    list_display = (
        "id",
        "instrument",
        "user",
        "function",
        "mode",
        "status",
        "started_at",
        "stopped_at",
    )
    list_filter = ("function", "mode", "status", "started_at")
    search_fields = (
        "instrument__name",
        "user__username",
        "notes",
        "error",
    )
    ordering = ("-started_at", "-pk")
