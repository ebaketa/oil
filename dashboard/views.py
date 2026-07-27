"""Views for the dashboard and informational pages."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from main.models import Instrument, Measurement
from services.connection_manager import ConnectionManager


@login_required
def dashboard(request):
    """Render the dashboard page."""
    instruments = Instrument.objects.all()
    connected_ids = ConnectionManager.connected_ids()
    return render(
        request,
        "main/dashboard.html",
        {
            "instruments": instruments,
            "instrument_count": instruments.count(),
            "reachable_instrument_count": instruments.filter(
                status=Instrument.Status.REACHABLE,
            ).exclude(pk__in=connected_ids).count(),
            "online_instrument_count": instruments.filter(
                pk__in=connected_ids,
            ).count(),
            "measurement_count": Measurement.objects.count(),
        },
    )


@login_required
def contact(request):
    """Render the contact page."""
    return render(request, "main/contact.html")


@login_required
def about(request):
    """Render the about page."""
    return render(request, "main/about.html")
