"""Exceptions raised by OIL instrument drivers."""


class DriverError(Exception):
    """Base exception for instrument-driver errors."""


class ConnectionError(DriverError):
    """An instrument connection could not be opened or initialized."""


class CommunicationError(DriverError):
    """Communication with a connected instrument failed."""


class MeasurementError(DriverError):
    """An instrument did not return a valid measurement."""
