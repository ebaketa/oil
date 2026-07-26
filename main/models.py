"""Database models for the OIL application."""

from django.conf import settings
from django.db import models


class UserPreference(models.Model):
    """Store interface preferences for an OIL user."""

    class Theme(models.TextChoices):
        """Available interface colour themes."""

        BLUE = "blue", "Blue"
        RED = "red", "Red"
        GREEN = "green", "Green"
        YELLOW = "yellow", "Yellow"
        ORANGE = "orange", "Orange"
        PURPLE = "purple", "Purple"
        TEAL = "teal", "Teal"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="oil_preferences",
    )
    theme = models.CharField(
        max_length=16,
        choices=Theme.choices,
        default=Theme.BLUE,
    )

    def __str__(self):
        """Return a readable representation of the preferences."""
        return f"{self.user}: {self.get_theme_display()}"
