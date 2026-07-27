"""Views for laboratory instrument inventory and driver operations."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from drivers.exceptions import DriverError
from services.connection_manager import ConnectionManager

from .forms import InstrumentForm
from .models import Instrument
from .services import (
    connect_instrument,
    disconnect_instrument,
    test_instrument_dc_voltage_mode,
    test_instrument_driver,
)


@login_required
def instrument_list(request):
    """Display the laboratory instrument inventory."""
    instruments = list(Instrument.objects.all())
    connected_ids = ConnectionManager.connected_ids()
    for instrument in instruments:
        instrument.is_online = instrument.pk in connected_ids
    return render(
        request,
        "main/instrument_list.html",
        {
            "instruments": instruments,
            "instrument_count": len(instruments),
        },
    )


@login_required
def instrument_create(request):
    """Display and process the new-instrument form."""
    if request.method == "POST":
        form = InstrumentForm(request.POST)
        if form.is_valid():
            instrument = form.save()
            messages.success(request, f"{instrument.name} has been added.")
            return redirect("instrument_list")
    else:
        form = InstrumentForm()

    return render(
        request,
        "main/instrument_form.html",
        {
            "form": form,
            "page_title": "Add instrument",
            "submit_label": "Add instrument",
        },
    )


@login_required
def instrument_edit(request, pk):
    """Display and process settings for an existing instrument."""
    instrument = get_object_or_404(Instrument, pk=pk)

    if request.method == "POST":
        form = InstrumentForm(request.POST, instance=instrument)
        if form.is_valid():
            instrument = form.save()
            messages.success(request, f"{instrument.name} has been updated.")
            return redirect("instrument_list")
    else:
        form = InstrumentForm(instance=instrument)

    return render(
        request,
        "main/instrument_form.html",
        {
            "form": form,
            "instrument": instrument,
            "page_title": "Edit instrument",
            "submit_label": "Save changes",
        },
    )


@login_required
def instrument_driver(request, pk):
    """Display driver configuration and the most recent test result."""
    instrument = get_object_or_404(Instrument, pk=pk)
    return render(
        request,
        "main/instrument_driver.html",
        {
            "instrument": instrument,
            "capabilities": instrument.capabilities,
        },
    )


@login_required
@require_POST
def instrument_connect(request, pk):
    """Open and retain a connection to an instrument."""
    instrument = get_object_or_404(Instrument, pk=pk)
    try:
        connect_instrument(instrument)
    except DriverError as exc:
        messages.error(request, f"Connection failed: {exc}")
    else:
        messages.success(request, f"{instrument.name} is connected.")
    return redirect("instrument_list")


@login_required
@require_POST
def instrument_disconnect(request, pk):
    """Return local control and close an instrument connection."""
    instrument = get_object_or_404(Instrument, pk=pk)
    try:
        disconnect_instrument(instrument)
    except DriverError as exc:
        messages.error(request, f"Disconnect failed: {exc}")
    else:
        messages.success(request, f"{instrument.name} is disconnected.")
    return redirect("instrument_list")


@login_required
@require_POST
def instrument_driver_test(request, pk):
    """Run a connection and identification test for an instrument driver."""
    instrument = get_object_or_404(Instrument, pk=pk)
    try:
        identity = test_instrument_driver(instrument)
    except DriverError as exc:
        messages.error(request, f"Driver test failed: {exc}")
    else:
        messages.success(request, f"Driver test passed: {identity}")
    return redirect("instrument_driver", pk=instrument.pk)


@login_required
@require_POST
def instrument_driver_test_dcv(request, pk):
    """Configure and verify DC voltage autorange for an instrument."""
    instrument = get_object_or_404(Instrument, pk=pk)
    try:
        configuration = test_instrument_dc_voltage_mode(instrument)
    except DriverError as exc:
        messages.error(request, f"DCV Auto test failed: {exc}")
    else:
        messages.success(
            request,
            f"DCV Auto confirmed: {configuration.function}, autorange enabled.",
        )
    return redirect("instrument_driver", pk=instrument.pk)
