"""Instrument drivers supplied with OIL."""

from .agilent_34401a import Agilent34401ADriver
from .keysight_34461a import Keysight34461ADriver
from .mock import MockInstrumentDriver
from .mock_dc_power_supply import MockDCPowerSupplyDriver
from .mock_rnd_320_3005p import MockRND3203005PDriver
from .registry import DriverRegistry
from .rnd_ka3005p import RNDKA3005PDriver

DriverRegistry.register("agilent_34401a", Agilent34401ADriver)
DriverRegistry.register("keysight_34461a", Keysight34461ADriver)
DriverRegistry.register("mock-dmm", MockInstrumentDriver)
DriverRegistry.register("mock_dc_power_supply", MockDCPowerSupplyDriver)
DriverRegistry.register("mock_rnd_320_3005p", MockRND3203005PDriver)
DriverRegistry.register("rnd_ka3005p", RNDKA3005PDriver)

__all__ = (
    "Agilent34401ADriver",
    "DriverRegistry",
    "Keysight34461ADriver",
    "MockDCPowerSupplyDriver",
    "MockInstrumentDriver",
    "MockRND3203005PDriver",
    "RNDKA3005PDriver",
)
