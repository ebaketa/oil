"""Views for laboratory instrument inventory and driver operations."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from drivers.exceptions import DriverError
from services.connection_manager import ConnectionManager

from .forms import InstrumentForm
from .models import Instrument
from .services import (
    connect_instrument,
    disconnect_instrument,
    test_instrument_configuration,
    test_instrument_dc_voltage_mode,
    test_instrument_driver,
)

TESTED_CONFIGURATION_SESSION_KEY = "tested_instrument_configuration"


@login_required
def instrument_list(request):
    """Display the laboratory instrument inventory."""
    instruments = list(Instrument.objects.order_by("pk"))
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
def instrument_detail(request, pk):
    """Display read-only inventory information for an instrument."""
    instrument = get_object_or_404(Instrument, pk=pk)
    instrument.is_online = instrument.pk in ConnectionManager.connected_ids()
    return render(
        request,
        "main/instrument_detail.html",
        {
            "instrument": instrument,
            "capabilities": instrument.capabilities,
        },
    )


@login_required
def instrument_create(request):
    """Display and process the new-instrument form."""
    if not request.user.is_staff:
        raise PermissionDenied

    connection_test_identity = ""
    if request.method == "POST":
        form = InstrumentForm(request.POST)
        if form.is_valid():
            instrument = form.save(commit=False)
            configuration = {
                "driver": instrument.driver,
                "address": instrument.address,
            }
            if request.POST.get("action") == "test_connection":
                request.session.pop(TESTED_CONFIGURATION_SESSION_KEY, None)
                try:
                    connection_test_identity = (
                        test_instrument_configuration(instrument)
                    )
                except DriverError as exc:
                    form.add_error(None, f"Connection test failed: {exc}")
                else:
                    request.session[TESTED_CONFIGURATION_SESSION_KEY] = (
                        configuration
                    )
            elif (
                request.session.get(TESTED_CONFIGURATION_SESSION_KEY)
                != configuration
            ):
                form.add_error(
                    None,
                    "Test the current driver and address before saving.",
                )
            else:
                instrument.save()
                request.session.pop(TESTED_CONFIGURATION_SESSION_KEY, None)
                messages.success(request, f"{instrument.name} has been added.")
                return redirect("instrument_list")
    else:
        request.session.pop(TESTED_CONFIGURATION_SESSION_KEY, None)
        form = InstrumentForm()

    return render(
        request,
        "main/instrument_form.html",
        {
            "form": form,
            "page_title": "Add instrument",
            "submit_label": "Add instrument",
            "connection_test_identity": connection_test_identity,
        },
    )


@login_required
def instrument_edit(request, pk):
    """Display and process settings for an existing instrument."""
    if not request.user.is_staff:
        raise PermissionDenied

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
@require_POST
def instrument_delete(request, pk):
    """Delete an instrument when requested by an administrator."""
    if not request.user.is_staff:
        raise PermissionDenied

    instrument = get_object_or_404(Instrument, pk=pk)
    instrument_name = instrument.name
    try:
        instrument.delete()
    except ProtectedError:
        messages.error(
            request,
            f"{instrument_name} cannot be deleted because it is in use.",
        )
    else:
        messages.success(request, f"{instrument_name} has been deleted.")
    return redirect("instrument_list")


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
    if not request.user.is_staff:
        raise PermissionDenied

    instrument = get_object_or_404(Instrument, pk=pk)
    try:
        identity = test_instrument_driver(instrument)
    except DriverError as exc:
        messages.error(request, f"Driver test failed: {exc}")
    else:
        messages.success(request, f"Driver test passed: {identity}")
    return redirect("instrument_edit", pk=instrument.pk)


@login_required
@require_POST
def instrument_driver_test_dcv(request, pk):
    """Configure and verify DC voltage autorange for an instrument."""
    if not request.user.is_staff:
        raise PermissionDenied

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
    return redirect("instrument_edit", pk=instrument.pk)
