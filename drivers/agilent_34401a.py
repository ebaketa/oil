"""Driver for the Agilent 34401A digital multimeter over a serial port."""

import time
from typing import Any

from .base import BaseInstrumentDriver, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class Agilent34401ADriver(BaseInstrumentDriver):
    """Communicate with an Agilent 34401A through a serial/FTDI adapter."""

    def __init__(
        self,
        port: str | None = None,
        *,
        usb_serial_number: str | None = None,
        baudrate: int = 9600,
        timeout: float = 10,
        voltage_range: float = 10,
        nplc: float = 100,
    ) -> None:
        """Configure the driver without opening the serial port."""
        super().__init__()
        if port is None and usb_serial_number is None:
            raise ValueError("A serial port or USB serial number is required.")

        self.port = port
        self.usb_serial_number = usb_serial_number
        self.baudrate = baudrate
        self.timeout = timeout
        self.voltage_range = voltage_range
        self.nplc = nplc
        self.serial_connection: Any | None = None

    def _resolve_port(self) -> str:
        """Return the configured port or discover it by USB serial number."""
        if self.port:
            return self.port

        from serial.tools import list_ports

        for candidate in list_ports.comports():
            if candidate.serial_number == self.usb_serial_number:
                return candidate.device

        raise ConnectionError(
            f"No serial port found for USB serial number {self.usb_serial_number}."
        )

    def connect(self) -> None:
        """Open the serial port and configure DC voltage measurement."""
        if self.connected:
            return

        import serial

        try:
            self.serial_connection = serial.Serial(
                port=self._resolve_port(),
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
            )
            self.serial_connection.reset_input_buffer()
            self.connected = True
            for command, delay in (
                ("SYST:REM", 0.5),
                ("DISP OFF", 0.5),
                ("*CLS", 0.5),
                (f"CONF:VOLT:DC {self.voltage_range}", 0.1),
                (f"VOLT:DC:NPLC {self.nplc}", 0.1),
            ):
                self.write(command)
                time.sleep(delay)
        except (OSError, serial.SerialException, CommunicationError) as exc:
            self._close_connection()
            raise ConnectionError("Could not initialize the Agilent 34401A.") from exc

    def disconnect(self) -> None:
        """Restore the display and local control, then close the serial port."""
        try:
            if self.serial_connection is not None:
                self.write("DISP ON")
                time.sleep(0.5)
                self.write("SYST:LOC")
        except CommunicationError:
            pass
        finally:
            self._close_connection()

    def _close_connection(self) -> None:
        """Close the serial connection without sending more commands."""
        connection, self.serial_connection = self.serial_connection, None
        self.connected = False
        if connection is not None and connection.is_open:
            connection.close()

    def write(self, command: str) -> None:
        """Send one newline-terminated SCPI command."""
        if self.serial_connection is None or not self.serial_connection.is_open:
            raise CommunicationError("The Agilent 34401A is not connected.")

        try:
            self.serial_connection.write(f"{command.rstrip()}\n".encode())
        except OSError as exc:
            raise CommunicationError("Could not write to the Agilent 34401A.") from exc

    def read_response(self) -> str:
        """Read and decode one response from the serial port."""
        if self.serial_connection is None or not self.serial_connection.is_open:
            raise CommunicationError("The Agilent 34401A is not connected.")

        try:
            response = self.serial_connection.readline()
        except OSError as exc:
            raise CommunicationError("Could not read from the Agilent 34401A.") from exc

        if not response:
            raise CommunicationError("The Agilent 34401A response timed out.")
        return response.decode("utf-8", errors="replace").strip()

    def query(self, command: str) -> str:
        """Send one SCPI query and return its response."""
        self.write(command)
        return self.read_response()

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def measure_dc_voltage(self) -> MeasurementResult:
        """Measure DC voltage and return a normalized numeric result."""
        try:
            value = float(self.query("READ?"))
        except (ValueError, CommunicationError) as exc:
            raise MeasurementError(
                "The Agilent 34401A did not return a valid DC voltage."
            ) from exc

        return MeasurementResult(parameter="Voltage DC", value=value, unit="V")
