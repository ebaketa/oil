"""Instrument drivers supplied with OIL."""

from .agilent_34401a import Agilent34401ADriver
from .keysight_34461a import Keysight34461ADriver
from .mock import MockInstrumentDriver
from .mock_dc_power_supply import MockDCPowerSupplyDriver
from .registry import DriverRegistry

DriverRegistry.register("agilent_34401a", Agilent34401ADriver)
DriverRegistry.register("keysight_34461a", Keysight34461ADriver)
DriverRegistry.register("mock", MockInstrumentDriver)
DriverRegistry.register("mock_dc_power_supply", MockDCPowerSupplyDriver)

__all__ = (
    "Agilent34401ADriver",
    "DriverRegistry",
    "Keysight34461ADriver",
    "MockDCPowerSupplyDriver",
    "MockInstrumentDriver",
)
