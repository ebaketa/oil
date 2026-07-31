"""Driver for the Agilent 34401A digital multimeter over a serial port."""

import time

from .base import (
    BaseInstrumentDriver,
    FunctionConfiguration,
    MeasurementCapability,
    MeasurementResult,
)
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .transports import InstrumentTransport, SerialTransport


class Agilent34401ADriver(BaseInstrumentDriver):
    """Communicate with an Agilent 34401A through a serial/FTDI adapter."""

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
        port: str | None = None,
        *,
        usb_serial_number: str | None = None,
        baudrate: int = 9600,
        timeout: float = 1,
        voltage_range: float = 10,
        nplc: float = 100,
        transport: InstrumentTransport | None = None,
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
        self._transport_override = transport
        self.transport = transport
        self.serial_connection = getattr(transport, "connection", None)
        self._dc_voltage_prepared = False
        self._prepared_function: str | None = None

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
        """Open serial communication and apply the proven DCV Auto setup."""
        if self.connected:
            return

        try:
            if self.transport is None:
                self.transport = SerialTransport(
                    self._resolve_port(),
                    baudrate=self.baudrate,
                    timeout=self.timeout,
                )
            self.transport.open()
            time.sleep(0.5)
            self.serial_connection = getattr(
                self.transport,
                "connection",
                None,
            )
            self._prepare_dc_voltage()
            self.connected = True
            self._dc_voltage_prepared = True
            self._prepared_function = "dc_voltage"
        except (OSError, CommunicationError) as exc:
            self._close_connection()
            raise ConnectionError("Could not initialize the Agilent 34401A.") from exc

    def disconnect(self) -> None:
        """Return local control and close the serial port."""
        transport = self.transport
        if transport is not None and transport.is_open:
            try:
                transport.write("SYSTem:LOCal")
            except CommunicationError:
                pass
        self._close_connection()

    def _close_connection(self) -> None:
        """Close the serial connection without sending more commands."""
        transport = self.transport
        self.serial_connection = None
        self.connected = False
        self._dc_voltage_prepared = False
        self._prepared_function = None
        if transport is not None:
            try:
                transport.close()
            except CommunicationError:
                pass
        self.transport = self._transport_override

    def write(self, command: str) -> None:
        """Send one newline-terminated SCPI command."""
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError("The Agilent 34401A is not connected.")
        self.transport.write(command)

    def read_response(self) -> str:
        """Read and decode one response from the serial port."""
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError("The Agilent 34401A is not connected.")
        return self.transport.read()

    def query(self, command: str) -> str:
        """Send one SCPI query and return its response."""
        if self.transport is None:
            raise CommunicationError("The Agilent 34401A is not connected.")
        return self.transport.query(command)

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def set_display_enabled(self, enabled: bool) -> None:
        """Enable or disable front-panel display updates."""
        self.write(f"DISP {'ON' if enabled else 'OFF'}")

    def _enter_remote(self) -> None:
        """Enter RS-232 remote mode using the model's proven command timing."""
        self.write("SYSTem:REMote")
        time.sleep(0.5)

    def _prepare_dc_voltage(self) -> None:
        """Apply the proven 34401A serial DC voltage setup sequence."""
        if self.transport is None or not self.transport.is_open:
            raise CommunicationError("The Agilent 34401A is not connected.")
        self.transport.reset_input_buffer()
        self._enter_remote()
        self.write("*CLS")
        time.sleep(0.5)
        self.write("CONF:VOLT:DC")
        time.sleep(0.1)
        self.write("VOLT:DC:RANG:AUTO ON")
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
        return self._measure_function(
            function="dc_voltage",
            configure_command="CONF:VOLT:DC",
            autorange_command="VOLT:DC:RANG:AUTO ON",
            parameter="Voltage DC",
            unit="V",
        )

    def measure_ac_voltage(self) -> MeasurementResult:
        """Measure AC voltage using autorange."""
        return self._measure_function(
            function="ac_voltage",
            configure_command="CONF:VOLT:AC",
            autorange_command="VOLT:AC:RANG:AUTO ON",
            parameter="Voltage AC",
            unit="V",
        )

    def measure_resistance(self) -> MeasurementResult:
        """Measure two-wire resistance using autorange."""
        return self._measure_function(
            function="resistance",
            configure_command="CONF:RES",
            autorange_command="RES:RANG:AUTO ON",
            parameter="Resistance",
            unit="Ω",
        )

    def _measure_function(
        self,
        *,
        function: str,
        configure_command: str,
        autorange_command: str,
        parameter: str,
        unit: str,
    ) -> MeasurementResult:
        """Configure one function when needed and return its next reading."""
        try:
            if self.transport is None:
                raise CommunicationError(
                    "The Agilent 34401A is not connected."
                )
            if self._prepared_function != function:
                self.transport.reset_input_buffer()
                self.write("*CLS")
                time.sleep(0.5)
                self.write(configure_command)
                time.sleep(0.1)
                self.write(autorange_command)
                time.sleep(0.1)
                self._prepared_function = function
                self._dc_voltage_prepared = function == "dc_voltage"

            self.write("READ?")
            response = self.transport.read(timeout=10)
            value = float(response)
        except ValueError as exc:
            raise MeasurementError(
                f"The Agilent 34401A returned an invalid reading: {response!r}."
            ) from exc
        except CommunicationError as exc:
            raise MeasurementError(
                f"The Agilent 34401A {parameter} measurement failed: {exc}"
            ) from exc

        return MeasurementResult(parameter=parameter, value=value, unit=unit)

    def configure_dc_voltage_auto(self) -> FunctionConfiguration:
        """Enter remote mode before configuring and verifying DC voltage."""
        self._enter_remote()
        return super().configure_dc_voltage_auto()
