"""Driver for the RND Lab 320-KA3005P programmable power supply."""

from decimal import Decimal, InvalidOperation
import time

import serial

from .base import BaseInstrumentDriver
from .exceptions import CommunicationError, ConfigurationError, ConnectionError
from .transports import InstrumentTransport, SerialTransport


class RNDKA3005PDriver(BaseInstrumentDriver):
    """Control one RND 320-KA3005P over its USB virtual COM or RS-232 port."""

    DEVICE_TYPE = "power_supply"
    MIN_VOLTAGE = Decimal("0.00")
    MAX_VOLTAGE = Decimal("30.00")
    VOLTAGE_STEP = Decimal("0.01")
    MIN_CURRENT = Decimal("0.000")
    MAX_CURRENT = Decimal("5.000")
    CURRENT_STEP = Decimal("0.001")
    CAPABILITIES = {}
    COMMAND_INTERVAL_SECONDS = 0.06
    VOLTAGE_SETTLING_SECONDS = 0.15

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 1,
        transport: InstrumentTransport | None = None,
    ) -> None:
        """Store the documented 9600 baud, 8N1 serial configuration."""
        super().__init__()
        if not port:
            raise ValueError("A serial port is required.")
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._transport_override = transport
        self.transport = transport
        self._last_command_at: float | None = None

    def connect(self) -> None:
        """Open the serial interface without changing output settings."""
        if self.connected:
            return
        try:
            if self.transport is None:
                self.transport = SerialTransport(
                    self.port,
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                    stopbits=serial.STOPBITS_ONE,
                    write_termination="",
                    response_termination=None,
                )
            self.transport.open()
            self.connected = True
        except (OSError, CommunicationError) as exc:
            self._close()
            raise ConnectionError(
                "Could not initialize the RND 320-KA3005P.",
            ) from exc

    def disconnect(self) -> None:
        """Close remote communication without changing the configured output."""
        self._close()

    def _close(self) -> None:
        """Close the transport and restore an injected test transport."""
        transport = self.transport
        self.connected = False
        if transport is not None:
            try:
                transport.close()
            except CommunicationError:
                pass
        self.transport = self._transport_override

    def write(self, command: str) -> None:
        """Send one command using the supply's unterminated wire format."""
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError("The RND 320-KA3005P is not connected.")
        self._pace_command()
        self.transport.write(command)
        self._last_command_at = time.monotonic()

    def query(self, command: str) -> str:
        """Send a query and return its ASCII response."""
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError("The RND 320-KA3005P is not connected.")
        self._pace_command()
        try:
            return self.transport.query(command, timeout=2).strip()
        finally:
            self._last_command_at = time.monotonic()

    def _pace_command(self) -> None:
        """Leave enough processing time between controller commands."""
        if self._last_command_at is None:
            return
        remaining = (
            self.COMMAND_INTERVAL_SECONDS
            - (time.monotonic() - self._last_command_at)
        )
        if remaining > 0:
            time.sleep(remaining)

    def identify(self) -> str:
        """Return the model and firmware identification."""
        return self.query("*IDN?")

    def set_voltage(self, voltage) -> float:
        """Set channel-one voltage from 0.00 V to 30.00 V."""
        value = self._validate_decimal(
            voltage,
            minimum=self.MIN_VOLTAGE,
            maximum=self.MAX_VOLTAGE,
            step=self.VOLTAGE_STEP,
            label="Voltage",
        )
        self.write(f"VSET1:{value:.2f}")
        return float(value)

    def set_current(self, current) -> float:
        """Set channel-one current limit from 0.000 A to 5.000 A."""
        value = self._validate_decimal(
            current,
            minimum=self.MIN_CURRENT,
            maximum=self.MAX_CURRENT,
            step=self.CURRENT_STEP,
            label="Current",
        )
        self.write(f"ISET1:{value:.3f}")
        return float(value)

    def enable_output(self) -> None:
        """Enable the output."""
        self.write("OUT1")

    def disable_output(self) -> None:
        """Disable the output."""
        self.write("OUT0")

    def measure_output_voltage(self) -> float:
        """Read the actual channel-one output voltage."""
        return self._parse_number(self.query("VOUT1?"), "output voltage")

    def measure_output_current(self) -> float:
        """Read the actual channel-one output current."""
        return self._parse_number(self.query("IOUT1?"), "output current")

    @staticmethod
    def _parse_number(response: str, label: str) -> float:
        """Convert a numeric device response into a finite float."""
        try:
            value = Decimal(response)
        except InvalidOperation as exc:
            raise CommunicationError(
                f"The supply returned an invalid {label}: {response!r}.",
            ) from exc
        if not value.is_finite():
            raise CommunicationError(
                f"The supply returned an invalid {label}: {response!r}.",
            )
        return float(value)

    @staticmethod
    def _validate_decimal(value, *, minimum, maximum, step, label) -> Decimal:
        """Validate a finite, bounded value at the device resolution."""
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ConfigurationError(f"{label} must be a number.") from exc
        if not normalized.is_finite():
            raise ConfigurationError(f"{label} must be finite.")
        if not minimum <= normalized <= maximum:
            raise ConfigurationError(
                f"{label} must be between {minimum} and {maximum}.",
            )
        if normalized % step != 0:
            raise ConfigurationError(
                f"{label} must use {step} steps.",
            )
        return normalized.quantize(step)
