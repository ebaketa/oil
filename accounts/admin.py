"""Django admin configuration for account preferences."""

from django.contrib import admin

from .models import UserPreference


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Display user interface preferences in Django admin."""

    list_display = (
        "user",
        "theme",
        "show_top_navigation",
        "show_sidebar",
        "sidebar_position",
    )
    list_filter = (
        "theme",
        "show_top_navigation",
        "show_sidebar",
        "sidebar_position",
    )
    search_fields = ("user__username",)
