"""Create OIL instrument drivers from stored inventory configuration."""

from .registry import DriverRegistry


def create_driver(instrument):
    """Create the driver configured for an instrument inventory record."""
    return DriverRegistry.create(instrument)
