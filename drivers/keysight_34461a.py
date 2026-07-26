"""Driver for the Keysight 34461A digital multimeter over Linux USBTMC."""

import time
from typing import BinaryIO, Callable

from .base import BaseInstrumentDriver, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError


class Keysight34461ADriver(BaseInstrumentDriver):
    """Communicate with a Keysight 34461A through a USBTMC device node."""

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

    def connect(self) -> None:
        """Open the USBTMC device and configure DC voltage measurement."""
        if self.connected:
            return

        try:
            self.device = self._open_device(
                self.device_path,
                "rb+",
                buffering=0,
            )
            self.connected = True
            for command, delay in (
                ("*CLS", 0.5),
                ("DISP:STAT OFF", 0.5),
                (f"CONF:VOLT:DC {self.voltage_range}", 0.1),
                (f"VOLT:DC:NPLC {self.nplc}", 0.1),
            ):
                self.write(command)
                time.sleep(delay)
        except (OSError, CommunicationError) as exc:
            self._close_device()
            raise ConnectionError("Could not initialize the Keysight 34461A.") from exc

    def disconnect(self) -> None:
        """Restore a safe local state and close the USBTMC device."""
        try:
            if self.device is not None:
                for command, delay in (
                    ("DISP:STAT ON", 0.5),
                    ("VOLT:DC:NPLC 10", 0.1),
                    ("*CLS", 0.5),
                    ("SYST:LOC", 0.5),
                ):
                    self.write(command)
                    time.sleep(delay)
        except CommunicationError:
            pass
        finally:
            self._close_device()

    def _close_device(self) -> None:
        """Close the USBTMC device without sending more commands."""
        device, self.device = self.device, None
        self.connected = False
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
        """Measure DC voltage and return a normalized numeric result."""
        try:
            value = float(self.query("READ?"))
        except (ValueError, CommunicationError) as exc:
            raise MeasurementError(
                "The Keysight 34461A did not return a valid DC voltage."
            ) from exc

        return MeasurementResult(parameter="Voltage DC", value=value, unit="V")
