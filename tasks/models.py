"""Persistent automation tasks and their sampled results."""

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from instruments.models import Instrument


class AutomationTask(models.Model):
    """Configure and track one automated virtual-bench run."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        STOPPED = "stopped", "Stopped"
        FAILED = "failed", "Failed"

    class VoltageMode(models.TextChoices):
        FIXED = "fixed", "Fixed"
        SWEEP = "sweep", "Sweep"
        CYCLE = "cycle", "Cycle"

    class VoltageSource(models.TextChoices):
        EXTERNAL = "external", "External"
        VIRTUAL = "virtual", "Virtual power supply"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="automation_tasks",
    )
    name = models.CharField(max_length=120)
    power_supply = models.ForeignKey(
        Instrument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="power_supply_tasks",
    )
    voltage_meter = models.ForeignKey(
        Instrument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="voltage_measurement_tasks",
    )
    temperature_meter = models.ForeignKey(
        Instrument,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="temperature_measurement_tasks",
    )
    voltage_mode = models.CharField(
        max_length=16,
        choices=VoltageMode.choices,
        default=VoltageMode.SWEEP,
    )
    voltage_source = models.CharField(
        max_length=16,
        choices=VoltageSource.choices,
        default=VoltageSource.VIRTUAL,
    )
    start_voltage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=0,
    )
    stop_voltage = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=0,
    )
    voltage_step = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=1,
        validators=(MinValueValidator(0.001),),
    )
    interval_seconds = models.FloatField(
        default=1,
        validators=(MinValueValidator(0.1),),
    )
    cycle_count = models.PositiveIntegerField(default=1)
    requested_samples = models.PositiveIntegerField(default=10)
    temperature_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=20,
    )
    temperature_max = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=30,
    )
    temperature_resolution = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.1,
        validators=(MinValueValidator(0.01),),
    )
    temperature_seed = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    stop_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")

    def __str__(self):
        return self.name


class TaskSample(models.Model):
    """Store one synchronized automation-task sample."""

    task = models.ForeignKey(
        AutomationTask,
        on_delete=models.CASCADE,
        related_name="samples",
    )
    index = models.PositiveIntegerField()
    voltage_setpoint = models.DecimalField(max_digits=6, decimal_places=3)
    measured_voltage = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
    )
    temperature = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("index",)
        constraints = (
            models.UniqueConstraint(
                fields=("task", "index"),
                name="tasks_unique_sample_index",
            ),
        )


class TaskInstrument(models.Model):
    """Store one selected instrument and its driver-specific task settings."""

    task = models.ForeignKey(
        AutomationTask,
        on_delete=models.CASCADE,
        related_name="task_instruments",
    )
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.PROTECT,
        related_name="automation_task_assignments",
    )
    order = models.PositiveIntegerField(default=0)
    configuration = models.JSONField(default=dict)

    class Meta:
        ordering = ("order", "pk")
        constraints = (
            models.UniqueConstraint(
                fields=("task", "instrument"),
                name="tasks_unique_instrument_per_task",
            ),
        )


class TaskReading(models.Model):
    """Store one instrument reading belonging to a synchronized sample."""

    sample = models.ForeignKey(
        TaskSample,
        on_delete=models.CASCADE,
        related_name="readings",
    )
    task_instrument = models.ForeignKey(
        TaskInstrument,
        on_delete=models.PROTECT,
        related_name="readings",
    )
    parameter = models.CharField(max_length=50)
    value = models.DecimalField(max_digits=16, decimal_places=6)
    unit = models.CharField(max_length=20)

    class Meta:
        ordering = ("task_instrument__order", "pk")
