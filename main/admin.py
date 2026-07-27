"""Admin configuration for the OIL application."""

from django.contrib import admin

from .models import Instrument, Measurement, MeasurementRun, UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Display user interface preferences in Django admin."""

    list_display = ("user", "theme")
    list_filter = ("theme",)
    search_fields = ("user__username",)


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    """Display laboratory instruments in Django admin."""

    list_display = ("name", "manufacturer", "model_name", "driver", "status")
    list_filter = ("driver", "status", "manufacturer")
    search_fields = ("name", "manufacturer", "model_name", "serial_number")


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
