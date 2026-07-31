"""Deterministic instrument driver for development and demonstrations."""

from collections.abc import Iterable
from itertools import cycle

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .transports import InstrumentTransport, MockTransport


class MockInstrumentDriver(BaseInstrumentDriver):
    """Simulate a digital multimeter without opening physical hardware."""

    DEFAULT_READINGS = (1.0, 1.001, 0.999, 1.002)
    FUNCTION_READINGS = {
        "dc_voltage": (1.0, 1.001, 0.999, 1.002),
        "ac_voltage": (0.707, 0.708, 0.706, 0.707),
        "dc_current": (0.010, 0.0101, 0.0099, 0.0102),
        "ac_current": (0.00707, 0.00708, 0.00706, 0.00707),
        "resistance": (1000.0, 1000.5, 999.5, 1001.0),
        "temperature": (23.0, 23.1, 23.0, 22.9),
    }
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
        "dc_current": MeasurementCapability(
            label="DC current",
            unit="A",
            autorange=True,
        ),
        "ac_current": MeasurementCapability(
            label="AC current",
            unit="A",
            autorange=True,
        ),
        "resistance": MeasurementCapability(
            label="Resistance",
            unit="Ω",
            autorange=True,
        ),
        "temperature": MeasurementCapability(
            label="Temperature",
            unit="°C",
        ),
    }

    def __init__(
        self,
        address: str = "mock-dmm://default",
        *,
        readings: Iterable[float] | None = None,
        transport: InstrumentTransport | None = None,
    ) -> None:
        """Configure a deterministic simulated instrument."""
        super().__init__()
        if not address.startswith("mock-dmm://"):
            raise ValueError(
                "Mock DMM addresses must start with mock-dmm://.",
            )

        custom_values = None if readings is None else tuple(readings)
        if custom_values is not None and not custom_values:
            raise ValueError("Mock driver readings cannot be empty.")

        self.address = address
        self.profile = address.removeprefix("mock-dmm://") or "default"
        self._readings = (
            cycle(custom_values)
            if custom_values is not None
            else None
        )
        self._function_readings = {
            function: cycle(values)
            for function, values in self.FUNCTION_READINGS.items()
        }
        self.transport = transport or MockTransport(
            {
                "*IDN?": self.IDENTITY,
                "*OPC?": "1",
                "SYST:ERR?": '+0,"No error"',
                "FUNC?": '"VOLT:DC"',
                "VOLT:DC:RANG:AUTO?": "1",
            },
        )

    @property
    def command_history(self) -> tuple[str, ...]:
        """Return commands received during the current driver lifetime."""
        history = getattr(self.transport, "command_history", ())
        return tuple(history)

    def connect(self) -> None:
        """Open an in-memory connection to the simulated instrument."""
        if self.profile == "connection-error":
            raise ConnectionError("The mock instrument could not connect.")
        self.transport.open()
        self.connected = True

    def disconnect(self) -> None:
        """Close the in-memory simulated connection."""
        self.transport.close()
        self.connected = False

    def _require_connection(self) -> None:
        """Reject operations while the simulated instrument is disconnected."""
        if not self.connected:
            raise CommunicationError("The mock instrument is not connected.")

    def write(self, command: str) -> None:
        """Record one simulated SCPI command."""
        self._require_connection()
        self.transport.write(command)

    def query(self, command: str) -> str:
        """Record a query and return its deterministic SCPI response."""
        self._require_connection()
        try:
            return self.transport.query(command)
        except CommunicationError as exc:
            raise CommunicationError(
                f"Unsupported mock query: {command}"
            ) from exc

    def identify(self) -> str:
        """Return a stable simulated instrument identity."""
        return self.query("*IDN?")

    def measure_dc_voltage(self) -> MeasurementResult:
        """Return the next deterministic simulated DC voltage."""
        return self._measure("dc_voltage", "Voltage DC", "V")

    def measure_ac_voltage(self) -> MeasurementResult:
        """Return the next deterministic simulated AC voltage."""
        return self._measure("ac_voltage", "Voltage AC", "V")

    def measure_dc_current(self) -> MeasurementResult:
        """Return the next deterministic simulated DC current."""
        return self._measure("dc_current", "Current DC", "A")

    def measure_ac_current(self) -> MeasurementResult:
        """Return the next deterministic simulated AC current."""
        return self._measure("ac_current", "Current AC", "A")

    def measure_resistance(self) -> MeasurementResult:
        """Return the next deterministic simulated resistance."""
        return self._measure("resistance", "Resistance", "Ω")

    def measure_temperature(self) -> MeasurementResult:
        """Return the next deterministic simulated temperature."""
        return self._measure("temperature", "Temperature", "°C")

    def _measure(
        self,
        function: str,
        parameter: str,
        unit: str,
    ) -> MeasurementResult:
        """Return the next reading or the configured simulated failure."""
        self._require_connection()
        if self.profile == "timeout":
            raise MeasurementError("The mock measurement timed out.")
        if self.profile == "measurement-error":
            raise MeasurementError("The mock measurement failed.")

        return MeasurementResult(
            parameter=parameter,
            value=float(
                next(self._readings)
                if self._readings is not None
                else next(self._function_readings[function])
            ),
            unit=unit,
        )
