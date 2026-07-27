"""Application services for instrument-driver operations."""

from django.utils import timezone

from drivers.exceptions import DriverError
from services.connection_manager import ConnectionManager

from .models import Instrument


def connect_instrument(instrument: Instrument) -> None:
    """Open and retain a managed connection to an instrument."""
    try:
        ConnectionManager.connect(instrument)
    except Exception as exc:
        instrument.status = Instrument.Status.ERROR
        instrument.last_driver_error = str(exc) or exc.__class__.__name__
        instrument.save(
            update_fields=("status", "last_driver_error", "updated_at"),
        )
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The instrument could not be connected.") from exc

    instrument.status = Instrument.Status.REACHABLE
    instrument.last_driver_error = ""
    instrument.save(
        update_fields=("status", "last_driver_error", "updated_at"),
    )


def disconnect_instrument(instrument: Instrument) -> None:
    """Return local control and close a managed instrument connection."""
    try:
        ConnectionManager.disconnect(instrument)
    except Exception as exc:
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The instrument could not be disconnected.") from exc


def test_instrument_driver(instrument: Instrument) -> str:
    """Connect, identify, disconnect, and persist the driver test result."""
    tested_at = timezone.now()

    try:
        with ConnectionManager.session(instrument) as driver:
            identity = driver.identify()
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        instrument.status = Instrument.Status.ERROR
        instrument.last_driver_test_at = tested_at
        instrument.last_driver_error = error
        instrument.save(
            update_fields=(
                "status",
                "last_driver_test_at",
                "last_driver_error",
                "updated_at",
            ),
        )
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The driver test could not be completed.") from exc

    instrument.status = Instrument.Status.REACHABLE
    instrument.last_driver_test_at = tested_at
    instrument.last_identification = identity
    instrument.last_driver_error = ""
    instrument.save(
        update_fields=(
            "status",
            "last_driver_test_at",
            "last_identification",
            "last_driver_error",
            "updated_at",
        ),
    )
    return identity


def test_instrument_dc_voltage_mode(instrument: Instrument):
    """Configure DC voltage autorange and verify the read-back state."""
    tested_at = timezone.now()

    try:
        with ConnectionManager.session(instrument) as driver:
            configuration = driver.configure_dc_voltage_auto()
    except Exception as exc:
        error = str(exc) or exc.__class__.__name__
        instrument.status = Instrument.Status.ERROR
        instrument.last_driver_test_at = tested_at
        instrument.last_driver_error = error
        instrument.save(
            update_fields=(
                "status",
                "last_driver_test_at",
                "last_driver_error",
                "updated_at",
            ),
        )
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The DC voltage mode test could not be completed.") from exc

    instrument.status = Instrument.Status.REACHABLE
    instrument.last_driver_test_at = tested_at
    instrument.last_driver_error = ""
    instrument.save(
        update_fields=(
            "status",
            "last_driver_test_at",
            "last_driver_error",
            "updated_at",
        ),
    )
    return configuration
