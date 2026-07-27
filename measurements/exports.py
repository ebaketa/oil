"""Streaming exports for stored measurements."""

import csv

from django.contrib.auth.decorators import login_required
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Measurement


CSV_COLUMNS = (
    "measurement_id",
    "run_id",
    "timestamp",
    "instrument_id",
    "instrument_name",
    "manufacturer",
    "model",
    "serial_number",
    "parameter",
    "value",
    "unit",
    "notes",
)


class CsvEcho:
    """Return CSV writer output directly instead of buffering it."""

    def write(self, value: str) -> str:
        """Return the value supplied by ``csv.writer``."""
        return value


def safe_spreadsheet_text(value: str) -> str:
    """Prevent user-controlled text from becoming a spreadsheet formula."""
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{value}"
    return value


def measurement_csv_rows():
    """Yield a UTF-8 BOM, header, and one CSV row per measurement."""
    writer = csv.writer(CsvEcho(), lineterminator="\r\n")
    yield "\ufeff"
    yield writer.writerow(CSV_COLUMNS)

    measurements = (
        Measurement.objects.select_related("instrument", "run")
        .order_by("timestamp", "pk")
        .iterator(chunk_size=1000)
    )
    for measurement in measurements:
        instrument = measurement.instrument
        yield writer.writerow(
            (
                measurement.pk,
                measurement.run_id or "",
                measurement.timestamp.isoformat(),
                instrument.pk,
                safe_spreadsheet_text(instrument.name),
                safe_spreadsheet_text(instrument.manufacturer),
                safe_spreadsheet_text(instrument.model_name),
                safe_spreadsheet_text(instrument.serial_number),
                safe_spreadsheet_text(measurement.parameter),
                measurement.value,
                safe_spreadsheet_text(measurement.unit),
                safe_spreadsheet_text(measurement.notes),
            ),
        )


@login_required
@require_GET
def measurement_export_csv(request):
    """Download all stored measurements as a streaming CSV file."""
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    response = StreamingHttpResponse(
        measurement_csv_rows(),
        content_type="text/csv; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="oil-measurements-{timestamp}.csv"'
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
