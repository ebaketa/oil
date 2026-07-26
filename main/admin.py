"""Admin configuration for the OIL application."""

from django.contrib import admin

from .models import Instrument, UserPreference


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

# Register your models here.
