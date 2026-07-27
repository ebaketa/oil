"""Application services for performing and storing measurements."""

import time
from collections.abc import Iterator
from threading import Event

from drivers.exceptions import DriverError
from services.connection_manager import ConnectionManager

from .models import Instrument, Measurement


def _read_measurement(driver, measurement_type: str):
    """Execute one supported measurement against an active driver."""
    measurement_methods = {
        "dc_voltage": driver.measure_dc_voltage,
        "ac_voltage": driver.measure_ac_voltage,
        "resistance": driver.measure_resistance,
    }
    try:
        measurement_method = measurement_methods[measurement_type]
    except KeyError as exc:
        raise DriverError(
            f"Unsupported measurement type: {measurement_type}"
        ) from exc
    return measurement_method()


def _store_result(
    instrument: Instrument,
    result,
    notes: str,
) -> Measurement:
    """Persist one normalized driver result."""
    return Measurement.objects.create(
        instrument=instrument,
        parameter=result.parameter,
        value=result.value,
        unit=result.unit,
        notes=notes,
    )


def _record_success(instrument: Instrument) -> None:
    """Persist a successful instrument operation."""
    instrument.status = Instrument.Status.REACHABLE
    instrument.last_driver_error = ""
    instrument.save(
        update_fields=("status", "last_driver_error", "updated_at"),
    )


def _record_failure(instrument: Instrument, exc: Exception) -> None:
    """Persist the most recent instrument failure."""
    instrument.status = Instrument.Status.ERROR
    instrument.last_driver_error = str(exc) or exc.__class__.__name__
    instrument.save(
        update_fields=("status", "last_driver_error", "updated_at"),
    )


def perform_measurement(
    instrument: Instrument,
    measurement_type: str,
    *,
    notes: str = "",
) -> Measurement:
    """Perform a supported driver operation and store its normalized result."""
    try:
        with ConnectionManager.temporary_session(instrument) as driver:
            result = _read_measurement(driver, measurement_type)
    except Exception as exc:
        _record_failure(instrument, exc)
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The measurement could not be completed.") from exc

    _record_success(instrument)
    return _store_result(instrument, result, notes)


def perform_measurement_loop(
    instrument: Instrument,
    measurement_type: str,
    *,
    count: int,
    interval_seconds: float,
    notes: str = "",
) -> list[Measurement]:
    """Perform a finite measurement series over one managed connection."""
    return list(
        iter_measurement_loop(
            instrument,
            measurement_type,
            count=count,
            interval_seconds=interval_seconds,
            notes=notes,
        ),
    )


def iter_measurement_loop(
    instrument: Instrument,
    measurement_type: str,
    *,
    count: int,
    interval_seconds: float,
    notes: str = "",
) -> Iterator[Measurement]:
    """Yield each stored reading as soon as a loop operation completes."""

    try:
        with ConnectionManager.temporary_session(instrument) as driver:
            for index in range(count):
                result = _read_measurement(driver, measurement_type)
                measurement = _store_result(instrument, result, notes)
                yield measurement
                if index < count - 1:
                    time.sleep(interval_seconds)
    except Exception as exc:
        _record_failure(instrument, exc)
        if isinstance(exc, DriverError):
            raise
        raise DriverError("The measurement loop could not be completed.") from exc

    _record_success(instrument)


def iter_continuous_measurements(
    instrument: Instrument,
    measurement_type: str,
    *,
    interval_seconds: float,
    stop_event: Event,
    notes: str = "",
) -> Iterator[Measurement]:
    """Yield stored readings over one connection until stop is requested."""
    try:
        with ConnectionManager.temporary_session(instrument) as driver:
            while not stop_event.is_set():
                result = _read_measurement(driver, measurement_type)
                yield _store_result(instrument, result, notes)
                if stop_event.wait(interval_seconds):
                    break
    except Exception as exc:
        _record_failure(instrument, exc)
        if isinstance(exc, DriverError):
            raise
        raise DriverError(
            "Continuous measurement could not be completed."
        ) from exc

    _record_success(instrument)
