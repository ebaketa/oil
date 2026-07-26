"""Shared contracts for OIL instrument drivers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class MeasurementResult:
    """A normalized numeric result returned by an instrument."""

    parameter: str
    value: float
    unit: str


class BaseInstrumentDriver(ABC):
    """Define the lifecycle and operations shared by instrument drivers."""

    def __init__(self) -> None:
        """Create a disconnected driver."""
        self.connected = False

    def __enter__(self):
        """Connect and return the driver for use in a context manager."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Disconnect when leaving a context manager."""
        self.disconnect()

    @abstractmethod
    def connect(self) -> None:
        """Open and initialize the instrument connection."""

    @abstractmethod
    def disconnect(self) -> None:
        """Restore local control and close the instrument connection."""

    @abstractmethod
    def write(self, command: str) -> None:
        """Send one command to the instrument."""

    @abstractmethod
    def query(self, command: str) -> str:
        """Send one query and return the instrument response."""

    @abstractmethod
    def identify(self) -> str:
        """Return the instrument identification response."""

    @abstractmethod
    def measure_dc_voltage(self) -> MeasurementResult:
        """Measure DC voltage and return a normalized result."""
