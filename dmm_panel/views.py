"""Views for interactive DMM measurements."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Avg, Max, Min, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from main.models import Instrument
from drivers.agilent_34401a import Agilent34401ADriver
from drivers.keysight_34461a import Keysight34461ADriver
from services.connection_manager import ConnectionManager
from tasks.bench import VirtualMockBench
from tasks.models import AutomationTask, TaskReading

from .models import PanelLease


PANEL_LEASE_TIMEOUT = timedelta(seconds=10)


def _drain_driver_commands(driver):
    """Return a JSON-safe command trace when supported by the driver."""
    drain = getattr(driver, "drain_command_log", None)
    if not callable(drain):
        return []
    commands = drain()
    if not isinstance(commands, (list, tuple)):
        return []
    return [str(command) for command in commands]


def _panel_token(request):
    """Return a bounded browser-instance token from GET or POST data."""
    token = request.GET.get("panel_token") or request.POST.get("panel_token", "")
    return token if 8 <= len(token) <= 64 else ""


def _claim_panel_control(instrument, user, token):
    """Atomically claim an absent/expired lease and return its ownership."""
    now = timezone.now()
    with transaction.atomic():
        lease, _created = PanelLease.objects.get_or_create(
            instrument=instrument,
            defaults={
                "user": user,
                "owner_token": token,
                "last_seen": now,
            },
        )
        lease = PanelLease.objects.select_for_update().get(pk=lease.pk)
        expired = lease.last_seen < now - PANEL_LEASE_TIMEOUT
        owns_control = lease.owner_token == token or expired
        if owns_control:
            lease.user = user
            lease.owner_token = token
            lease.last_seen = now
            lease.save(update_fields=("user", "owner_token", "last_seen"))
        return owns_control, dict(lease.latest_status)


def _has_panel_control(instrument, token):
    """Return whether a browser token owns a live instrument lease."""
    if not token:
        return False
    return PanelLease.objects.filter(
        instrument=instrument,
        owner_token=token,
        last_seen__gte=timezone.now() - PANEL_LEASE_TIMEOUT,
    ).exists()


def _active_task(instrument):
    """Return the newest active task that owns the instrument."""
    return AutomationTask.objects.filter(
        Q(power_supply=instrument)
        | Q(voltage_meter=instrument)
        | Q(temperature_meter=instrument)
        | Q(task_instruments__instrument=instrument),
        status__in=(AutomationTask.Status.PENDING, AutomationTask.Status.RUNNING),
    ).distinct().order_by("-started_at", "-pk").first()


def _is_busy(instrument):
    return _active_task(instrument) is not None


def _dmm_or_404(pk):
    instrument = get_object_or_404(Instrument, pk=pk)
    if not instrument.capabilities:
        from django.http import Http404

        raise Http404("This instrument has no measurement functions.")
    return instrument


@login_required
@require_GET
def panel_list(request):
    """List registered instruments that provide a front panel."""
    instruments = [
        instrument
        for instrument in Instrument.objects.all()
        if instrument.capabilities
    ]
    for instrument in instruments:
        instrument.active_task = _active_task(instrument)
    active_panel_count = sum(
        instrument.active_task is not None for instrument in instruments
    )
    return render(
        request,
        "dmm_panel/panel_list.html",
        {
            "panel_instruments": instruments,
            "active_panel_count": active_panel_count,
            "available_panel_count": len(instruments) - active_panel_count,
        },
    )


def _reading_decimal_places(reading):
    """Use the same task-specific display precision as the Task workspace."""
    assignment = reading.task_instrument
    instrument = assignment.instrument
    if (
        reading.parameter == "Voltage DC"
        and instrument.driver == Instrument.Driver.MOCK
    ):
        reference_voltage = (
            reading.sample.voltage_setpoint
            if assignment.configuration.get("source")
            == AutomationTask.VoltageSource.VIRTUAL
            else reading.value
        )
        return VirtualMockBench.voltage_decimal_places(
            reference_voltage,
            assignment.configuration.get(
                "count_mode",
                VirtualMockBench.DEFAULT_COUNT_MODE,
            ),
        )
    if instrument.driver == Instrument.Driver.RPI_CPU_TEMPERATURE:
        return 2
    precision_drivers = {
        Instrument.Driver.AGILENT_34401A: Agilent34401ADriver,
        Instrument.Driver.KEYSIGHT_34461A: Keysight34461ADriver,
    }
    if (
        instrument.driver in precision_drivers
        and reading.parameter in {"Voltage DC", "Resistance"}
    ):
        driver_class = precision_drivers[instrument.driver]
        resolution = assignment.configuration.get("resolution", "5.5")
        if resolution not in driver_class.RESOLUTION_NPLC:
            resolution = "5.5"
        capability_name = (
            "dc_voltage" if reading.parameter == "Voltage DC" else "resistance"
        )
        ranges = instrument.capabilities[capability_name].ranges
        if ranges:
            absolute_value = abs(float(reading.value))
            active_range = next(
                (candidate for candidate in ranges if absolute_value <= candidate),
                ranges[-1],
            )
            return driver_class.decimal_places(
                active_range,
                resolution,
            )
    limits = instrument.power_supply_voltage_limits
    if limits is not None:
        return max(0, -limits["step"].as_tuple().exponent)
    return 3


@login_required
@require_GET
def panel(request, pk):
    """Render one instrument as a virtual DMM front panel."""
    instrument = _dmm_or_404(pk)
    active_task = _active_task(instrument)
    display_labels = {
        "dc_voltage": "DC Voltage",
        "ac_voltage": "AC Voltage",
        "dc_current": "DC Current",
        "ac_current": "AC Current",
        "resistance_4w": "Resistance 4W",
        "continuity": "Continuity",
        "diode": "Diode",
    }
    default_function_buttons = (
        ("dc_voltage", "DCV"),
        ("dc_current", "DCI"),
        ("ac_voltage", "ACV"),
        ("ac_current", "ACI"),
        ("resistance", "2W"),
        ("resistance_4w", "4W"),
        ("frequency", "Freq"),
        ("capacitance", "Cap"),
        ("diode", "Dio"),
        ("continuity", "Cont"),
        ("temperature", "Temp"),
    )
    agilent_34401a_function_buttons = (
        ("dc_voltage", "DCV"),
        ("dc_current", "DCI"),
        ("ac_voltage", "ACV"),
        ("ac_current", "ACI"),
        ("resistance", "Ω 2W"),
        ("resistance_4w", "Ω 4W"),
        ("frequency", "Freq"),
        ("period", "Period"),
        ("continuity", "Cont )))"),
        ("diode", "Diode"),
    )
    function_buttons = (
        agilent_34401a_function_buttons
        if instrument.driver == Instrument.Driver.AGILENT_34401A
        else default_function_buttons
    )
    display_units = {
        "dc_voltage": "VDC",
        "ac_voltage": "VAC",
        "dc_current": "ADC",
        "ac_current": "AAC",
    }
    capabilities = []
    for name, button_label in function_buttons:
        capability = instrument.capabilities.get(name)
        capabilities.append(
            {
                "name": name,
                "label": capability.label if capability else button_label,
                "button_label": button_label,
                "display_label": (
                    display_labels.get(name, capability.label)
                    if capability else button_label
                ),
                "unit": capability.unit if capability else "",
                "display_unit": (
                    display_units.get(name, capability.unit)
                    if capability else ""
                ),
                "autorange": capability.autorange if capability else False,
                "range_values": ",".join(
                    f"{value:g}" for value in capability.ranges
                ) if capability else "",
                "available": capability is not None,
            }
        )
    count_modes = (
        {
            mode: [float(full_scale) for full_scale, _resolution in ranges]
            for mode, ranges in VirtualMockBench.VOLTAGE_COUNT_MODES.items()
        }
        if instrument.driver == Instrument.Driver.MOCK else {}
    )
    count_mode_labels = (
        dict(VirtualMockBench.COUNT_MODE_LABELS)
        if instrument.driver == Instrument.Driver.MOCK else {}
    )
    return render(
        request,
        "dmm_panel/panel.html",
        {
            "instrument": instrument,
            "capabilities": capabilities,
            "busy": active_task is not None,
            "active_task": active_task,
            "count_modes": count_modes,
            "count_mode_labels": count_mode_labels,
            "reads_instrument_status": instrument.driver in {
                Instrument.Driver.AGILENT_34401A,
                Instrument.Driver.KEYSIGHT_34461A,
            },
            "extra_display_digits": (
                1
                if instrument.driver == Instrument.Driver.AGILENT_34401A
                else 0
            ),
            "supports_nplc_control": (
                instrument.driver == Instrument.Driver.AGILENT_34401A
            ),
        },
    )


@login_required
@require_GET
def status(request, pk):
    """Return the physical DMM's current front-panel measurement setup."""
    instrument = _dmm_or_404(pk)
    if _is_busy(instrument):
        return JsonResponse(
            {"error": "Instrument is in use by an active task."},
            status=409,
        )
    if instrument.driver not in {
        Instrument.Driver.AGILENT_34401A,
        Instrument.Driver.KEYSIGHT_34461A,
    }:
        return JsonResponse(
            {"error": "Instrument status readback is not supported."},
            status=400,
        )
    token = _panel_token(request)
    if not token:
        return JsonResponse({"error": "Invalid panel token."}, status=400)
    owns_control, latest_status = _claim_panel_control(
        instrument,
        request.user,
        token,
    )
    if not owns_control:
        latest_status.update({"read_only": True, "pending": not latest_status})
        return JsonResponse(latest_status)
    try:
        with ConnectionManager.persistent_session(instrument) as driver:
            payload = driver.read_panel_status()
            payload["commands"] = _drain_driver_commands(driver)
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    payload["read_only"] = False
    cached_payload = {
        key: value for key, value in payload.items() if key != "commands"
    }
    PanelLease.objects.filter(
        instrument=instrument,
        owner_token=token,
    ).update(last_seen=timezone.now(), latest_status=cached_payload)
    return JsonResponse(payload)


@login_required
@require_POST
def resolution(request, pk):
    """Set a physical DMM panel resolution and return confirmed NPLC."""
    instrument = _dmm_or_404(pk)
    if _is_busy(instrument):
        return JsonResponse(
            {"error": "Instrument is in use by an active task."},
            status=409,
        )
    if instrument.driver not in {
        Instrument.Driver.AGILENT_34401A,
        Instrument.Driver.KEYSIGHT_34461A,
    }:
        return JsonResponse(
            {"error": "Instrument resolution control is not supported."},
            status=400,
        )
    token = _panel_token(request)
    if not _has_panel_control(instrument, token):
        return JsonResponse(
            {"error": "Panel is open in read-only mode."},
            status=409,
        )
    function = request.POST.get("function", "")
    requested_resolution = request.POST.get("resolution", "")
    try:
        with ConnectionManager.session(instrument) as driver:
            if (
                instrument.driver == Instrument.Driver.AGILENT_34401A
                and requested_resolution in Agilent34401ADriver.RESOLUTION_MODES
            ):
                result = driver.set_resolution_mode(
                    function,
                    requested_resolution,
                )
            else:
                nplc = driver.set_resolution(function, requested_resolution)
                result = {
                    "resolution": requested_resolution,
                    "nplc": nplc,
                }
            commands = _drain_driver_commands(driver)
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    return JsonResponse(
        {**result, "commands": commands},
    )


@login_required
@require_POST
def nplc(request, pk):
    """Set and verify the 34401A integration time from its panel."""
    instrument = _dmm_or_404(pk)
    if _is_busy(instrument):
        return JsonResponse(
            {"error": "Instrument is in use by an active task."},
            status=409,
        )
    if instrument.driver != Instrument.Driver.AGILENT_34401A:
        return JsonResponse(
            {"error": "Instrument NPLC control is not supported."},
            status=400,
        )
    token = _panel_token(request)
    if not _has_panel_control(instrument, token):
        return JsonResponse(
            {"error": "Panel is open in read-only mode."},
            status=409,
        )
    function = request.POST.get("function", "")
    try:
        requested_nplc = float(request.POST.get("nplc", ""))
    except ValueError:
        return JsonResponse({"error": "Invalid NPLC value."}, status=400)
    try:
        with ConnectionManager.session(instrument) as driver:
            actual_nplc = driver.set_nplc(function, requested_nplc)
            commands = _drain_driver_commands(driver)
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    return JsonResponse({"nplc": actual_nplc, "commands": commands})


@login_required
@require_POST
def clear_status(request, pk):
    """Clear the physical instrument status and error queue with *CLS."""
    instrument = _dmm_or_404(pk)
    if _is_busy(instrument):
        return JsonResponse(
            {"error": "Instrument is in use by an active task."},
            status=409,
        )
    token = _panel_token(request)
    if not _has_panel_control(instrument, token):
        return JsonResponse(
            {"error": "Panel is open in read-only mode."},
            status=409,
        )
    try:
        with ConnectionManager.persistent_session(instrument) as driver:
            driver.write("*CLS")
            commands = _drain_driver_commands(driver)
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    return JsonResponse({"cleared": True, "commands": commands})


@login_required
@require_POST
def release(request, pk):
    """Clear instrument errors and release the owning browser's control."""
    instrument = _dmm_or_404(pk)
    token = _panel_token(request)
    owns_control = _has_panel_control(instrument, token)
    if not owns_control:
        return JsonResponse({"released": False})
    cleared_errors = ()
    try:
        with ConnectionManager.persistent_session(instrument) as driver:
            cleared_errors = driver.clear_error_queue()
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    finally:
        ConnectionManager.disconnect(instrument)
        PanelLease.objects.filter(
            instrument=instrument,
            owner_token=token,
        ).delete()
    return JsonResponse(
        {"released": True, "cleared_errors": list(cleared_errors)},
    )


@login_required
@require_POST
def measure(request, pk):
    """Take one reading while respecting active task ownership."""
    instrument = _dmm_or_404(pk)
    if _is_busy(instrument):
        return JsonResponse(
            {"error": "Instrument is in use by an active task."},
            status=409,
        )
    if (
        instrument.driver in {
            Instrument.Driver.AGILENT_34401A,
            Instrument.Driver.KEYSIGHT_34461A,
        }
        and not _has_panel_control(instrument, _panel_token(request))
    ):
        return JsonResponse(
            {"error": "Panel is open in read-only mode."},
            status=409,
        )
    function = request.POST.get("function", "dc_voltage")
    if function not in instrument.capabilities:
        return JsonResponse({"error": "Unsupported measurement function."}, status=400)
    capability = instrument.capabilities[function]
    count_mode = request.POST.get(
        "count_mode",
        VirtualMockBench.DEFAULT_COUNT_MODE,
    )
    voltage_ranges = capability.ranges
    if function == "dc_voltage" and instrument.driver == Instrument.Driver.MOCK:
        try:
            VirtualMockBench.validate_count_mode(count_mode)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        voltage_ranges = tuple(
            float(full_scale)
            for full_scale, _resolution in (
                VirtualMockBench.VOLTAGE_COUNT_MODES[count_mode]
            )
        )
    requested_range = request.POST.get("range", "auto")
    voltage_range = None
    if capability.autorange or capability.ranges:
        if requested_range == "auto":
            if not capability.autorange:
                return JsonResponse(
                    {"error": "This function does not support autorange."},
                    status=400,
                )
        else:
            try:
                voltage_range = float(requested_range)
            except ValueError:
                return JsonResponse({"error": "Invalid measurement range."}, status=400)
            if voltage_range not in voltage_ranges:
                return JsonResponse({"error": "Unsupported measurement range."}, status=400)
    measurement_error = None
    commands = []
    try:
        with ConnectionManager.session(instrument) as driver:
            try:
                if function == "dc_voltage" and instrument.driver == Instrument.Driver.MOCK:
                    driver.set_count_mode(count_mode)
                measurement = getattr(driver, f"measure_{function}")
                result = (
                    measurement(voltage_range)
                    if function in {"dc_voltage", "ac_voltage", "dc_current"}
                    else measurement()
                )
            except Exception as exc:
                # A panel command error must not escape the active session:
                # disconnecting a physical DMM also sends its Local command.
                measurement_error = exc
                recover = getattr(driver, "recover_panel_error", None)
                if recover is not None:
                    try:
                        recover()
                    except Exception:
                        pass
            commands = _drain_driver_commands(driver)
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    if measurement_error is not None:
        return JsonResponse(
            {
                "error": str(measurement_error)
                or measurement_error.__class__.__name__,
                "commands": commands,
            },
            status=503,
        )
    decimals = 3
    if function == "dc_voltage" and instrument.driver == Instrument.Driver.MOCK:
        reference_voltage = voltage_range if voltage_range is not None else result.value
        decimals = VirtualMockBench.voltage_decimal_places(
            reference_voltage,
            count_mode,
        )
    return JsonResponse(
        {
            "parameter": result.parameter,
            "value": result.value,
            "unit": result.unit,
            "decimals": decimals,
            "autorange": capability.autorange and voltage_range is None,
            "range_value": voltage_range,
            "count_mode": count_mode,
            "voltage_ranges": list(voltage_ranges),
            "commands": commands,
        },
    )


@login_required
@require_GET
def live_reading(request, pk):
    """Return the newest task-owned reading without touching the instrument."""
    instrument = _dmm_or_404(pk)
    task = _active_task(instrument)
    if task is None:
        return JsonResponse({"active": False})
    reading = (
        TaskReading.objects.filter(
            sample__task=task,
            task_instrument__instrument=instrument,
            sample__status__in=("completed", "failed"),
        )
        .select_related("sample", "task_instrument__instrument")
        .order_by("-sample__index", "-pk")
        .first()
    )
    payload = {
        "active": True,
        "task_id": task.pk,
        "task_name": task.name,
    }
    if reading is not None:
        statistics = TaskReading.objects.filter(
            sample__task=task,
            task_instrument=reading.task_instrument,
            parameter=reading.parameter,
        ).aggregate(
            minimum=Min("value"),
            maximum=Max("value"),
            average=Avg("value"),
        )
        recent_values = list(
            TaskReading.objects.filter(
                sample__task=task,
                task_instrument=reading.task_instrument,
                parameter=reading.parameter,
            )
            .order_by("-sample__index")
            .values_list("value", flat=True)[:120]
        )
        payload.update(
            parameter=reading.parameter,
            value=float(reading.value),
            unit=reading.unit,
            sample_id=reading.sample.index,
            timestamp=reading.sample.timestamp.isoformat(),
            decimals=_reading_decimal_places(reading),
            autorange=True,
            minimum=float(statistics["minimum"]),
            maximum=float(statistics["maximum"]),
            average=float(statistics["average"]),
            recent_values=[float(value) for value in reversed(recent_values)],
        )
        if reading.task_instrument.instrument.driver in {
            Instrument.Driver.AGILENT_34401A,
            Instrument.Driver.KEYSIGHT_34461A,
        }:
            resolution = reading.task_instrument.configuration.get(
                "resolution",
                "5.5",
            )
            if resolution not in {"4.5", "5.5", "6.5"}:
                resolution = "5.5"
            payload["resolution"] = resolution
        if (
            reading.parameter == "Voltage DC"
            and reading.task_instrument.instrument.driver
            == Instrument.Driver.MOCK
        ):
            count_mode = reading.task_instrument.configuration.get(
                "count_mode",
                VirtualMockBench.DEFAULT_COUNT_MODE,
            )
            payload.update(
                count_mode=count_mode,
                voltage_ranges=[
                    float(full_scale)
                    for full_scale, _resolution in (
                        VirtualMockBench.VOLTAGE_COUNT_MODES[count_mode]
                    )
                ],
            )
    return JsonResponse(payload)
