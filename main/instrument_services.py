"""Compatibility imports for instrument services."""

from instruments.services import (
    connect_instrument,
    disconnect_instrument,
    test_instrument_dc_voltage_mode,
    test_instrument_driver,
)

__all__ = [
    "connect_instrument",
    "disconnect_instrument",
    "test_instrument_dc_voltage_mode",
    "test_instrument_driver",
]
