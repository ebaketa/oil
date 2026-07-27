"""Small explicit serializers for the OIL JSON API."""

from instruments.models import Instrument
from measurements.models import Measurement
from services.connection_manager import ConnectionManager


def serialize_capabilities(instrument: Instrument) -> dict[str, dict]:
    """Return JSON-compatible capability metadata for an instrument."""
    return {
        name: {
            "label": capability.label,
            "unit": capability.unit,
            "autorange": capability.autorange,
            "ranges": list(capability.ranges),
            "nplc": list(capability.nplc),
        }
        for name, capability in instrument.capabilities.items()
    }


def serialize_instrument(
    instrument: Instrument,
    *,
    include_capabilities: bool = False,
) -> dict:
    """Return one instrument inventory record as JSON-compatible data."""
    payload = {
        "id": instrument.pk,
        "name": instrument.name,
        "manufacturer": instrument.manufacturer,
        "model": instrument.model_name,
        "serial_number": instrument.serial_number,
        "driver": instrument.driver,
        "driver_label": instrument.get_driver_display(),
        "address": instrument.address,
        "status": instrument.status,
        "online": ConnectionManager.is_connected(instrument),
        "description": instrument.description,
        "created_at": instrument.created_at.isoformat(),
        "updated_at": instrument.updated_at.isoformat(),
    }
    if include_capabilities:
        payload["capabilities"] = serialize_capabilities(instrument)
    return payload


def serialize_measurement(measurement: Measurement) -> dict:
    """Return one normalized measurement as JSON-compatible data."""
    return {
        "id": measurement.pk,
        "run_id": measurement.run_id,
        "instrument_id": measurement.instrument_id,
        "instrument": measurement.instrument.name,
        "parameter": measurement.parameter,
        "value": measurement.value,
        "unit": measurement.unit,
        "timestamp": measurement.timestamp.isoformat(),
        "notes": measurement.notes,
    }
