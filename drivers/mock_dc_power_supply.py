"""Deterministic mock DC power supply for development and demonstrations."""

from decimal import Decimal, InvalidOperation

from .base import BaseInstrumentDriver
from .exceptions import CommunicationError, ConfigurationError, ConnectionError
from .transports import InstrumentTransport, MockTransport


class MockDCPowerSupplyDriver(BaseInstrumentDriver):
    """Simulate a programmable single-output DC power supply."""

    IDENTITY = "OIL,MOCK-DC-POWER-SUPPLY,0001,1.0"
    MIN_VOLTAGE = Decimal("0.000")
    MAX_VOLTAGE = Decimal("60.000")
    VOLTAGE_STEP = Decimal("0.001")
    CAPABILITIES = {}

    def __init__(
        self,
        address: str = "mock-psu://default",
        *,
        transport: InstrumentTransport | None = None,
    ) -> None:
        """Create a disabled supply with a zero-volt setpoint."""
        super().__init__()
        if not address.startswith("mock-psu://"):
            raise ValueError(
                "Mock DC power supply addresses must start with mock-psu://.",
            )

        self.address = address
        self.profile = address.removeprefix("mock-psu://") or "default"
        self.transport = transport or MockTransport(
            {"*IDN?": self.IDENTITY},
        )
        self._voltage_setpoint = self.MIN_VOLTAGE
        self._output_enabled = False

    @property
    def command_history(self) -> tuple[str, ...]:
        """Return commands received during the driver lifetime."""
        history = getattr(self.transport, "command_history", ())
        return tuple(history)

    @property
    def voltage_setpoint(self) -> float:
        """Return the configured output voltage in volts."""
        return float(self._voltage_setpoint)

    @property
    def output_enabled(self) -> bool:
        """Return whether the simulated output is enabled."""
        return self._output_enabled

    def connect(self) -> None:
        """Open the in-memory power supply connection."""
        if self.profile == "connection-error":
            raise ConnectionError(
                "The mock DC power supply could not connect.",
            )
        self.transport.open()
        self.connected = True

    def disconnect(self) -> None:
        """Disable the output and close the simulated connection."""
        if self.connected:
            self._output_enabled = False
        self.transport.close()
        self.connected = False

    def _require_connection(self) -> None:
        """Reject operations while the supply is disconnected."""
        if not self.connected:
            raise CommunicationError(
                "The mock DC power supply is not connected.",
            )

    def write(self, command: str) -> None:
        """Apply a supported SCPI-like power supply command."""
        self._require_connection()
        normalized = command.strip()
        self.transport.write(normalized)
        upper_command = normalized.upper()

        if upper_command.startswith("VOLT "):
            self._voltage_setpoint = self._validate_voltage(
                normalized.split(maxsplit=1)[1],
            )
            return
        if upper_command in {"OUTP ON", "OUTPUT ON"}:
            self._output_enabled = True
            return
        if upper_command in {"OUTP OFF", "OUTPUT OFF"}:
            self._output_enabled = False
            return

        raise CommunicationError(
            f"Unsupported mock DC power supply command: {command}",
        )

    def query(self, command: str) -> str:
        """Return identification, setpoint, state, or output voltage."""
        self._require_connection()
        normalized = command.strip()
        upper_command = normalized.upper()

        if upper_command == "*IDN?":
            return self.transport.query(normalized)

        self.transport.write(normalized)
        if upper_command in {"VOLT?", "VOLTAGE?"}:
            return self._format_voltage(self._voltage_setpoint)
        if upper_command in {"OUTP?", "OUTPUT?"}:
            return "1" if self._output_enabled else "0"
        if upper_command in {"MEAS:VOLT?", "MEASURE:VOLTAGE?"}:
            voltage = (
                self._voltage_setpoint
                if self._output_enabled
                else self.MIN_VOLTAGE
            )
            return self._format_voltage(voltage)

        raise CommunicationError(
            f"Unsupported mock DC power supply query: {command}",
        )

    def identify(self) -> str:
        """Return the stable simulated supply identity."""
        return self.query("*IDN?")

    def set_voltage(self, voltage) -> float:
        """Set output voltage from 0 to 60 V in exact 1 mV steps."""
        value = self._validate_voltage(voltage)
        self.write(f"VOLT {self._format_voltage(value)}")
        return self.voltage_setpoint

    def enable_output(self) -> None:
        """Enable the simulated DC output."""
        self.write("OUTP ON")

    def disable_output(self) -> None:
        """Disable the simulated DC output."""
        self.write("OUTP OFF")

    def measure_output_voltage(self) -> float:
        """Return zero when disabled or the setpoint when enabled."""
        return float(self.query("MEAS:VOLT?"))

    @classmethod
    def _validate_voltage(cls, voltage) -> Decimal:
        """Return a valid voltage aligned to the 1 mV resolution."""
        try:
            value = Decimal(str(voltage))
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationError("Voltage must be a number.") from exc

        if not value.is_finite():
            raise ConfigurationError("Voltage must be finite.")
        if not cls.MIN_VOLTAGE <= value <= cls.MAX_VOLTAGE:
            raise ConfigurationError(
                "Voltage must be between 0.000 V and 60.000 V.",
            )
        if value % cls.VOLTAGE_STEP != 0:
            raise ConfigurationError(
                "Voltage must use 0.001 V steps.",
            )
        return value.quantize(cls.VOLTAGE_STEP)

    @staticmethod
    def _format_voltage(voltage: Decimal) -> str:
        """Format a voltage with the supported millivolt resolution."""
        return f"{voltage:.3f}"
