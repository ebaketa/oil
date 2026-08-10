"""Deterministic simulator for the RND Lab 320-3005P power supply."""

from decimal import Decimal, InvalidOperation

from .exceptions import CommunicationError, ConfigurationError, ConnectionError
from .rnd_ka3005p import RNDKA3005PDriver


class MockRND3203005PDriver(RNDKA3005PDriver):
    """Simulate the single-output 30 V / 5 A RND supply in memory."""

    IDENTITY = "RND 320-3005P V1.0 (OIL simulator)"
    ADDRESS_SCHEME = "mock-rnd-psu://"
    MAX_TOLERANCE_MV = Decimal("30000")
    TOLERANCE_PATTERN = (
        Decimal("-1"),
        Decimal("-0.5"),
        Decimal("0"),
        Decimal("0.5"),
        Decimal("1"),
        Decimal("0"),
    )

    def __init__(self, address: str = "mock-rnd-psu://default") -> None:
        """Create a disconnected simulator with a safely disabled output."""
        if not address.startswith(self.ADDRESS_SCHEME):
            raise ValueError(
                "Mock RND 320-3005P addresses must start with "
                "mock-rnd-psu://.",
            )
        # Do not create a serial transport; this subclass implements the wire
        # protocol entirely in memory.
        super().__init__(address)
        self.address = address
        self.profile = address.removeprefix(self.ADDRESS_SCHEME) or "default"
        self._voltage_setpoint = self.MIN_VOLTAGE
        self._current_setpoint = self.MIN_CURRENT
        self._output_enabled = False
        self._output_tolerance_mv = Decimal("0")
        self._actual_output_voltage = self.MIN_VOLTAGE
        self._tolerance_index = 0
        self._command_history: list[str] = []

    @property
    def command_history(self) -> tuple[str, ...]:
        """Return all accepted commands and queries in execution order."""
        return tuple(self._command_history)

    @property
    def voltage_setpoint(self) -> float:
        return float(self._voltage_setpoint)

    @property
    def current_setpoint(self) -> float:
        return float(self._current_setpoint)

    @property
    def output_enabled(self) -> bool:
        return self._output_enabled

    @property
    def output_tolerance_mv(self) -> float:
        """Return the configured maximum absolute output error in mV."""
        return float(self._output_tolerance_mv)

    def measure_actual_output_voltage(self) -> float:
        """Expose the unrounded terminal voltage to virtual test equipment."""
        self._require_connection()
        if not self._output_enabled:
            return 0.0
        return float(self._actual_output_voltage)

    def set_output_tolerance_mv(self, tolerance_mv) -> float:
        """Configure a deterministic output error within ±tolerance mV."""
        try:
            value = Decimal(str(tolerance_mv))
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationError("Output tolerance must be a number.") from exc
        if not value.is_finite():
            raise ConfigurationError("Output tolerance must be finite.")
        if not Decimal("0") <= value <= self.MAX_TOLERANCE_MV:
            raise ConfigurationError(
                "Output tolerance must be between 0 and 30000 mV.",
            )
        self._output_tolerance_mv = value
        self._tolerance_index = 0
        self._actual_output_voltage = self._voltage_setpoint
        return float(value)

    def _apply_output_tolerance(self) -> None:
        """Choose the next repeatable error inside the configured interval."""
        fraction = self.TOLERANCE_PATTERN[
            self._tolerance_index % len(self.TOLERANCE_PATTERN)
        ]
        self._tolerance_index += 1
        offset = fraction * self._output_tolerance_mv / Decimal("1000")
        self._actual_output_voltage = min(
            self.MAX_VOLTAGE,
            max(self.MIN_VOLTAGE, self._voltage_setpoint + offset),
        )

    def connect(self) -> None:
        """Open the simulated connection without touching setpoints."""
        if self.profile == "connection-error":
            raise ConnectionError("The mock RND 320-3005P could not connect.")
        self.connected = True

    def disconnect(self) -> None:
        """Disable the simulated output and close the connection."""
        self._output_enabled = False
        self.connected = False

    def _require_connection(self) -> None:
        if not self.connected:
            raise CommunicationError("The mock RND 320-3005P is not connected.")

    def write(self, command: str) -> None:
        """Apply one command from the physical supply's serial protocol."""
        self._require_connection()
        normalized = command.strip().upper()
        self._command_history.append(normalized)

        if normalized.startswith("VSET1:"):
            self._voltage_setpoint = self._validate_decimal(
                normalized.partition(":")[2],
                minimum=self.MIN_VOLTAGE,
                maximum=self.MAX_VOLTAGE,
                step=self.VOLTAGE_STEP,
                label="Voltage",
            )
            self._apply_output_tolerance()
            return
        if normalized.startswith("ISET1:"):
            self._current_setpoint = self._validate_decimal(
                normalized.partition(":")[2],
                minimum=self.MIN_CURRENT,
                maximum=self.MAX_CURRENT,
                step=self.CURRENT_STEP,
                label="Current",
            )
            return
        if normalized == "OUT1":
            self._output_enabled = True
            return
        if normalized == "OUT0":
            self._output_enabled = False
            return
        raise CommunicationError(
            f"Unsupported mock RND 320-3005P command: {command}",
        )

    def query(self, command: str) -> str:
        """Return identity, programmed values, or deterministic readings."""
        self._require_connection()
        normalized = command.strip().upper()
        self._command_history.append(normalized)

        if normalized == "*IDN?":
            return self.IDENTITY
        if normalized == "VSET1?":
            return f"{self._voltage_setpoint:.2f}"
        if normalized == "ISET1?":
            return f"{self._current_setpoint:.3f}"
        if normalized == "VOUT1?":
            value = self._actual_output_voltage if self._output_enabled else Decimal("0")
            return f"{value:.2f}"
        if normalized == "IOUT1?":
            # Without a simulated load the output draws no current.
            return "0.000"
        if normalized == "OUT?":
            return "1" if self._output_enabled else "0"
        raise CommunicationError(
            f"Unsupported mock RND 320-3005P query: {command}",
        )
