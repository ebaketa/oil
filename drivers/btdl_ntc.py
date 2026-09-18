"""Driver for the Baketa BTDL-NTC temperature instrument."""

import math
import time

import serial

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .transports import InstrumentTransport, SerialTransport


class BTDLNTCDriver(BaseInstrumentDriver):
    """Read a BTDL-NTC over its newline-delimited SCPI serial interface."""

    CAPABILITIES = {
        "temperature": MeasurementCapability(
            label="Temperature",
            unit="°C",
        ),
    }
    BAUDRATE = 19200
    DEVICE_NAME = "BTDL-NTC"
    ERROR_SENTINEL = 9.9e37
    ERROR_QUEUE_CAPACITY = 8
    STARTUP_DELAY_SECONDS = 3.0

    def __init__(
        self,
        port: str,
        *,
        timeout: float = 1,
        transport: InstrumentTransport | None = None,
    ) -> None:
        """Store the documented 19200 baud, 8N1 serial configuration."""
        super().__init__()
        if not port:
            raise ValueError("A serial port is required.")
        self.port = port
        self.timeout = timeout
        self._transport_override = transport
        self.transport = transport

    def connect(self) -> None:
        """Open the serial interface without changing device state."""
        if self.connected:
            return
        try:
            if self.transport is None:
                self.transport = SerialTransport(
                    self.port,
                    baudrate=self.BAUDRATE,
                    timeout=self.timeout,
                    response_timeout=self.timeout,
                    stopbits=serial.STOPBITS_ONE,
                    write_termination="\n",
                    response_termination="\n",
                )
            self.transport.open()
            if self._transport_override is None:
                # Opening the CH340 serial port resets the controller. Wait for
                # firmware startup, then discard any boot-time serial output.
                time.sleep(self.STARTUP_DELAY_SECONDS)
                self.transport.reset_input_buffer()
            self.connected = True
        except (OSError, CommunicationError) as exc:
            self._close()
            raise ConnectionError(
                f"Could not initialize the {self.DEVICE_NAME} on {self.port}.",
            ) from exc

    def disconnect(self) -> None:
        """Close the serial interface."""
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

    def _require_connection(self) -> InstrumentTransport:
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError(f"The {self.DEVICE_NAME} is not connected.")
        return self.transport

    def write(self, command: str) -> None:
        """Send one SCPI command and record it for diagnostics."""
        transport = self._require_connection()
        self._record_command(command)
        transport.write(command)

    def query(self, command: str) -> str:
        """Send one SCPI query and return its newline-terminated response."""
        transport = self._require_connection()
        self._record_command(command)
        return transport.query(command, timeout=self.timeout).strip()

    def identify(self) -> str:
        """Return the manufacturer, model, serial number, and firmware."""
        return self.query("*IDN?")

    def reset_device(self) -> None:
        """Reset the ADC interface and verify command completion."""
        self.execute("*RST")

    def clear_status(self) -> None:
        """Clear the firmware error queue and verify command completion."""
        self.execute("*CLS")

    def error_count(self) -> int:
        """Return the number of entries waiting in the firmware error queue."""
        response = self.query("SYST:ERR:COUNT?")
        try:
            count = int(response)
        except ValueError as exc:
            raise CommunicationError(
                f"The {self.DEVICE_NAME} returned an invalid error count: "
                f"{response!r}.",
            ) from exc
        if not 0 <= count <= self.ERROR_QUEUE_CAPACITY:
            raise CommunicationError(
                f"The {self.DEVICE_NAME} returned an invalid error count: {count}.",
            )
        return count

    def measure_temperature(self) -> MeasurementResult:
        """Take one ADC sample and return degrees Celsius."""
        response = self.query("MEAS:TEMP?")
        try:
            value = float(response)
        except ValueError as exc:
            raise MeasurementError(
                f"The BTDL-NTC returned an invalid temperature: {response!r}.",
            ) from exc

        if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
            error = self.query("SYST:ERR:NEXT?")
            raise MeasurementError(
                f"The BTDL-NTC sensor reading failed: {error}.",
            )

        return MeasurementResult(
            parameter="Temperature",
            value=value,
            unit="°C",
        )
