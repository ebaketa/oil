"""Driver for the Agilent 34401A digital multimeter over a serial port."""

import time
from typing import Any

from .base import BaseInstrumentDriver, FunctionConfiguration, MeasurementResult
from .agilent_34401a_transport import Agilent34401ATransport
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class Agilent34401ADriver(BaseInstrumentDriver):
    """Communicate with an Agilent 34401A through a serial/FTDI adapter."""

    def __init__(
        self,
        port: str | None = None,
        *,
        usb_serial_number: str | None = None,
        baudrate: int = 9600,
        timeout: float = 1,
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
        self.transport: Agilent34401ATransport | None = None
        self._dc_voltage_prepared = False

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
        """Open the serial port without changing instrument settings."""
        if self.connected:
            return

        try:
            self.transport = Agilent34401ATransport(self._resolve_port())
            self.serial_connection = self.transport.ser
            self.connected = True
            self._dc_voltage_prepared = True
        except (OSError, CommunicationError) as exc:
            self._close_connection()
            raise ConnectionError("Could not initialize the Agilent 34401A.") from exc

    def disconnect(self) -> None:
        """Return local control and close the serial port."""
        if self.transport is not None:
            self.transport.close()
            self.transport = None
            self.serial_connection = None
            self.connected = False
            self._dc_voltage_prepared = False
        else:
            self._close_connection()

    def _close_connection(self) -> None:
        """Close the serial connection without sending more commands."""
        connection, self.serial_connection = self.serial_connection, None
        self.transport = None
        self.connected = False
        self._dc_voltage_prepared = False
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

    def _enter_remote(self) -> None:
        """Enter RS-232 remote mode using the model's proven command timing."""
        self.serial_connection.write("SYSTem:REMote\n".encode())
        time.sleep(0.5)

    def _prepare_dc_voltage(self) -> None:
        """Apply the proven 34401A serial DC voltage setup sequence."""
        if self.serial_connection is None:
            raise CommunicationError("The Agilent 34401A is not connected.")
        self.serial_connection.reset_input_buffer()
        self._enter_remote()
        self.serial_connection.write("*CLS\n".encode())
        time.sleep(0.5)
        self.serial_connection.write("CONF:VOLT:DC\n".encode())
        time.sleep(0.1)
        self.serial_connection.write("VOLT:DC:RANG:AUTO ON\n".encode())
        time.sleep(0.1)

    def execute(self, command: str) -> None:
        """Execute a command using 34401A serial error-queue confirmation.

        The 34401A connected over RS-232 can leave ``*OPC?`` waiting after a
        configuration command. Its setting queries provide the authoritative
        completion check, while this method verifies that the command did not
        add a SCPI error.
        """
        self.write(command)
        time.sleep(0.5)

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

    def measure_dc_voltage(self) -> MeasurementResult:
        """Measure DC voltage and return a normalized numeric result."""
        try:
            if self.transport is None:
                raise CommunicationError(
                    "The Agilent 34401A is not connected."
                )
            response = self.transport.get_data()
            if response is None:
                raise CommunicationError(
                    "The Agilent 34401A response timed out."
                )
            value = float(response)
        except ValueError as exc:
            raise MeasurementError(
                f"The Agilent 34401A returned an invalid reading: {response!r}."
            ) from exc
        except CommunicationError as exc:
            raise MeasurementError(
                f"The Agilent 34401A measurement failed: {exc}"
            ) from exc

        return MeasurementResult(parameter="Voltage DC", value=value, unit="V")

    def configure_dc_voltage_auto(self) -> FunctionConfiguration:
        """Enter remote mode before configuring and verifying DC voltage."""
        self._enter_remote()
        return super().configure_dc_voltage_auto()
