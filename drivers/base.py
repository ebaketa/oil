"""Shared contracts for OIL instrument drivers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar, Mapping, Self

from .exceptions import CommunicationError, ConfigurationError, MeasurementError

if TYPE_CHECKING:
    from main.models import Instrument


@dataclass(frozen=True)
class MeasurementResult:
    """A normalized numeric result returned by an instrument."""

    parameter: str
    value: float
    unit: str


@dataclass(frozen=True)
class FunctionConfiguration:
    """A function configuration read back from an instrument."""

    function: str
    autorange: bool


@dataclass(frozen=True)
class MeasurementCapability:
    """Describe one measurement function exposed by a driver."""

    label: str
    unit: str
    autorange: bool = False
    ranges: tuple[float, ...] = ()
    nplc: tuple[float, ...] = ()


class BaseInstrumentDriver(ABC):
    """Define the lifecycle and operations shared by instrument drivers."""

    CAPABILITIES: ClassVar[Mapping[str, MeasurementCapability]] = {}

    @classmethod
    def capabilities(cls) -> Mapping[str, MeasurementCapability]:
        """Return immutable measurement capabilities without connecting."""
        return MappingProxyType(dict(cls.CAPABILITIES))

    @classmethod
    def from_instrument(cls, instrument: "Instrument") -> Self:
        """Create a driver from a stored instrument inventory record."""
        return cls(instrument.address)

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

    def execute(self, command: str) -> None:
        """Execute a command and verify completion without a SCPI error."""
        self.write(command)

        completed = self.query("*OPC?").strip()
        try:
            command_completed = int(completed) == 1
        except ValueError:
            command_completed = False

        if not command_completed:
            raise CommunicationError(
                f"The instrument did not complete command: {command}"
            )

        error = self.query("SYST:ERR?").strip()
        error_code = error.split(",", maxsplit=1)[0].strip()
        try:
            command_succeeded = int(error_code) == 0
        except ValueError:
            command_succeeded = False

        if not command_succeeded:
            raise CommunicationError(
                f"The instrument rejected command {command!r}: {error}"
            )

    def clear_error_queue(self, maximum_errors: int = 20) -> tuple[str, ...]:
        """Read and remove stale SCPI errors before a new operation."""
        errors = []

        for _index in range(maximum_errors + 1):
            response = self.query("SYST:ERR?").strip()
            error_code = response.split(",", maxsplit=1)[0].strip()
            try:
                code = int(error_code)
            except ValueError as exc:
                raise CommunicationError(
                    f"Invalid SCPI error response: {response}"
                ) from exc

            if code == 0:
                return tuple(errors)
            errors.append(response)

        raise CommunicationError(
            "The SCPI error queue could not be cleared."
        )

    def configure_dc_voltage_auto(self) -> FunctionConfiguration:
        """Select DC voltage autorange and verify the resulting mode."""
        self.clear_error_queue()
        self.execute("CONF:VOLT:DC")
        self.execute("VOLT:DC:RANG:AUTO ON")

        function = self.query("FUNC?").strip().strip('"').upper()
        autorange_response = (
            self.query("VOLT:DC:RANG:AUTO?").strip().strip('"').upper()
        )
        dc_voltage_names = {"VOLT", "VOLT:DC", "VOLTAGE", "VOLTAGE:DC"}
        autorange_enabled = autorange_response in {"1", "+1", "ON"}

        if function not in dc_voltage_names:
            raise ConfigurationError(
                f"Expected DC voltage mode, but instrument reported {function!r}."
            )
        if not autorange_enabled:
            raise ConfigurationError(
                "DC voltage autorange was not enabled by the instrument."
            )

        return FunctionConfiguration(
            function="Voltage DC",
            autorange=True,
        )

    def measure_dc_voltage(self) -> MeasurementResult:
        """Measure DC voltage and return a normalized result."""
        raise MeasurementError("This driver does not support DC voltage.")

    def measure_ac_voltage(self) -> MeasurementResult:
        """Measure AC voltage and return a normalized result."""
        raise MeasurementError("This driver does not support AC voltage.")

    def measure_resistance(self) -> MeasurementResult:
        """Measure two-wire resistance and return a normalized result."""
        raise MeasurementError("This driver does not support resistance.")
