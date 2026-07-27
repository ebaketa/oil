"""Compatibility imports for forms moved to domain applications."""

from accounts.forms import ProfileForm
from instruments.forms import InstrumentForm
from measurements.forms import (
    ContinuousMeasurementForm,
    LoopMeasurementForm,
    MeasurementForm,
)

__all__ = [
    "ContinuousMeasurementForm",
    "InstrumentForm",
    "LoopMeasurementForm",
    "MeasurementForm",
    "ProfileForm",
]
