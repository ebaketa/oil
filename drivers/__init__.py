"""Instrument drivers supplied with OIL."""

from .agilent_34401a import Agilent34401ADriver
from .keysight_34461a import Keysight34461ADriver
from .mock import MockInstrumentDriver
from .registry import DriverRegistry

DriverRegistry.register("agilent_34401a", Agilent34401ADriver)
DriverRegistry.register("keysight_34461a", Keysight34461ADriver)
DriverRegistry.register("mock", MockInstrumentDriver)

__all__ = (
    "Agilent34401ADriver",
    "DriverRegistry",
    "Keysight34461ADriver",
    "MockInstrumentDriver",
)
