"""Deterministic instrument driver for development and demonstrations."""

from collections.abc import Iterable
from itertools import cycle

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class MockInstrumentDriver(BaseInstrumentDriver):
    """Simulate a digital multimeter without opening physical hardware."""

    DEFAULT_READINGS = (1.0, 1.001, 0.999, 1.002)
    IDENTITY = "OIL,MOCK-DMM,0001,1.0"
    CAPABILITIES = {
        "dc_voltage": MeasurementCapability(
            label="DC voltage",
            unit="V",
            autorange=True,
        ),
        "ac_voltage": MeasurementCapability(
            label="AC voltage",
            unit="V",
            autorange=True,
        ),
        "resistance": MeasurementCapability(
            label="Resistance",
            unit="Ω",
            autorange=True,
        ),
    }

    def __init__(
        self,
        address: str = "mock://default",
        *,
        readings: Iterable[float] | None = None,
    ) -> None:
        """Configure a deterministic simulated instrument."""
        super().__init__()
        if not address.startswith("mock://"):
            raise ValueError("Mock driver addresses must start with mock://.")

        values = tuple(self.DEFAULT_READINGS if readings is None else readings)
        if not values:
            raise ValueError("Mock driver readings cannot be empty.")

        self.address = address
        self.profile = address.removeprefix("mock://") or "default"
        self._readings = cycle(values)
        self._commands: list[str] = []

    @property
    def command_history(self) -> tuple[str, ...]:
        """Return commands received during the current driver lifetime."""
        return tuple(self._commands)

    def connect(self) -> None:
        """Open an in-memory connection to the simulated instrument."""
        if self.profile == "connection-error":
            raise ConnectionError("The mock instrument could not connect.")
        self.connected = True

    def disconnect(self) -> None:
        """Close the in-memory simulated connection."""
        self.connected = False

    def _require_connection(self) -> None:
        """Reject operations while the simulated instrument is disconnected."""
        if not self.connected:
            raise CommunicationError("The mock instrument is not connected.")

    def write(self, command: str) -> None:
        """Record one simulated SCPI command."""
        self._require_connection()
        self._commands.append(command.rstrip())

    def query(self, command: str) -> str:
        """Record a query and return its deterministic SCPI response."""
        self.write(command)
        responses = {
            "*IDN?": self.IDENTITY,
            "*OPC?": "1",
            "SYST:ERR?": '+0,"No error"',
            "FUNC?": '"VOLT:DC"',
            "VOLT:DC:RANG:AUTO?": "1",
        }
        try:
            return responses[command.rstrip()]
        except KeyError as exc:
            raise CommunicationError(
                f"Unsupported mock query: {command}"
            ) from exc

    def identify(self) -> str:
        """Return a stable simulated instrument identity."""
        return self.query("*IDN?")

    def measure_dc_voltage(self) -> MeasurementResult:
        """Return the next deterministic simulated DC voltage."""
        return self._measure("Voltage DC", "V")

    def measure_ac_voltage(self) -> MeasurementResult:
        """Return the next deterministic simulated AC voltage."""
        return self._measure("Voltage AC", "V")

    def measure_resistance(self) -> MeasurementResult:
        """Return the next deterministic simulated resistance."""
        return self._measure("Resistance", "Ω")

    def _measure(self, parameter: str, unit: str) -> MeasurementResult:
        """Return the next reading or the configured simulated failure."""
        self._require_connection()
        if self.profile == "timeout":
            raise MeasurementError("The mock measurement timed out.")
        if self.profile == "measurement-error":
            raise MeasurementError("The mock measurement failed.")

        return MeasurementResult(
            parameter=parameter,
            value=float(next(self._readings)),
            unit=unit,
        )
