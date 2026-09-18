"""Instrument drivers supplied with OIL."""

from .agilent_34401a import Agilent34401ADriver
from .btdl_ntc import BTDLNTCDriver
from .btdl_ds18b20 import BTDLDS18B20Driver
from .btdl_bmx280 import BTDLBMx280Driver
from .keysight_34461a import Keysight34461ADriver
from .mock import MockInstrumentDriver
from .mock_dc_power_supply import MockDCPowerSupplyDriver
from .mock_rnd_320_3005p import MockRND3203005PDriver
from .registry import DriverRegistry
from .rnd_ka3005p import RNDKA3005PDriver
from .rpi_cpu_temperature import RaspberryPiCPUTemperatureDriver

DriverRegistry.register("agilent_34401a", Agilent34401ADriver)
DriverRegistry.register("btdl_ntc", BTDLNTCDriver)
DriverRegistry.register("btdl_ds18b20", BTDLDS18B20Driver)
DriverRegistry.register("btdl_bmx280", BTDLBMx280Driver)
DriverRegistry.register("keysight_34461a", Keysight34461ADriver)
DriverRegistry.register("mock-dmm", MockInstrumentDriver)
DriverRegistry.register("mock_dc_power_supply", MockDCPowerSupplyDriver)
DriverRegistry.register("mock_rnd_320_3005p", MockRND3203005PDriver)
DriverRegistry.register("rnd_ka3005p", RNDKA3005PDriver)
DriverRegistry.register("rpi_cpu_temperature", RaspberryPiCPUTemperatureDriver)

__all__ = (
    "Agilent34401ADriver",
    "BTDLNTCDriver",
    "BTDLDS18B20Driver",
    "BTDLBMx280Driver",
    "DriverRegistry",
    "Keysight34461ADriver",
    "MockDCPowerSupplyDriver",
    "MockInstrumentDriver",
    "MockRND3203005PDriver",
    "RNDKA3005PDriver",
    "RaspberryPiCPUTemperatureDriver",
)
