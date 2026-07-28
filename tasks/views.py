"""Views for measurement tasks."""

from django.contrib.auth.decorators import login_required
import json
import csv
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from instruments.models import Instrument
from measurements.exports import safe_spreadsheet_text

from .forms import TaskBuilderForm
from .models import AutomationTask, TaskInstrument
from .runner import TaskRunner


class CsvEcho:
    """Return CSV writer output directly for streaming responses."""

    def write(self, value):
        return value


def _serialize_task(task, *, include_samples=False):
    """Return one task and optionally its stored samples."""
    task_instruments = list(
        task.task_instruments.select_related("instrument").all(),
    )
    serialized_instruments = [
        {
            "assignment_id": assignment.pk,
            "instrument_id": assignment.instrument_id,
            "name": assignment.instrument.name,
            "driver": assignment.instrument.get_driver_display(),
            "configuration": assignment.configuration,
        }
        for assignment in task_instruments
    ]
    if not serialized_instruments:
        for assignment_id, instrument in (
            ("legacy-psu", task.power_supply),
            ("legacy-voltage", task.voltage_meter),
            ("legacy-temperature", task.temperature_meter),
        ):
            if instrument is not None:
                serialized_instruments.append(
                    {
                        "assignment_id": assignment_id,
                        "instrument_id": instrument.pk,
                        "name": instrument.name,
                        "driver": instrument.get_driver_display(),
                        "configuration": {},
                    },
                )

    payload = {
        "id": task.pk,
        "name": task.name,
        "status": task.status,
        "status_label": task.get_status_display(),
        "power_supply": (
            task.power_supply.name if task.power_supply else "No power supply"
        ),
        "voltage_meter": (
            task.voltage_meter.name if task.voltage_meter else None
        ),
        "temperature_meter": (
            task.temperature_meter.name if task.temperature_meter else None
        ),
        "voltage_mode": task.get_voltage_mode_display(),
        "voltage_source": task.get_voltage_source_display(),
        "start_voltage": str(task.start_voltage),
        "stop_voltage": str(task.stop_voltage),
        "voltage_step": str(task.voltage_step),
        "interval_seconds": task.interval_seconds,
        "sample_count": getattr(task, "sample_count", task.samples.count()),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": (
            task.finished_at.isoformat() if task.finished_at else None
        ),
        "error": task.error,
        "instruments": serialized_instruments,
    }
    if include_samples:
        samples = []
        for sample in task.samples.all():
            readings = [
                {
                    "instrument": reading.task_instrument.instrument.name,
                    "assignment_id": reading.task_instrument_id,
                    "parameter": reading.parameter,
                    "value": str(reading.value),
                    "unit": reading.unit,
                }
                for reading in sample.readings.all()
            ]
            if not task_instruments:
                if task.power_supply:
                    readings.append(
                        {
                            "instrument": task.power_supply.name,
                            "assignment_id": "legacy-psu",
                            "parameter": "Voltage setpoint",
                            "value": str(sample.voltage_setpoint),
                            "unit": "V",
                        },
                    )
                if task.voltage_meter and sample.measured_voltage is not None:
                    readings.append(
                        {
                            "instrument": task.voltage_meter.name,
                            "assignment_id": "legacy-voltage",
                            "parameter": "Voltage DC",
                            "value": str(sample.measured_voltage),
                            "unit": "V",
                        },
                    )
                if task.temperature_meter and sample.temperature is not None:
                    readings.append(
                        {
                            "instrument": task.temperature_meter.name,
                            "assignment_id": "legacy-temperature",
                            "parameter": "Temperature",
                            "value": str(sample.temperature),
                            "unit": "°C",
                        },
                    )
            samples.append(
                {
                "index": sample.index,
                "voltage_setpoint": str(sample.voltage_setpoint),
                "measured_voltage": (
                    str(sample.measured_voltage)
                    if sample.measured_voltage is not None
                    else None
                ),
                "temperature": (
                    str(sample.temperature)
                    if sample.temperature is not None
                    else None
                ),
                "timestamp": sample.timestamp.isoformat(),
                "readings": readings,
                },
            )
        payload["samples"] = samples
    return payload


@login_required
def task_list(request):
    """Render the Tasks workspace."""
    saved_tasks = (
        AutomationTask.objects.filter(user=request.user)
        .select_related(
            "power_supply",
            "voltage_meter",
            "temperature_meter",
        )
        .annotate(
            sample_count=Count("samples"),
        )
    )
    available_instruments = []
    for instrument in Instrument.objects.all():
        available_instruments.append(
            {
                "id": instrument.pk,
                "name": str(instrument),
                "driver": instrument.driver,
                "driver_label": instrument.get_driver_display(),
                "capabilities": {
                    name: {
                        "label": capability.label,
                        "unit": capability.unit,
                    }
                    for name, capability in instrument.capabilities.items()
                },
            },
        )
    return render(
        request,
        "tasks/task_list.html",
        {
            "saved_tasks": saved_tasks,
            "task_status_choices": AutomationTask.Status.choices,
            "task_form": TaskBuilderForm(),
            "available_instruments": available_instruments,
        },
    )


@login_required
@require_POST
def task_create(request):
    """Validate, persist, and schedule an automation task."""
    form = TaskBuilderForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    try:
        submitted_instruments = json.loads(request.POST.get("instruments", ""))
    except json.JSONDecodeError:
        submitted_instruments = None
    if not isinstance(submitted_instruments, list) or not submitted_instruments:
        return JsonResponse(
            {"error": "Add at least one instrument to the task."},
            status=400,
        )

    instrument_ids = [item.get("instrument_id") for item in submitted_instruments]
    if (
        any(not isinstance(pk, int) for pk in instrument_ids)
        or len(set(instrument_ids)) != len(instrument_ids)
    ):
        return JsonResponse(
            {"error": "Task instruments must be valid and unique."},
            status=400,
        )
    instrument_map = Instrument.objects.in_bulk(instrument_ids)
    if len(instrument_map) != len(instrument_ids):
        return JsonResponse({"error": "An instrument was not found."}, status=400)

    normalized = []
    try:
        for order, item in enumerate(submitted_instruments):
            instrument = instrument_map[item["instrument_id"]]
            config = item.get("configuration", {})
            if instrument.driver == Instrument.Driver.MOCK_DC_POWER_SUPPLY:
                mode = config.get("mode")
                if mode not in AutomationTask.VoltageMode.values:
                    raise ValueError("Select a valid power supply mode.")
                for name in ("start_voltage", "stop_voltage", "voltage_step"):
                    value = Decimal(str(config.get(name)))
                    if name == "voltage_step":
                        if not Decimal("0.001") <= value <= Decimal("60"):
                            raise ValueError("Voltage step must be 0.001–60 V.")
                    elif not Decimal("0") <= value <= Decimal("60"):
                        raise ValueError("Voltage must be 0–60 V.")
                    config[name] = str(value)
                config["cycle_count"] = int(config.get("cycle_count", 1))
                if not 1 <= config["cycle_count"] <= 100:
                    raise ValueError("Cycle count must be 1–100.")
                start = Decimal(config["start_voltage"])
                stop = Decimal(config["stop_voltage"])
                step = Decimal(config["voltage_step"])
                if mode != AutomationTask.VoltageMode.FIXED and start == stop:
                    raise ValueError(
                        "Sweep and Cycle require different voltages.",
                    )
                approximate_steps = int(abs(stop - start) / step) + 2
                multiplier = (
                    config["cycle_count"] * 2
                    if mode == AutomationTask.VoltageMode.CYCLE
                    else 1
                )
                if approximate_steps * multiplier > 10000:
                    raise ValueError(
                        "Power supply program exceeds 10,000 steps.",
                    )
            elif instrument.capabilities:
                function = config.get("function")
                if function not in instrument.capabilities:
                    raise ValueError("Select a supported DMM function.")
                source = config.get("source", "external")
                if source not in AutomationTask.VoltageSource.values:
                    raise ValueError("Select a valid measurement source.")
                if (
                    source == AutomationTask.VoltageSource.VIRTUAL
                    and instrument.driver != Instrument.Driver.MOCK
                ):
                    raise ValueError(
                        "Only a Mock DMM can use a virtual source.",
                    )
                config["source"] = source
                if function == "temperature":
                    minimum = Decimal(str(config.get("minimum")))
                    maximum = Decimal(str(config.get("maximum")))
                    resolution = Decimal(str(config.get("resolution")))
                    if minimum >= maximum or resolution <= 0:
                        raise ValueError("Temperature range is invalid.")
                    config.update(
                        minimum=str(minimum),
                        maximum=str(maximum),
                        resolution=str(resolution),
                        seed=int(config.get("seed", 1)),
                    )
            else:
                raise ValueError(
                    "This driver is not yet supported by the Task builder.",
                )
            normalized.append((order, instrument, config))
    except (ValueError, TypeError, InvalidOperation) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    power_supplies = [
        instrument
        for _order, instrument, _config in normalized
        if instrument.driver == Instrument.Driver.MOCK_DC_POWER_SUPPLY
    ]
    if len(power_supplies) > 1:
        return JsonResponse(
            {"error": "A task currently supports one power supply."},
            status=400,
        )
    has_virtual_meter = any(
        config.get("source") == AutomationTask.VoltageSource.VIRTUAL
        for _order, instrument, config in normalized
        if instrument.driver == Instrument.Driver.MOCK
        and config.get("function") == "dc_voltage"
    )
    if has_virtual_meter and not power_supplies:
        return JsonResponse(
            {"error": "Virtual voltage measurement requires a Mock PSU."},
            status=400,
        )

    instruments = set(instrument_ids)
    active_tasks = AutomationTask.objects.filter(
        status__in=(
            AutomationTask.Status.PENDING,
            AutomationTask.Status.RUNNING,
        ),
    )
    busy = active_tasks.filter(
        Q(power_supply_id__in=instruments)
        | Q(voltage_meter_id__in=instruments)
        | Q(temperature_meter_id__in=instruments)
        | Q(task_instruments__instrument_id__in=instruments)
    ).distinct().exists()
    if busy:
        return JsonResponse(
            {"error": "A selected instrument already has an active task."},
            status=409,
        )

    power_supply = power_supplies[0] if power_supplies else None
    with transaction.atomic():
        task = AutomationTask.objects.create(
            user=request.user,
            name=form.cleaned_data["name"],
            interval_seconds=form.cleaned_data["interval_seconds"],
            requested_samples=form.cleaned_data["requested_samples"],
            power_supply=power_supply,
        )
        TaskInstrument.objects.bulk_create(
            [
                TaskInstrument(
                    task=task,
                    instrument=instrument,
                    order=order,
                    configuration=config,
                )
                for order, instrument, config in normalized
            ],
        )
    TaskRunner.start(task.pk)
    return JsonResponse(_serialize_task(task), status=201)


@login_required
@require_GET
def task_detail(request, pk):
    """Return one owned task with all currently stored samples."""
    try:
        task = (
            AutomationTask.objects.select_related(
                "power_supply",
                "voltage_meter",
                "temperature_meter",
            )
            .prefetch_related("samples")
            .prefetch_related(
                "samples__readings__task_instrument__instrument",
            )
            .get(pk=pk, user=request.user)
        )
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    return JsonResponse(_serialize_task(task, include_samples=True))


@login_required
@require_POST
def task_stop(request, pk):
    """Request an owned running task to stop."""
    try:
        task = AutomationTask.objects.get(pk=pk, user=request.user)
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    if task.status not in (
        AutomationTask.Status.PENDING,
        AutomationTask.Status.RUNNING,
    ):
        return JsonResponse(
            {"error": "Task is not active."},
            status=409,
        )
    TaskRunner.stop(task.pk)
    return JsonResponse({"stopping": True})


@login_required
@require_GET
def task_export_csv(request, pk):
    """Export one owned task as a pivoted instrument-results CSV."""
    try:
        task = (
            AutomationTask.objects.prefetch_related(
                "task_instruments__instrument",
                "samples__readings__task_instrument__instrument",
            )
            .get(pk=pk, user=request.user)
        )
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)

    assignments = list(task.task_instruments.all())
    columns = [
        (assignment.pk, assignment.instrument.name)
        for assignment in assignments
    ]
    if not columns:
        columns = [
            (key, instrument.name)
            for key, instrument in (
                ("legacy-psu", task.power_supply),
                ("legacy-voltage", task.voltage_meter),
                ("legacy-temperature", task.temperature_meter),
            )
            if instrument is not None
        ]
    writer = csv.writer(CsvEcho(), lineterminator="\r\n")

    def rows():
        yield "\ufeff"
        yield writer.writerow(
            (
                "Time",
                *(
                    safe_spreadsheet_text(instrument_name)
                    for _key, instrument_name in columns
                ),
            ),
        )
        for sample in task.samples.all():
            readings = {
                reading.task_instrument_id: reading
                for reading in sample.readings.all()
            }
            if not assignments:
                legacy_values = {
                    "legacy-psu": (
                        f"{sample.voltage_setpoint} V"
                        if task.power_supply
                        else ""
                    ),
                    "legacy-voltage": (
                        f"{sample.measured_voltage} V"
                        if sample.measured_voltage is not None
                        else ""
                    ),
                    "legacy-temperature": (
                        f"{sample.temperature} °C"
                        if sample.temperature is not None
                        else ""
                    ),
                }
            yield writer.writerow(
                (
                    timezone.localtime(sample.timestamp).strftime(
                        "%d.%m.%Y %H:%M:%S",
                    ),
                    *(
                        (
                            f"{readings[key].value} {readings[key].unit}"
                            if key in readings
                            else legacy_values.get(key, "")
                            if not assignments
                            else ""
                        )
                        for key, _instrument_name in columns
                    ),
                ),
            )

    response = StreamingHttpResponse(
        rows(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="task-{task.pk}.csv"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
