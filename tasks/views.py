"""Views for measurement tasks."""

from django.contrib.auth.decorators import login_required
import json
import csv
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max, Min, Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from instruments.models import Instrument
from measurements.exports import safe_spreadsheet_text

from .forms import TaskBuilderForm
from .models import AutomationTask, TaskInstrument, TaskSample
from .runner import TaskRunner


class CsvEcho:
    """Return CSV writer output directly for streaming responses."""

    def write(self, value):
        return value


def _voltage_decimal_places(instrument):
    """Return the voltage precision published by a power-supply driver."""
    limits = instrument.power_supply_voltage_limits
    if limits is None:
        return None
    return max(0, -limits["step"].as_tuple().exponent)


def _serialize_task(task, *, include_samples=False, samples_queryset=None):
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
            "voltage_decimals": _voltage_decimal_places(
                assignment.instrument,
            ),
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
                        "voltage_decimals": _voltage_decimal_places(
                            instrument,
                        ),
                    },
                )

    result_columns = []
    for instrument in serialized_instruments:
        configuration = instrument["configuration"]
        if configuration.get("readback_voltage", False):
            result_columns.extend(
                (
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": "Voltage setpoint",
                        "label": f'{instrument["name"]} — Set voltage',
                        "decimals": instrument["voltage_decimals"],
                    },
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": "Output voltage readback",
                        "label": f'{instrument["name"]} — Read voltage',
                        "decimals": instrument["voltage_decimals"],
                    },
                ),
            )
        else:
            result_columns.append(
                {
                    "assignment_id": instrument["assignment_id"],
                    "parameter": None,
                    "label": instrument["name"],
                    "decimals": instrument["voltage_decimals"],
                },
            )

    payload = {
        "id": task.pk,
        "name": task.name,
        "description": task.description,
        "measurement_mode": task.measurement_mode,
        "measurement_mode_label": task.get_measurement_mode_display(),
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
        "start_delay_seconds": task.start_delay_seconds,
        "trigger_period": {
            "hours": int(task.interval_seconds // 3600),
            "minutes": int(task.interval_seconds % 3600 // 60),
            "seconds": int(task.interval_seconds % 60),
            "hundredths": int(round(task.interval_seconds * 100)) % 100,
        },
        "sample_count": getattr(
            task,
            "sample_count",
            task.samples.exclude(status=TaskSample.Status.ACQUIRING).count(),
        ),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": (
            task.finished_at.isoformat() if task.finished_at else None
        ),
        "error": task.error,
        "instruments": serialized_instruments,
        "result_columns": result_columns,
    }
    if include_samples:
        samples = []
        recent_samples = samples_queryset
        if recent_samples is None:
            recent_samples = task.samples.exclude(
                status=TaskSample.Status.ACQUIRING,
            ).order_by("-index")[:200]
        recent_samples = recent_samples.prefetch_related(
            "readings__task_instrument__instrument",
        )
        for sample in recent_samples:
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
                "status": sample.status,
                "error": sample.error,
                "acquisition_time_seconds": (
                    str(sample.acquisition_time_seconds)
                    if sample.acquisition_time_seconds is not None
                    else None
                ),
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
            sample_count=Count(
                "samples",
                filter=~Q(samples__status=TaskSample.Status.ACQUIRING),
            ),
        )
        .order_by("-created_at", "-pk")
    )
    available_instruments = []
    for instrument in Instrument.objects.all():
        available_instruments.append(
            {
                "id": instrument.pk,
                "name": str(instrument),
                "driver": instrument.driver,
                "driver_label": instrument.get_driver_display(),
                "is_power_supply": instrument.is_power_supply,
                "voltage_limits": (
                    {
                        name: str(value)
                        for name, value in (
                            instrument.power_supply_voltage_limits or {}
                        ).items()
                    }
                ),
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
            if instrument.is_power_supply:
                limits = instrument.power_supply_voltage_limits
                mode = config.get("mode")
                if mode not in AutomationTask.VoltageMode.values:
                    raise ValueError("Select a valid power supply mode.")
                for name in ("start_voltage", "stop_voltage", "voltage_step"):
                    value = Decimal(str(config.get(name)))
                    if name == "voltage_step":
                        if not limits["step"] <= value <= limits["maximum"]:
                            raise ValueError(
                                "Voltage step is outside the driver's range.",
                            )
                    elif not limits["minimum"] <= value <= limits["maximum"]:
                        raise ValueError(
                            "Voltage is outside the driver's range.",
                        )
                    config[name] = str(value)
                config["cycle_count"] = int(config.get("cycle_count", 1))
                if not 1 <= config["cycle_count"] <= 100:
                    raise ValueError("Cycle count must be 1–100.")
                readback_voltage = config.get("readback_voltage", False)
                if readback_voltage in (True, "true"):
                    readback_voltage = True
                elif readback_voltage in (False, "false"):
                    readback_voltage = False
                else:
                    raise ValueError("Select a valid voltage readback option.")
                config["readback_voltage"] = readback_voltage
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
                display_off = config.get("display_off", False)
                if display_off in (True, "true"):
                    display_off = True
                elif display_off in (False, "false"):
                    display_off = False
                else:
                    raise ValueError("Select a valid display option.")
                if (
                    display_off
                    and instrument.driver not in (
                        Instrument.Driver.AGILENT_34401A,
                        Instrument.Driver.KEYSIGHT_34461A,
                    )
                ):
                    raise ValueError(
                        "Display control is only available for Agilent 34401A "
                        "and Keysight 34461A.",
                    )
                config["display_off"] = display_off
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
        if instrument.is_power_supply
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
    has_mock_supply = any(
        instrument.driver == Instrument.Driver.MOCK_DC_POWER_SUPPLY
        for instrument in power_supplies
    )
    if has_virtual_meter and not has_mock_supply:
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
            description=form.cleaned_data["description"],
            measurement_mode=form.cleaned_data["measurement_mode"],
            interval_seconds=form.cleaned_data["interval_seconds"],
            start_delay_seconds=form.cleaned_data["start_delay_seconds"],
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
            .get(pk=pk, user=request.user)
        )
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    return JsonResponse(_serialize_task(task, include_samples=True))


@login_required
@require_GET
def task_chart_data(request, pk):
    """Return a bounded, evenly sampled time range for a task chart."""
    try:
        task = AutomationTask.objects.get(pk=pk, user=request.user)
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)

    range_name = request.GET.get("range", "hour")
    range_seconds = {
        "hour": 3600,
        "day": 86400,
        "week": 604800,
        "month": 2592000,
        "year": 31536000,
        "all": None,
    }
    if range_name not in range_seconds:
        return JsonResponse({"error": "Invalid chart range."}, status=400)

    samples = task.samples.exclude(status=TaskSample.Status.ACQUIRING)
    latest_timestamp = samples.aggregate(latest=Max("timestamp"))["latest"]
    seconds = range_seconds[range_name]
    if latest_timestamp is not None and seconds is not None:
        samples = samples.filter(
            timestamp__gte=latest_timestamp - timedelta(seconds=seconds),
        )

    summary = samples.aggregate(
        count=Count("id"),
        first_index=Min("index"),
        last_index=Max("index"),
    )
    if summary["count"] > 1000:
        first_index = summary["first_index"]
        last_index = summary["last_index"]
        span = last_index - first_index
        selected_indices = {
            round(first_index + span * position / 999)
            for position in range(1000)
        }
        samples = samples.filter(index__in=selected_indices)

    payload = _serialize_task(
        task,
        include_samples=True,
        samples_queryset=samples.order_by("index"),
    )
    return JsonResponse(
        {
            "range": range_name,
            "sample_count": summary["count"],
            "samples": payload["samples"],
            "result_columns": payload["result_columns"],
        },
    )


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
@require_POST
def task_complete(request, pk):
    """Mark one owned stopped task as completed."""
    try:
        task = AutomationTask.objects.get(pk=pk, user=request.user)
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    if task.status != AutomationTask.Status.STOPPED:
        return JsonResponse(
            {"error": "Only a stopped task can be marked as completed."},
            status=409,
        )
    task.status = AutomationTask.Status.COMPLETED
    task.save(update_fields=("status",))
    return JsonResponse(_serialize_task(task, include_samples=True))


@login_required
@require_POST
def task_delete(request, pk):
    """Permanently delete one owned inactive task."""
    try:
        task = AutomationTask.objects.get(pk=pk, user=request.user)
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    if task.status in (
        AutomationTask.Status.PENDING,
        AutomationTask.Status.RUNNING,
    ):
        return JsonResponse(
            {"error": "Stop the active task before deleting it."},
            status=409,
        )
    task.delete()
    return JsonResponse({"deleted": True, "id": pk})


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
    columns = []
    for assignment in assignments:
        if assignment.configuration.get("readback_voltage", False):
            columns.extend(
                (
                    (
                        assignment.pk,
                        "Voltage setpoint",
                        f"{assignment.instrument.name} — Set voltage",
                        _voltage_decimal_places(assignment.instrument),
                    ),
                    (
                        assignment.pk,
                        "Output voltage readback",
                        f"{assignment.instrument.name} — Read voltage",
                        _voltage_decimal_places(assignment.instrument),
                    ),
                ),
            )
        else:
            columns.append(
                (
                    assignment.pk,
                    None,
                    assignment.instrument.name,
                    _voltage_decimal_places(assignment.instrument),
                ),
            )
    if not columns:
        columns = [
            (key, None, instrument.name, None)
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
                    for _key, _parameter, instrument_name, _decimals in columns
                ),
            ),
        )
        for sample in task.samples.exclude(
            status=TaskSample.Status.ACQUIRING,
        ):
            sample_readings = list(sample.readings.all())
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
                        next(
                            (
                                f'{reading.value:.{decimals}f} {reading.unit}'
                                if decimals is not None
                                else f"{reading.value} {reading.unit}"
                                for reading in sample_readings
                                if reading.task_instrument_id == key
                                and (
                                    parameter is None
                                    or reading.parameter == parameter
                                )
                            ),
                            legacy_values.get(key, "")
                            if not assignments
                            else "",
                        )
                        for key, parameter, _instrument_name, decimals in columns
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
