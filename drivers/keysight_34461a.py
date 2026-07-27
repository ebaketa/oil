"""Driver for the Keysight 34461A digital multimeter over Linux USBTMC."""

import time
from typing import BinaryIO, Callable

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class Keysight34461ADriver(BaseInstrumentDriver):
    """Communicate with a Keysight 34461A through a USBTMC device node."""

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
        device_path: str = "/dev/usbtmc0",
        *,
        voltage_range: float = 10,
        nplc: float = 100,
        open_device: Callable[..., BinaryIO] = open,
    ) -> None:
        """Configure the driver without opening the USBTMC device."""
        super().__init__()
        self.device_path = device_path
        self.voltage_range = voltage_range
        self.nplc = nplc
        self._open_device = open_device
        self.device: BinaryIO | None = None
        self._dc_voltage_prepared = False
        self._prepared_function: str | None = None

    def connect(self) -> None:
        """Open the USBTMC device without changing instrument settings."""
        if self.connected:
            return

        try:
            self.device = self._open_device(
                self.device_path,
                "rb+",
                buffering=0,
            )
            self.connected = True
        except (OSError, CommunicationError) as exc:
            self._close_device()
            raise ConnectionError("Could not initialize the Keysight 34461A.") from exc

    def disconnect(self) -> None:
        """Return local control and close the USBTMC device."""
        try:
            if self.device is not None:
                self.write("SYST:LOC")
        except CommunicationError:
            pass
        finally:
            self._close_device()

    def _close_device(self) -> None:
        """Close the USBTMC device without sending more commands."""
        device, self.device = self.device, None
        self.connected = False
        self._dc_voltage_prepared = False
        self._prepared_function = None
        if device is not None and not device.closed:
            device.close()

    def write(self, command: str) -> None:
        """Send one newline-terminated SCPI command."""
        if self.device is None:
            raise CommunicationError("The Keysight 34461A is not connected.")

        try:
            self.device.write(f"{command.rstrip()}\n".encode())
        except OSError as exc:
            raise CommunicationError("Could not write to the Keysight 34461A.") from exc

    def read_response(self, size: int = 400) -> str:
        """Read and decode one response from the USBTMC device."""
        if self.device is None:
            raise CommunicationError("The Keysight 34461A is not connected.")

        try:
            response = self.device.read(size)
        except OSError as exc:
            raise CommunicationError("Could not read from the Keysight 34461A.") from exc

        if not response:
            raise CommunicationError("The Keysight 34461A returned an empty response.")
        return response.decode("utf-8", errors="replace").strip()

    def query(self, command: str) -> str:
        """Send one SCPI query and return its response."""
        self.write(command)
        return self.read_response()

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def measure_dc_voltage(self) -> MeasurementResult:
        """Measure DC voltage in autorange and return a normalized result."""
        return self._measure_function(
            function="dc_voltage",
            configure_command="CONF:VOLT:DC",
            autorange_command="VOLT:DC:RANG:AUTO ON",
            parameter="Voltage DC",
            unit="V",
        )

    def measure_ac_voltage(self) -> MeasurementResult:
        """Measure AC voltage in autorange and return a normalized result."""
        return self._measure_function(
            function="ac_voltage",
            configure_command="CONF:VOLT:AC",
            autorange_command="VOLT:AC:RANG:AUTO ON",
            parameter="Voltage AC",
            unit="V",
        )

    def measure_resistance(self) -> MeasurementResult:
        """Measure two-wire resistance in autorange."""
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
            if self._prepared_function != function:
                self.write("*CLS")
                time.sleep(0.5)
                self.write(configure_command)
                time.sleep(0.1)
                self.write(autorange_command)
                time.sleep(0.1)
                self._prepared_function = function
                self._dc_voltage_prepared = function == "dc_voltage"

            self.write("READ?")
            time.sleep(0.5)
            value = float(self.read_response())
        except (ValueError, CommunicationError) as exc:
            raise MeasurementError(
                f"The Keysight 34461A did not return a valid {parameter}."
            ) from exc

        return MeasurementResult(parameter=parameter, value=value, unit=unit)
