"""Views for measurement tasks."""

from django.contrib.auth.decorators import login_required
import json
import csv
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Count, Max, Min, Q
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from instruments.models import Instrument
from measurements.exports import safe_spreadsheet_text
from services.connection_manager import ConnectionManager

from .forms import TaskBuilderForm
from .bench import VirtualMockBench
from .models import AutomationTask, TaskInstrument, TaskSample
from .runner import TaskRunner


class CsvEcho:
    """Return CSV writer output directly for streaming responses."""

    def write(self, value):
        return value


BMX280_MEASUREMENTS = {
    "temperature_1": ("Temperature channel 1", "T CH1", "°C", 2),
    "pressure_1": ("Pressure channel 1", "P CH1", "hPa", 4),
    "humidity_1": ("Humidity channel 1", "RH CH1", "%RH", 2),
    "temperature_2": ("Temperature channel 2", "T CH2", "°C", 2),
    "pressure_2": ("Pressure channel 2", "P CH2", "hPa", 4),
    "humidity_2": ("Humidity channel 2", "RH CH2", "%RH", 2),
}


def _bmx280_column_label(measurement, configuration, instrument_name):
    """Build a human label from the detected sensor type, not its channel."""
    _quantity, raw_channel = measurement.rsplit("_", 1)
    parameter, fallback, _unit, _decimals = BMX280_MEASUREMENTS[measurement]
    sensor_types = configuration.get("sensor_types", {})
    sensor_type = sensor_types.get(raw_channel)
    if sensor_type not in {"BMP280", "BME280"}:
        return f"{instrument_name} — {fallback}"
    duplicate = list(sensor_types.values()).count(sensor_type) > 1
    sensor_name = f"{instrument_name} {sensor_type}"
    if duplicate:
        sensor_name += f" {BTDL_BMX280_ADDRESSES[raw_channel]}"
    quantity_label = parameter.rsplit(" channel ", 1)[0]
    return f"{sensor_name} — {quantity_label}"


BTDL_BMX280_ADDRESSES = {"1": "0x76", "2": "0x77"}
CHART_AXES = ("primary", "secondary", "axis3", "axis4", "axis5")


def _voltage_decimal_places(instrument):
    """Return the voltage precision published by a power-supply driver."""
    limits = instrument.power_supply_voltage_limits
    if limits is None:
        return None
    return max(0, -limits["step"].as_tuple().exponent)


def _measurement_decimal_places(instrument, configuration):
    """Return the configured display precision for one task instrument."""
    function = configuration.get("function")
    if instrument.driver == Instrument.Driver.BTDL_NTC:
        return 1
    if instrument.driver == Instrument.Driver.BTDL_DS18B20:
        if function == "temperature_ds1820":
            return 1
        if function == "temperature_ds18b20":
            return 1
    if instrument.driver == Instrument.Driver.BTDL_BMX280:
        if function.startswith(("temperature_", "humidity_")):
            return 2
        if function.startswith("pressure_"):
            return 4
    if instrument.driver == Instrument.Driver.RPI_CPU_TEMPERATURE:
        return 2
    return _voltage_decimal_places(instrument)


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
            "driver_name": assignment.instrument.driver,
            "configuration": assignment.configuration,
            "voltage_decimals": _voltage_decimal_places(
                assignment.instrument,
            ),
            "display_decimals": _measurement_decimal_places(
                assignment.instrument,
                assignment.configuration,
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
                        "driver_name": instrument.driver,
                        "configuration": {},
                        "voltage_decimals": _voltage_decimal_places(
                            instrument,
                        ),
                        "display_decimals": _measurement_decimal_places(
                            instrument,
                            {},
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
                        "axis": "primary",
                    },
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": "Output voltage readback",
                        "label": f'{instrument["name"]} — Read voltage',
                        "decimals": instrument["voltage_decimals"],
                        "axis": "primary",
                    },
                ),
            )
        elif configuration.get("function") == "temperatures" and instrument[
            "driver_name"
        ] == Instrument.Driver.BTDL_DS18B20:
            for parameter, short_label in (
                ("Temperature DS1820/DS18S20", "DS1820"),
                ("Temperature DS18B20", "DS18B20"),
            ):
                result_columns.append(
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": parameter,
                        "label": f'{instrument["name"]} — {short_label}',
                        "decimals": 1,
                        "axis": configuration.get("chart_axis", "primary"),
                    },
                )
        elif configuration.get("function") == "environment" and instrument[
            "driver_name"
        ] == Instrument.Driver.BTDL_BMX280:
            for measurement in configuration.get("measurements", ()):
                metadata = BMX280_MEASUREMENTS.get(measurement)
                if metadata is None:
                    continue
                parameter, _short_label, _unit, decimals = metadata
                result_columns.append(
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": parameter,
                        "label": _bmx280_column_label(
                            measurement,
                            configuration,
                            instrument["name"],
                        ),
                        "decimals": decimals,
                        "axis": configuration.get("measurement_axes", {}).get(
                            measurement,
                            configuration.get("chart_axis", "primary"),
                        ),
                    },
                )
        elif configuration.get("function") == "temperatures" and instrument[
            "driver_name"
        ] == Instrument.Driver.BTDL_BMX280:
            for channel in (1, 2):
                parameter = f"Temperature channel {channel}"
                result_columns.append(
                    {
                        "assignment_id": instrument["assignment_id"],
                        "parameter": parameter,
                        "label": f'{instrument["name"]} — CH{channel}',
                        "decimals": 2,
                        "axis": configuration.get("chart_axis", "primary"),
                    },
                )
        else:
            result_columns.append(
                {
                    "assignment_id": instrument["assignment_id"],
                    "parameter": None,
                    "label": instrument["name"],
                    "decimals": instrument["display_decimals"],
                    "axis": configuration.get("chart_axis", "primary"),
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
        "sample_count": task.sample_count,
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
            readings = []
            for reading in sample.readings.all():
                serialized_reading = {
                    "instrument": reading.task_instrument.instrument.name,
                    "assignment_id": reading.task_instrument_id,
                    "parameter": reading.parameter,
                    "value": str(reading.value),
                    "unit": reading.unit,
                }
                if (
                    reading.parameter == "Voltage DC"
                    and reading.task_instrument.instrument.driver
                    == Instrument.Driver.MOCK
                ):
                    configuration = reading.task_instrument.configuration
                    reference_voltage = (
                        sample.voltage_setpoint
                        if configuration.get("source")
                        == AutomationTask.VoltageSource.VIRTUAL
                        else reading.value
                    )
                    decimals = (
                        VirtualMockBench.voltage_decimal_places(
                            reference_voltage,
                            configuration.get(
                                "count_mode",
                                VirtualMockBench.DEFAULT_COUNT_MODE,
                            ),
                        )
                    )
                    serialized_reading["decimals"] = decimals
                    serialized_reading["value"] = format(
                        reading.value,
                        f".{decimals}f",
                    )
                if (
                    reading.parameter == "Temperature"
                    and reading.task_instrument.instrument.driver
                    == Instrument.Driver.RPI_CPU_TEMPERATURE
                ):
                    serialized_reading["decimals"] = 2
                    serialized_reading["value"] = format(
                        reading.value,
                        ".2f",
                    )
                if (
                    reading.parameter == "Temperature"
                    and reading.task_instrument.instrument.driver
                    == Instrument.Driver.BTDL_NTC
                ):
                    serialized_reading["decimals"] = 1
                    serialized_reading["value"] = format(
                        reading.value,
                        ".1f",
                    )
                readings.append(serialized_reading)
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
                "sensor_inventory_url": (
                    reverse("bmx280_sensor_inventory", args=(instrument.pk,))
                    if instrument.driver == Instrument.Driver.BTDL_BMX280
                    else None
                ),
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
@require_GET
def bmx280_sensor_inventory(request, pk):
    """Read the sensor types currently attached to one BTDL-BMx280."""
    try:
        instrument = Instrument.objects.get(
            pk=pk,
            driver=Instrument.Driver.BTDL_BMX280,
        )
    except Instrument.DoesNotExist:
        return JsonResponse({"error": "BTDL-BMx280 was not found."}, status=404)
    try:
        with ConnectionManager.session(instrument) as driver:
            sensors = driver.sensor_inventory()
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or "Could not read the BMx280 sensors."},
            status=503,
        )
    return JsonResponse({"sensors": list(sensors)})


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
                sweep_back = config.get("sweep_back", False)
                if sweep_back in (True, "true"):
                    sweep_back = True
                elif sweep_back in (False, "false"):
                    sweep_back = False
                else:
                    raise ValueError("Select a valid Sweep Back option.")
                config["sweep_back"] = (
                    sweep_back if mode == AutomationTask.VoltageMode.SWEEP else False
                )
                if mode == AutomationTask.VoltageMode.FIXED:
                    set_voltage = Decimal(
                        str(
                            config.get(
                                "set_voltage",
                                config.get("start_voltage"),
                            ),
                        ),
                    )
                    if not limits["minimum"] <= set_voltage <= limits["maximum"]:
                        raise ValueError("Voltage is outside the driver's range.")
                    if set_voltage % limits["step"] != 0:
                        raise ValueError(
                            "Voltage does not match the driver's resolution.",
                        )
                    config["set_voltage"] = str(set_voltage)
                    config["start_voltage"] = str(set_voltage)
                    config["stop_voltage"] = str(set_voltage)
                    config["voltage_step"] = str(limits["step"])
                    config["cycle_count"] = 1
                else:
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
                if instrument.driver == Instrument.Driver.MOCK_RND_320_3005P:
                    tolerance_unit = config.get("output_tolerance_unit", "mV")
                    if tolerance_unit not in ("uV", "mV", "V"):
                        raise ValueError("Select a valid output tolerance unit.")
                    tolerance_value = Decimal(
                        str(
                            config.get(
                                "output_tolerance_value",
                                config.get("output_tolerance_mv", "0"),
                            ),
                        ),
                    )
                    tolerance_mv = tolerance_value * {
                        "uV": Decimal("0.001"),
                        "mV": Decimal("1"),
                        "V": Decimal("1000"),
                    }[tolerance_unit]
                    if not tolerance_mv.is_finite() or not (
                        Decimal("0") <= tolerance_mv <= Decimal("30000")
                    ):
                        raise ValueError(
                            "Output tolerance must be between 0 and 30000 mV.",
                        )
                    config["output_tolerance_value"] = str(tolerance_value)
                    config["output_tolerance_unit"] = tolerance_unit
                    config["output_tolerance_mv"] = str(tolerance_mv)
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
                if (
                    instrument.driver == Instrument.Driver.BTDL_BMX280
                    and function == "environment"
                ):
                    measurements = config.get("measurements")
                    if not isinstance(measurements, list) or not measurements:
                        raise ValueError(
                            "Select at least one BTDL-BMx280 value to log.",
                        )
                    invalid = set(measurements) - set(BMX280_MEASUREMENTS)
                    if invalid:
                        raise ValueError("Select valid BTDL-BMx280 values.")
                    config["measurements"] = list(dict.fromkeys(measurements))
                    sensor_types = config.get("sensor_types", {})
                    if isinstance(sensor_types, str):
                        sensor_types = json.loads(sensor_types)
                    if not isinstance(sensor_types, dict) or any(
                        str(channel) not in BTDL_BMX280_ADDRESSES
                        or sensor_type not in {"BMP280", "BME280"}
                        for channel, sensor_type in sensor_types.items()
                    ):
                        raise ValueError("Invalid BTDL-BMx280 sensor inventory.")
                    config["sensor_types"] = {
                        str(channel): sensor_type
                        for channel, sensor_type in sensor_types.items()
                    }
                    measurement_axes = config.get("measurement_axes", {})
                    if not isinstance(measurement_axes, dict):
                        raise ValueError("Select valid chart Y-axes.")
                    if any(
                        axis not in CHART_AXES
                        for axis in measurement_axes.values()
                    ):
                        raise ValueError("Select valid chart Y-axes.")
                    config["measurement_axes"] = {
                        measurement: measurement_axes.get(
                            measurement,
                            "primary",
                        )
                        for measurement in config["measurements"]
                    }
                else:
                    config.pop("measurements", None)
                    config.pop("sensor_types", None)
                    config.pop("measurement_axes", None)
                if (
                    instrument.driver == Instrument.Driver.MOCK
                    and function == "dc_voltage"
                ):
                    count_mode = str(
                        config.get(
                            "count_mode",
                            VirtualMockBench.DEFAULT_COUNT_MODE,
                        ),
                    )
                    VirtualMockBench.validate_count_mode(count_mode)
                    config["count_mode"] = count_mode
                else:
                    config.pop("count_mode", None)
                if (
                    instrument.driver == Instrument.Driver.BTDL_DS18B20
                    and function in {"temperature_ds18b20", "temperatures"}
                ):
                    bits = int(config.get("ds18b20_resolution_bits", 12))
                    if bits not in (9, 10, 11, 12):
                        raise ValueError(
                            "DS18B20 resolution must be 9, 10, 11, or 12 bits.",
                        )
                    config["ds18b20_resolution_bits"] = bits
                else:
                    config.pop("ds18b20_resolution_bits", None)
                if (
                    instrument.driver in {
                        Instrument.Driver.AGILENT_34401A,
                        Instrument.Driver.KEYSIGHT_34461A,
                    }
                    and function in {"dc_voltage", "resistance"}
                ):
                    resolution = str(
                        config.get(
                            "measurement_resolution",
                            config.get("resolution", "5.5"),
                        )
                    )
                    if resolution not in {"4.5", "5.5", "6.5"}:
                        resolution = "5.5"
                    config["resolution"] = resolution
                    config.pop("measurement_resolution", None)
                elif function != "temperature":
                    config.pop("resolution", None)
                chart_axis = config.get("chart_axis", "primary")
                if chart_axis not in CHART_AXES:
                    raise ValueError("Select a valid chart Y-axis.")
                config["chart_axis"] = chart_axis
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
                if (
                    function == "temperature"
                    and instrument.driver == Instrument.Driver.MOCK
                ):
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
    has_virtual_supply = any(
        instrument.driver in (
            Instrument.Driver.MOCK_DC_POWER_SUPPLY,
            Instrument.Driver.MOCK_RND_320_3005P,
        )
        for instrument in power_supplies
    )
    if has_virtual_meter and not has_virtual_supply:
        return JsonResponse(
            {"error": "Virtual voltage measurement requires a simulated PSU."},
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
def task_restart(request, pk):
    """Resume one owned failed task after its last stored sample."""
    try:
        task = AutomationTask.objects.get(pk=pk, user=request.user)
    except AutomationTask.DoesNotExist:
        return JsonResponse({"error": "Task was not found."}, status=404)
    if task.status != AutomationTask.Status.FAILED:
        return JsonResponse(
            {"error": "Only a failed task can be restarted."},
            status=409,
        )
    instrument_ids = set(
        task.task_instruments.values_list("instrument_id", flat=True),
    )
    instrument_ids.update(
        instrument_id
        for instrument_id in (
            task.power_supply_id,
            task.voltage_meter_id,
            task.temperature_meter_id,
        )
        if instrument_id is not None
    )
    conflicting_task = AutomationTask.objects.filter(
        status__in=(
            AutomationTask.Status.PENDING,
            AutomationTask.Status.RUNNING,
        ),
    ).filter(
        Q(power_supply_id__in=instrument_ids)
        | Q(voltage_meter_id__in=instrument_ids)
        | Q(temperature_meter_id__in=instrument_ids)
        | Q(task_instruments__instrument_id__in=instrument_ids)
    ).distinct().exists()
    if conflicting_task:
        return JsonResponse(
            {"error": "A task instrument is already in use."},
            status=409,
        )
    task.status = AutomationTask.Status.PENDING
    task.error = ""
    task.finished_at = None
    task.stop_requested = False
    task.save(
        update_fields=("status", "error", "finished_at", "stop_requested"),
    )
    try:
        TaskRunner.start(task.pk, resume=True)
    except ValueError as exc:
        task.status = AutomationTask.Status.FAILED
        task.error = str(exc)
        task.finished_at = timezone.now()
        task.save(update_fields=("status", "error", "finished_at"))
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse(_serialize_task(task, include_samples=True))


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
    """Export one owned task as a European-format pivoted results CSV."""
    try:
        task = (
            AutomationTask.objects.prefetch_related(
                "task_instruments__instrument",
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
                    {
                        "key": assignment.pk,
                        "parameter": "Voltage setpoint",
                        "label": f"{assignment.instrument.name} — Set voltage",
                        "unit": "V",
                        "decimals": _voltage_decimal_places(
                            assignment.instrument,
                        ),
                        "assignment": assignment,
                    },
                    {
                        "key": assignment.pk,
                        "parameter": "Output voltage readback",
                        "label": f"{assignment.instrument.name} — Read voltage",
                        "unit": "V",
                        "decimals": _voltage_decimal_places(
                            assignment.instrument,
                        ),
                        "assignment": assignment,
                    },
                ),
            )
        elif (
            assignment.configuration.get("function") == "temperatures"
            and assignment.instrument.driver
            in {
                Instrument.Driver.BTDL_DS18B20,
                Instrument.Driver.BTDL_BMX280,
            }
        ):
            parameters = (
                (
                    "Temperature DS1820/DS18S20",
                    "Temperature DS18B20",
                )
                if assignment.instrument.driver
                == Instrument.Driver.BTDL_DS18B20
                else ("Temperature channel 1", "Temperature channel 2")
            )
            decimals = (
                1
                if assignment.instrument.driver
                == Instrument.Driver.BTDL_DS18B20
                else 2
            )
            for index, parameter in enumerate(parameters, start=1):
                short_label = (
                    ("DS1820", "DS18B20")[index - 1]
                    if assignment.instrument.driver
                    == Instrument.Driver.BTDL_DS18B20
                    else f"CH{index}"
                )
                columns.append(
                    {
                        "key": assignment.pk,
                        "parameter": parameter,
                        "label": (
                            f"{assignment.instrument.name} — {short_label}"
                        ),
                        "unit": "°C",
                        "decimals": decimals,
                        "assignment": assignment,
                    },
                )
        elif (
            assignment.configuration.get("function") == "environment"
            and assignment.instrument.driver == Instrument.Driver.BTDL_BMX280
        ):
            for measurement in assignment.configuration.get(
                "measurements",
                (),
            ):
                metadata = BMX280_MEASUREMENTS.get(measurement)
                if metadata is None:
                    continue
                parameter, _short_label, unit, decimals = metadata
                columns.append(
                    {
                        "key": assignment.pk,
                        "parameter": parameter,
                        "label": _bmx280_column_label(
                            measurement,
                            assignment.configuration,
                            assignment.instrument.name,
                        ),
                        "unit": unit,
                        "decimals": decimals,
                        "assignment": assignment,
                    },
                )
        else:
            function = assignment.configuration.get("function")
            capability = assignment.instrument.capabilities.get(function)
            columns.append(
                {
                    "key": assignment.pk,
                    "parameter": None,
                    "label": assignment.instrument.name,
                    "unit": capability.unit if capability else "",
                    "decimals": _measurement_decimal_places(
                        assignment.instrument,
                        assignment.configuration,
                    ),
                    "assignment": assignment,
                },
            )
    if not columns:
        columns = [
            {
                "key": key,
                "parameter": None,
                "label": instrument.name,
                "unit": unit,
                "decimals": decimals,
                "assignment": None,
            }
            for key, instrument, unit, decimals in (
                ("legacy-psu", task.power_supply, "V", 3),
                ("legacy-voltage", task.voltage_meter, "V", 4),
                ("legacy-temperature", task.temperature_meter, "°C", 2),
            )
            if instrument is not None
        ]
    writer = csv.writer(CsvEcho(), delimiter=";", lineterminator="\r\n")
    export_timezone = ZoneInfo("Europe/Berlin")

    def format_number(value, decimals):
        """Format one numeric CSV cell with a European decimal comma."""
        if value is None:
            return ""
        formatted = (
            f"{value:.{decimals}f}"
            if decimals is not None
            else format(value, "f")
        )
        return formatted.replace(".", ",")

    def rows():
        yield "\ufeff"
        yield writer.writerow(
            (
                "ID",
                "Time",
                "Acquisition Time (s)",
                *(
                    safe_spreadsheet_text(
                        f'{column["label"]} ({column["unit"]})'
                        if column["unit"]
                        else column["label"]
                    )
                    for column in columns
                ),
            ),
        )
        samples = (
            task.samples.exclude(status=TaskSample.Status.ACQUIRING)
            .prefetch_related("readings")
            .iterator(chunk_size=2000)
        )
        for sample in samples:
            sample_readings = list(sample.readings.all())
            if not assignments:
                legacy_values = {
                    "legacy-psu": sample.voltage_setpoint,
                    "legacy-voltage": sample.measured_voltage,
                    "legacy-temperature": sample.temperature,
                }
            exported_values = []
            for column in columns:
                reading = next(
                    (
                        candidate
                        for candidate in sample_readings
                        if candidate.task_instrument_id == column["key"]
                        and (
                            column["parameter"] is None
                            or candidate.parameter == column["parameter"]
                        )
                    ),
                    None,
                )
                value = (
                    reading.value
                    if reading is not None
                    else legacy_values.get(column["key"])
                    if not assignments
                    else None
                )
                decimals = column["decimals"]
                assignment = column["assignment"]
                if (
                    assignment is not None
                    and assignment.instrument.driver == Instrument.Driver.MOCK
                    and assignment.configuration.get("function") == "dc_voltage"
                ):
                    reference_voltage = (
                        sample.voltage_setpoint
                        if assignment.configuration.get("source") == "virtual"
                        else value
                    )
                    decimals = VirtualMockBench.voltage_decimal_places(
                        reference_voltage,
                        assignment.configuration.get(
                            "count_mode",
                            VirtualMockBench.DEFAULT_COUNT_MODE,
                        ),
                    )
                exported_values.append(format_number(value, decimals))
            yield writer.writerow(
                (
                    sample.index,
                    timezone.localtime(
                        sample.timestamp,
                        export_timezone,
                    ).isoformat(
                        timespec="milliseconds",
                    ),
                    format_number(
                        sample.acquisition_time_seconds,
                        3,
                    ),
                    *exported_values,
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
