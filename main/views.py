"""Compatibility imports for views moved to domain applications."""

from accounts.views import profile
from dashboard.views import about, contact, dashboard
from instruments.views import (
    instrument_connect,
    instrument_create,
    instrument_disconnect,
    instrument_driver,
    instrument_driver_test,
    instrument_driver_test_dcv,
    instrument_edit,
    instrument_list,
)
from measurements.views import (
    measurement_continuous,
    measurement_continuous_stop,
    measurement_continuous_stream,
    measurement_create,
    measurement_list,
    measurement_loop,
    measurement_loop_stream,
    measurement_single_result,
)

__all__ = [
    "about",
    "contact",
    "dashboard",
    "instrument_connect",
    "instrument_create",
    "instrument_disconnect",
    "instrument_driver",
    "instrument_driver_test",
    "instrument_driver_test_dcv",
    "instrument_edit",
    "instrument_list",
    "measurement_continuous",
    "measurement_continuous_stop",
    "measurement_continuous_stream",
    "measurement_create",
    "measurement_list",
    "measurement_loop",
    "measurement_loop_stream",
    "measurement_single_result",
    "profile",
]
