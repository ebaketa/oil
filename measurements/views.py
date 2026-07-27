"""Views for measurement workflows."""

import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from drivers.exceptions import DriverError

from .forms import (
    ContinuousMeasurementForm,
    LoopMeasurementForm,
    MeasurementForm,
)
from .models import Measurement
from .services import (
    iter_continuous_measurements,
    iter_measurement_loop,
    perform_measurement,
    perform_measurement_loop,
)
from .sessions import ContinuousSessionRegistry


@login_required
def measurement_list(request):
    """Display stored instrument measurements."""
    measurements = Measurement.objects.select_related("instrument")
    return render(
        request,
        "main/measurement_list.html",
        {
            "measurements": measurements,
            "measurement_count": measurements.count(),
        },
    )


@login_required
def measurement_create(request):
    """Select, perform, and store a new instrument measurement."""
    measurement = None
    measurement_summary = None

    if request.method == "POST":
        form = MeasurementForm(request.POST)
        if form.is_valid():
            try:
                measurement = perform_measurement(
                    form.cleaned_data["instrument"],
                    form.cleaned_data["measurement_type"],
                    notes=form.cleaned_data["notes"],
                )
            except DriverError as exc:
                form.add_error(None, f"Measurement failed: {exc}")
            else:
                messages.success(
                    request,
                    (
                        f"Measurement recorded: {measurement.value} "
                        f"{measurement.unit}."
                    ),
                )
                measurement_summary = {
                    "instrument": str(form.cleaned_data["instrument"]),
                    "measurement": dict(
                        form.fields["measurement_type"].choices,
                    )[form.cleaned_data["measurement_type"]],
                    "notes": form.cleaned_data["notes"],
                }
    else:
        form = MeasurementForm()

    return render(
        request,
        "main/measurement_form.html",
        {
            "form": form,
            "measurement": measurement,
            "measurement_summary": measurement_summary,
        },
    )


@login_required
@require_POST
def measurement_single_result(request):
    """Perform one measurement and return a row for the live Single table."""
    form = MeasurementForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    try:
        measurement = perform_measurement(
            form.cleaned_data["instrument"],
            form.cleaned_data["measurement_type"],
            notes=form.cleaned_data["notes"],
        )
    except DriverError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    return JsonResponse(
        {
            "timestamp": measurement.timestamp.isoformat(),
            "instrument": measurement.instrument.name,
            "parameter": measurement.parameter,
            "value": measurement.value,
            "unit": measurement.unit,
        },
    )


@login_required
def measurement_continuous(request):
    """Render controls for a continuous measurement session."""
    return render(
        request,
        "main/measurement_continuous_form.html",
        {"form": ContinuousMeasurementForm()},
    )


@login_required
@require_POST
def measurement_continuous_stream(request):
    """Stream readings until the matching continuous session is stopped."""
    form = ContinuousMeasurementForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    try:
        session_id = str(uuid.UUID(request.POST.get("session_id", "")))
    except (ValueError, AttributeError):
        return JsonResponse(
            {"error": "A valid continuous session identifier is required."},
            status=400,
        )

    try:
        stop_event = ContinuousSessionRegistry.start(
            session_id,
            request.user.pk,
        )
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=409)

    instrument = form.cleaned_data["instrument"]
    measurement_type = form.cleaned_data["measurement_type"]
    interval_seconds = form.cleaned_data["interval_seconds"]
    notes = form.cleaned_data["notes"]

    def stream_results():
        try:
            for index, measurement in enumerate(
                iter_continuous_measurements(
                    instrument,
                    measurement_type,
                    interval_seconds=interval_seconds,
                    stop_event=stop_event,
                    notes=notes,
                ),
                start=1,
            ):
                yield json.dumps(
                    {
                        "index": index,
                        "timestamp": measurement.timestamp.isoformat(),
                        "instrument": measurement.instrument.name,
                        "parameter": measurement.parameter,
                        "value": measurement.value,
                        "unit": measurement.unit,
                    },
                ) + "\n"
        except DriverError as exc:
            yield json.dumps({"error": str(exc)}) + "\n"
        finally:
            stop_event.set()
            ContinuousSessionRegistry.finish(session_id)

    response = StreamingHttpResponse(
        stream_results(),
        content_type="application/x-ndjson",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@login_required
@require_POST
def measurement_continuous_stop(request):
    """Request immediate cleanup of an owned continuous session."""
    try:
        session_id = str(uuid.UUID(request.POST.get("session_id", "")))
    except (ValueError, AttributeError):
        return JsonResponse(
            {"error": "A valid continuous session identifier is required."},
            status=400,
        )

    if not ContinuousSessionRegistry.stop(session_id, request.user.pk):
        return JsonResponse(
            {"error": "Continuous measurement session was not found."},
            status=404,
        )
    return JsonResponse({"stopping": True})


@login_required
def measurement_loop(request):
    """Configure and perform a finite series of measurements."""
    measurements = []
    loop_summary = None

    if request.method == "POST":
        form = LoopMeasurementForm(request.POST)
        if form.is_valid():
            instrument = form.cleaned_data["instrument"]
            try:
                measurements = perform_measurement_loop(
                    instrument,
                    form.cleaned_data["measurement_type"],
                    count=form.cleaned_data["count"],
                    interval_seconds=form.cleaned_data["interval_seconds"],
                    notes=form.cleaned_data["notes"],
                )
            except DriverError as exc:
                form.add_error(None, f"Measurement loop failed: {exc}")
            else:
                loop_summary = {
                    "instrument": str(instrument),
                    "measurement": dict(
                        form.fields["measurement_type"].choices,
                    )[form.cleaned_data["measurement_type"]],
                    "count": form.cleaned_data["count"],
                    "interval_seconds": form.cleaned_data["interval_seconds"],
                    "notes": form.cleaned_data["notes"],
                }
    else:
        form = LoopMeasurementForm()

    return render(
        request,
        "main/measurement_loop_form.html",
        {
            "form": form,
            "measurements": measurements,
            "loop_summary": loop_summary,
        },
    )


@login_required
@require_POST
def measurement_loop_stream(request):
    """Stream each loop reading to the browser as newline-delimited JSON."""
    form = LoopMeasurementForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()},
            status=400,
        )

    instrument = form.cleaned_data["instrument"]
    measurement_type = form.cleaned_data["measurement_type"]
    count = form.cleaned_data["count"]
    interval_seconds = form.cleaned_data["interval_seconds"]
    notes = form.cleaned_data["notes"]

    def stream_results():
        try:
            for index, measurement in enumerate(
                iter_measurement_loop(
                    instrument,
                    measurement_type,
                    count=count,
                    interval_seconds=interval_seconds,
                    notes=notes,
                ),
                start=1,
            ):
                yield json.dumps(
                    {
                        "index": index,
                        "timestamp": measurement.timestamp.isoformat(),
                        "instrument": measurement.instrument.name,
                        "parameter": measurement.parameter,
                        "value": measurement.value,
                        "unit": measurement.unit,
                    },
                ) + "\n"
        except DriverError as exc:
            yield json.dumps({"error": str(exc)}) + "\n"

    response = StreamingHttpResponse(
        stream_results(),
        content_type="application/x-ndjson",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
