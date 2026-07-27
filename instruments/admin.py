"""Django admin configuration for laboratory instruments."""

from django.contrib import admin

from .models import Instrument


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    """Display laboratory instruments in Django admin."""

    list_display = ("name", "manufacturer", "model_name", "driver", "status")
    list_filter = ("driver", "status", "manufacturer")
    search_fields = ("name", "manufacturer", "model_name", "serial_number")
