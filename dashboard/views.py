"""Views for the dashboard and informational pages."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from main.models import Instrument, Measurement
from services.connection_manager import ConnectionManager
from tasks.models import AutomationTask


@login_required
def dashboard(request):
    """Render the dashboard page."""
    instruments = Instrument.objects.all()
    tasks = AutomationTask.objects.all()
    connected_ids = ConnectionManager.connected_ids()
    return render(
        request,
        "main/dashboard.html",
        {
            "instruments": instruments,
            "active_task_count": tasks.filter(
                status__in=(
                    AutomationTask.Status.PENDING,
                    AutomationTask.Status.RUNNING,
                ),
            ).count(),
            "completed_task_count": tasks.filter(
                status=AutomationTask.Status.COMPLETED,
            ).count(),
            "instrument_count": instruments.count(),
            "panel_count": sum(
                1 for instrument in instruments if instrument.capabilities
            ),
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
