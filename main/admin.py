"""Admin configuration for the OIL application."""

from django.contrib import admin

from .models import UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Display user interface preferences in Django admin."""

    list_display = ("user", "theme")
    list_filter = ("theme",)
    search_fields = ("user__username",)

# Register your models here.
