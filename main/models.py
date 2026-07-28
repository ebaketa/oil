"""Database models for the OIL application."""

from django.conf import settings
from django.core.validators import MinValueValidator
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

    class SidebarPosition(models.TextChoices):
        """Available horizontal sidebar positions."""

        LEFT = "left", "Left"
        RIGHT = "right", "Right"

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
    show_top_navigation = models.BooleanField(default=True)
    show_sidebar = models.BooleanField(default=True)
    sidebar_position = models.CharField(
        max_length=8,
        choices=SidebarPosition.choices,
        default=SidebarPosition.LEFT,
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
        MOCK = "mock", "Mock instrument"
        MOCK_DC_POWER_SUPPLY = (
            "mock_dc_power_supply",
            "Mock DC Power Supply",
        )

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
        help_text=(
            "Device path such as /dev/ttyUSB0 or /dev/usbtmc0, "
            "mock://default, or mock-psu://default."
        ),
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
    def capabilities(self):
        """Return capabilities published by the configured driver."""
        from drivers.registry import DriverRegistry

        return DriverRegistry.capabilities(self.driver)

    def supports_function(self, function: str) -> bool:
        """Return whether the configured driver supports a function."""
        return function in self.capabilities

    @property
    def status_badge(self):
        """Return the Bootstrap badge colour for the current status."""
        return {
            self.Status.REACHABLE: "success",
            self.Status.OFFLINE: "secondary",
            self.Status.ERROR: "danger",
        }.get(self.status, "secondary")


class MeasurementRun(models.Model):
    """Store the lifecycle and configuration of one measurement series."""

    class Function(models.TextChoices):
        """Measurement functions currently supported by OIL."""

        DC_VOLTAGE = "dc_voltage", "DC voltage"
        AC_VOLTAGE = "ac_voltage", "AC voltage"
        DC_CURRENT = "dc_current", "DC current"
        AC_CURRENT = "ac_current", "AC current"
        RESISTANCE = "resistance", "Resistance"
        TEMPERATURE = "temperature", "Temperature"

    class Mode(models.TextChoices):
        """Supported measurement acquisition modes."""

        SINGLE = "single", "Single"
        CONTINUOUS = "continuous", "Continuous"
        LOOP = "loop", "Loop"

    class Status(models.TextChoices):
        """Lifecycle states for a measurement run."""

        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        STOPPED = "stopped", "Stopped"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="measurement_runs",
    )
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="measurement_runs",
    )
    function = models.CharField(max_length=50, choices=Function.choices)
    mode = models.CharField(max_length=16, choices=Mode.choices)
    interval = models.FloatField(
        null=True,
        blank=True,
        validators=(MinValueValidator(0.1),),
        help_text="Seconds between readings.",
    )
    requested_count = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=(MinValueValidator(1),),
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        """Show the most recently started runs first."""

        ordering = ("-started_at", "-pk")

    def __str__(self):
        """Return a readable run summary."""
        return (
            f"{self.get_mode_display()} {self.get_function_display()} "
            f"on {self.instrument.name}"
        )


class Measurement(models.Model):
    """Store one normalized reading returned by an instrument driver."""

    run = models.ForeignKey(
        MeasurementRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="measurements",
    )
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
