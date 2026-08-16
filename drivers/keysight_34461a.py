"""Driver for the Keysight 34461A digital multimeter over Linux USBTMC."""

import time
from typing import BinaryIO, Callable

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .transports import InstrumentTransport, USBTMCTransport


class Keysight34461ADriver(BaseInstrumentDriver):
    """Communicate with a Keysight 34461A through a USBTMC device node."""

    CAPABILITIES = {
        "dc_voltage": MeasurementCapability(
            label="DC voltage",
            unit="V",
            autorange=True,
            ranges=(0.1, 1.0, 10.0, 100.0, 1000.0),
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
        response_timeout: float = 10,
        open_device: Callable[..., BinaryIO] = open,
        transport: InstrumentTransport | None = None,
    ) -> None:
        """Configure the driver without opening the USBTMC device."""
        super().__init__()
        self.device_path = device_path
        self.voltage_range = voltage_range
        self.nplc = nplc
        self.response_timeout = response_timeout
        self._open_device = open_device
        self.transport = transport or USBTMCTransport(
            device_path,
            open_device=open_device,
        )
        self._dc_voltage_prepared = False
        self._prepared_function: str | None = None

    def connect(self) -> None:
        """Open the USBTMC device without changing instrument settings."""
        if self.connected:
            return

        try:
            self.transport.open()
            self.connected = True
        except (OSError, CommunicationError) as exc:
            self._close_device()
            raise ConnectionError("Could not initialize the Keysight 34461A.") from exc

    def disconnect(self) -> None:
        """Return local control and close the USBTMC device."""
        try:
            if self.transport.is_open:
                self.write("SYST:LOC")
        except CommunicationError:
            pass
        finally:
            self._close_device()

    def _close_device(self) -> None:
        """Close the USBTMC device without sending more commands."""
        self.connected = False
        self._dc_voltage_prepared = False
        self._prepared_function = None
        try:
            self.transport.close()
        except CommunicationError:
            pass

    @property
    def device(self) -> BinaryIO | None:
        """Expose the USBTMC handle for backwards-compatible diagnostics."""
        return getattr(self.transport, "device", None)

    @device.setter
    def device(self, value: BinaryIO | None) -> None:
        """Replace the USBTMC handle in compatibility tests."""
        if not hasattr(self.transport, "device"):
            raise AttributeError("The configured transport has no device handle.")
        self.transport.device = value

    def write(self, command: str) -> None:
        """Send one newline-terminated SCPI command."""
        if not self.transport.is_open:
            raise CommunicationError("The Keysight 34461A is not connected.")
        self.transport.write(command)

    def read_response(self, size: int = 400) -> str:
        """Read and decode one response from the USBTMC device."""
        if not self.transport.is_open:
            raise CommunicationError("The Keysight 34461A is not connected.")
        return self.transport.read(timeout=self.response_timeout)

    def query(self, command: str) -> str:
        """Send one SCPI query and return its response."""
        return self.transport.query(command)

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def set_display_enabled(self, enabled: bool) -> None:
        """Enable or disable front-panel display updates."""
        self.write(f"DISP {'ON' if enabled else 'OFF'}")

    def measure_dc_voltage(
        self,
        voltage_range: float | None = None,
    ) -> MeasurementResult:
        """Measure DC voltage using autorange or a supported fixed range."""
        if (
            voltage_range is not None
            and voltage_range not in self.CAPABILITIES["dc_voltage"].ranges
        ):
            raise MeasurementError(
                f"Unsupported Keysight 34461A DC voltage range: "
                f"{voltage_range} V."
            )
        configuration = (
            "dc_voltage"
            if voltage_range is None
            else f"dc_voltage:{voltage_range:g}"
        )
        return self._measure_function(
            function=configuration,
            configure_command=(
                "CONF:VOLT:DC"
                if voltage_range is None
                else f"CONF:VOLT:DC {voltage_range:g}"
            ),
            autorange_command=(
                "VOLT:DC:RANG:AUTO ON"
                if voltage_range is None
                else "VOLT:DC:RANG:AUTO OFF"
            ),
            parameter="Voltage DC",
            unit="V",
        )

    def prepare_measurement(self, function: str) -> None:
        """Configure a task measurement function before its first trigger."""
        settings = {
            "dc_voltage": ("CONF:VOLT:DC", "VOLT:DC:RANG:AUTO ON"),
            "ac_voltage": ("CONF:VOLT:AC", "VOLT:AC:RANG:AUTO ON"),
            "resistance": ("CONF:RES", "RES:RANG:AUTO ON"),
        }
        try:
            configure_command, autorange_command = settings[function]
        except KeyError as exc:
            raise MeasurementError(
                f"The Keysight 34461A does not support {function!r}.",
            ) from exc
        self._prepare_function(
            function,
            configure_command,
            autorange_command,
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
            self._prepare_function(
                function,
                configure_command,
                autorange_command,
            )
            self.write("READ?")
            value = float(self.read_response())
        except (ValueError, CommunicationError) as exc:
            raise MeasurementError(
                f"The Keysight 34461A did not return a valid {parameter}."
            ) from exc

        return MeasurementResult(parameter=parameter, value=value, unit=unit)

    def _prepare_function(
        self,
        function: str,
        configure_command: str,
        autorange_command: str,
    ) -> None:
        """Configure one measurement function once per connection."""
        if self._prepared_function == function:
            return
        self.write("*CLS")
        time.sleep(0.5)
        self.write(configure_command)
        time.sleep(0.1)
        self.write(autorange_command)
        time.sleep(0.1)
        self._prepared_function = function
        self._dc_voltage_prepared = function.startswith("dc_voltage")
