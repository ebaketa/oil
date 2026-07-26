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


class Instrument(models.Model):
    """Represent a laboratory instrument available to OIL."""

    class Driver(models.TextChoices):
        """Instrument drivers currently supplied with OIL."""

        AGILENT_34401A = "agilent_34401a", "Agilent 34401A"
        KEYSIGHT_34461A = "keysight_34461a", "Keysight 34461A"

    class Status(models.TextChoices):
        """Connection states shown in the instrument inventory."""

        OFFLINE = "offline", "Offline"
        REACHABLE = "reachable", "Reachable"
        ERROR = "error", "Error"

    name = models.CharField(max_length=100)
    manufacturer = models.CharField(max_length=100)
    model_name = models.CharField("model", max_length=100)
    serial_number = models.CharField(max_length=100, blank=True)
    driver = models.CharField(max_length=32, choices=Driver.choices)
    address = models.CharField(
        max_length=255,
        help_text="Device path such as /dev/ttyUSB0 or /dev/usbtmc0.",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    description = models.TextField(blank=True)
    last_identification = models.TextField(blank=True)
    last_driver_test_at = models.DateTimeField(null=True, blank=True)
    last_driver_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Configure instrument ordering."""

        ordering = ("manufacturer", "model_name", "name")

    def __str__(self):
        """Return the instrument's display identity."""
        return f"{self.name} ({self.manufacturer} {self.model_name})"

    @property
    def status_badge(self):
        """Return the Bootstrap badge colour for the current status."""
        return {
            self.Status.REACHABLE: "success",
            self.Status.OFFLINE: "secondary",
            self.Status.ERROR: "danger",
        }.get(self.status, "secondary")


class Measurement(models.Model):
    """Store one normalized reading returned by an instrument driver."""

    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="measurements",
    )
    parameter = models.CharField(max_length=50)
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        """Show the newest measurements first."""

        ordering = ("-timestamp",)

    def __str__(self):
        """Return a readable measurement summary."""
        return (
            f"{self.instrument.name}: {self.parameter} = "
            f"{self.value} {self.unit}"
        )
