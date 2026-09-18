"""Driver for the Keysight 34461A digital multimeter over Linux USBTMC."""

import math
import time
from typing import BinaryIO, Callable

from .base import BaseInstrumentDriver, MeasurementCapability, MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .transports import InstrumentTransport, USBTMCTransport


class Keysight34461ADriver(BaseInstrumentDriver):
    """Communicate with a Keysight 34461A through a USBTMC device node."""

    RESOLUTION_NPLC = {"4.5": 0.02, "5.5": 1.0, "6.5": 10.0}
    RESOLUTION_COUNTS = {"4.5": 10_000, "5.5": 100_000, "6.5": 1_000_000}

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
        self._selected_resolutions: dict[str, str] = {}

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
        self._record_command(command)
        self.transport.write(command)

    def read_response(self, size: int = 400) -> str:
        """Read and decode one response from the USBTMC device."""
        if not self.transport.is_open:
            raise CommunicationError("The Keysight 34461A is not connected.")
        return self.transport.read(timeout=self.response_timeout)

    def query(self, command: str) -> str:
        """Send one SCPI query and return its response."""
        self._record_command(command)
        return self.transport.query(command)

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def set_display_enabled(self, enabled: bool) -> None:
        """Enable or disable front-panel display updates."""
        self.write(f"DISP {'ON' if enabled else 'OFF'}")

    def read_panel_status(self) -> dict[str, str | float | bool | int]:
        """Read the active measurement setup without changing it."""
        function_response = self.query("FUNC?").strip().strip('"').upper()
        functions = {
            "VOLT": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLT:DC": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLT:AC": ("ac_voltage", "VOLT:AC", "Voltage AC", "V"),
            "RES": ("resistance", "RES", "Resistance", "Ω"),
        }
        try:
            function, command, parameter, unit = functions[function_response]
        except KeyError as exc:
            raise CommunicationError(
                f"Unsupported active function reported by the instrument: "
                f"{function_response!r}."
            ) from exc
        autorange_response = self.query(f"{command}:RANG:AUTO?").strip().upper()
        autorange = autorange_response in {"1", "+1", "ON"}
        try:
            value = float(self.query("READ?").strip())
            range_value = float(self.query(f"{command}:RANG?").strip())
        except ValueError as exc:
            raise CommunicationError(
                "The instrument returned an invalid panel status value."
            ) from exc
        status = {
            "function": function,
            "parameter": parameter,
            "unit": unit,
            "autorange": autorange,
            "range_value": range_value,
            "value": value,
        }
        if function in {"dc_voltage", "resistance"}:
            try:
                nplc = float(self.query(f"{command}:NPLC?").strip())
            except ValueError as exc:
                raise CommunicationError(
                    "The instrument returned an invalid NPLC value."
                ) from exc
            resolution = min(
                self.RESOLUTION_NPLC,
                key=lambda mode: abs(self.RESOLUTION_NPLC[mode] - nplc),
            )
            status.update(
                nplc=nplc,
                resolution=resolution,
                decimals=self.decimal_places(range_value, resolution),
            )
        self._prepared_function = (
            function if autorange else f"{function}:{range_value:g}"
        )
        return status

    def set_resolution(self, function: str, resolution: str) -> float:
        """Set and verify measurement resolution through NPLC."""
        commands = {"dc_voltage": "VOLT:DC", "resistance": "RES"}
        if function not in commands:
            raise CommunicationError(
                "Resolution control is unavailable for this function."
            )
        if resolution not in self.RESOLUTION_NPLC:
            raise CommunicationError("Unsupported resolution.")
        command = commands[function]
        requested_nplc = self.RESOLUTION_NPLC[resolution]
        self.execute(f"{command}:NPLC {requested_nplc:g}")
        try:
            actual_nplc = float(self.query(f"{command}:NPLC?").strip())
        except ValueError as exc:
            raise CommunicationError(
                "The instrument returned an invalid NPLC value."
            ) from exc
        if abs(actual_nplc - requested_nplc) > 1e-9:
            raise CommunicationError(
                "The instrument did not apply the requested resolution."
            )
        self._selected_resolutions[function] = resolution
        return actual_nplc

    @classmethod
    def decimal_places(cls, range_value: float, resolution: str) -> int:
        """Return display decimal places for a range and digit mode."""
        return max(
            0,
            -math.floor(
                math.log10(range_value / cls.RESOLUTION_COUNTS[resolution])
            ),
        )

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
        base_function = function.split(":", maxsplit=1)[0]
        selected_resolution = self._selected_resolutions.get(base_function)
        resolution_commands = {"dc_voltage": "VOLT:DC", "resistance": "RES"}
        if selected_resolution and base_function in resolution_commands:
            nplc = self.RESOLUTION_NPLC[selected_resolution]
            self.write(f"{resolution_commands[base_function]}:NPLC {nplc:g}")
            time.sleep(0.1)
        self._prepared_function = function
        self._dc_voltage_prepared = function.startswith("dc_voltage")
