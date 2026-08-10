"""Driver for the Raspberry Pi Linux thermal-zone CPU sensor."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class RaspberryPiCPUTemperatureDriver(BaseInstrumentDriver):
    """Read CPU temperature from a Linux thermal-zone sysfs file."""

    DEFAULT_ADDRESS = "/sys/class/thermal/thermal_zone0/temp"
    CAPABILITIES = {
        "temperature": MeasurementCapability(
            label="Temperature",
            unit="°C",
        ),
    }

    def __init__(self, address: str = DEFAULT_ADDRESS) -> None:
        super().__init__()
        if not address:
            raise ValueError("A thermal-zone temperature path is required.")
        self.address = address
        self.temperature_path = Path(address)

    def connect(self) -> None:
        """Verify that the kernel temperature file can be read."""
        try:
            self.temperature_path.read_text(encoding="ascii")
        except (OSError, UnicodeError) as exc:
            self.connected = False
            raise ConnectionError(
                f"Could not read Raspberry Pi temperature sensor: {self.address}",
            ) from exc
        self.connected = True

    def disconnect(self) -> None:
        """Close the logical sysfs connection."""
        self.connected = False

    def _require_connection(self) -> None:
        if not self.connected:
            raise CommunicationError(
                "The Raspberry Pi temperature sensor is not connected.",
            )

    def write(self, command: str) -> None:
        """Reject writes because the kernel thermal sensor is read-only."""
        self._require_connection()
        raise CommunicationError(
            f"The Raspberry Pi temperature sensor is read-only: {command}",
        )

    def query(self, command: str) -> str:
        """Return sensor identity or the current temperature in Celsius."""
        self._require_connection()
        normalized = command.strip().upper()
        if normalized == "*IDN?":
            return f"Raspberry Pi,CPU thermal sensor,{self.address}"
        if normalized in {"MEAS:TEMP?", "MEASURE:TEMPERATURE?"}:
            return str(self._read_temperature())
        raise CommunicationError(
            f"Unsupported Raspberry Pi temperature query: {command}",
        )

    def identify(self) -> str:
        """Identify the kernel thermal-zone sensor and its path."""
        return self.query("*IDN?")

    def measure_temperature(self) -> MeasurementResult:
        """Return the CPU temperature normalized to degrees Celsius."""
        return MeasurementResult(
            parameter="Temperature",
            value=float(self.query("MEAS:TEMP?")),
            unit="°C",
        )

    def _read_temperature(self) -> Decimal:
        """Convert the sysfs millidegree value to degrees Celsius."""
        try:
            raw = self.temperature_path.read_text(encoding="ascii").strip()
            value = Decimal(raw) / Decimal("1000")
        except (OSError, UnicodeError, InvalidOperation) as exc:
            raise MeasurementError(
                "Could not read Raspberry Pi CPU temperature.",
            ) from exc
        if not value.is_finite() or not Decimal("-273.15") <= value <= Decimal("1000"):
            raise MeasurementError(
                f"Invalid Raspberry Pi CPU temperature: {raw!r}.",
            )
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
