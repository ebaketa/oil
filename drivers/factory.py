"""Create OIL instrument drivers from stored inventory configuration."""

from .agilent_34401a import Agilent34401ADriver
from .keysight_34461a import Keysight34461ADriver


def create_driver(instrument):
    """Create the driver configured for an instrument inventory record."""
    if instrument.driver == "agilent_34401a":
        return Agilent34401ADriver(port=instrument.address)

    if instrument.driver == "keysight_34461a":
        return Keysight34461ADriver(device_path=instrument.address)

    raise ValueError(f"Unsupported instrument driver: {instrument.driver}")
