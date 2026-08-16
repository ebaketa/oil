"""Views for interactive DMM measurements."""

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Max, Min, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from main.models import Instrument
from services.connection_manager import ConnectionManager
from tasks.bench import VirtualMockBench
from tasks.models import AutomationTask, TaskReading


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
    }
    function_buttons = (
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
        },
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
    try:
        with ConnectionManager.session(instrument) as driver:
            if function == "dc_voltage" and instrument.driver == Instrument.Driver.MOCK:
                driver.set_count_mode(count_mode)
            measurement = getattr(driver, f"measure_{function}")
            result = (
                measurement(voltage_range)
                if function == "dc_voltage"
                else measurement()
            )
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
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
            "autorange": voltage_range is None,
            "range_value": voltage_range,
            "count_mode": count_mode,
            "voltage_ranges": list(voltage_ranges),
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
