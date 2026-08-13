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
    return render(
        request,
        "dmm_panel/panel_list.html",
        {"panel_instruments": instruments},
    )


def _reading_decimal_places(reading):
    """Use the same task-specific display precision as the Task workspace."""
    assignment = reading.task_instrument
    instrument = assignment.instrument
    if (
        reading.parameter == "Voltage DC"
        and instrument.driver == Instrument.Driver.MOCK
        and assignment.configuration.get("source")
        == AutomationTask.VoltageSource.VIRTUAL
    ):
        return VirtualMockBench.voltage_decimal_places(
            reading.sample.voltage_setpoint,
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
        "dc_voltage": "Voltage DC",
        "ac_voltage": "Voltage AC",
        "dc_current": "Current DC",
        "ac_current": "Current AC",
    }
    capabilities = [
        {
            "name": name,
            "label": capability.label,
            "display_label": display_labels.get(name, capability.label),
            "unit": capability.unit,
        }
        for name, capability in instrument.capabilities.items()
    ]
    return render(
        request,
        "dmm_panel/panel.html",
        {
            "instrument": instrument,
            "capabilities": capabilities,
            "busy": active_task is not None,
            "active_task": active_task,
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
    try:
        with ConnectionManager.session(instrument) as driver:
            result = getattr(driver, f"measure_{function}")()
    except Exception as exc:
        return JsonResponse(
            {"error": str(exc) or exc.__class__.__name__},
            status=503,
        )
    return JsonResponse(
        {
            "parameter": result.parameter,
            "value": result.value,
            "unit": result.unit,
            "decimals": 3,
            "autorange": True,
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
    return JsonResponse(payload)
