"""Session-authenticated JSON API views."""

import json
from functools import wraps

from django.http import JsonResponse

from drivers.exceptions import DriverError
from instruments.models import Instrument
from measurements.forms import MeasurementForm
from measurements.models import Measurement
from measurements.services import perform_measurement

from .serializers import serialize_instrument, serialize_measurement


def api_endpoint(*allowed_methods):
    """Require authentication and return JSON for unsupported methods."""

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse(
                    {"error": "Authentication is required."},
                    status=401,
                )
            if request.method not in allowed_methods:
                response = JsonResponse(
                    {
                        "error": (
                            f"Method {request.method} is not allowed."
                        ),
                    },
                    status=405,
                )
                response["Allow"] = ", ".join(allowed_methods)
                return response
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def _parse_pagination(request) -> tuple[int, int] | JsonResponse:
    """Validate bounded limit and offset query parameters."""
    try:
        limit = int(request.GET.get("limit", 50))
        offset = int(request.GET.get("offset", 0))
    except ValueError:
        return JsonResponse(
            {"error": "limit and offset must be integers."},
            status=400,
        )
    if not 1 <= limit <= 100:
        return JsonResponse(
            {"error": "limit must be between 1 and 100."},
            status=400,
        )
    if offset < 0:
        return JsonResponse(
            {"error": "offset must be zero or greater."},
            status=400,
        )
    return limit, offset


@api_endpoint("GET")
def instrument_list(request):
    """Return all configured instruments."""
    instruments = Instrument.objects.all()
    return JsonResponse(
        {
            "count": instruments.count(),
            "results": [
                serialize_instrument(instrument)
                for instrument in instruments
            ],
        },
    )


@api_endpoint("GET")
def instrument_detail(request, pk):
    """Return one instrument and its measurement capabilities."""
    try:
        instrument = Instrument.objects.get(pk=pk)
    except Instrument.DoesNotExist:
        return JsonResponse(
            {"error": "Instrument was not found."},
            status=404,
        )
    return JsonResponse(
        serialize_instrument(
            instrument,
            include_capabilities=True,
        ),
    )


@api_endpoint("GET")
def measurement_list(request):
    """Return stored measurements using bounded offset pagination."""
    pagination = _parse_pagination(request)
    if isinstance(pagination, JsonResponse):
        return pagination
    limit, offset = pagination

    measurements = Measurement.objects.select_related("instrument")
    count = measurements.count()
    page = measurements[offset:offset + limit]
    return JsonResponse(
        {
            "count": count,
            "limit": limit,
            "offset": offset,
            "results": [
                serialize_measurement(measurement)
                for measurement in page
            ],
        },
    )


@api_endpoint("POST")
def measurement_single(request):
    """Validate JSON, perform one measurement, and return the stored result."""
    if request.content_type != "application/json":
        return JsonResponse(
            {"error": "Content-Type must be application/json."},
            status=415,
        )
    try:
        payload = json.loads(request.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"error": "Request body must contain valid JSON."},
            status=400,
        )
    if not isinstance(payload, dict):
        return JsonResponse(
            {"error": "Request body must be a JSON object."},
            status=400,
        )

    form = MeasurementForm(
        {
            "instrument": payload.get("instrument_id"),
            "measurement_type": payload.get("function"),
            "notes": payload.get("notes", ""),
        },
    )
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
        return JsonResponse(
            {"error": str(exc)},
            status=502,
        )

    return JsonResponse(
        serialize_measurement(measurement),
        status=201,
    )
