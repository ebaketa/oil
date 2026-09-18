"""Driver for the Agilent 34401A digital multimeter over a serial port."""

import math
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

    RESOLUTION_NPLC = {
        "4.5": 0.02,
        "5.5": 1.0,
        "6.5": 10.0,
    }
    RESOLUTION_COUNTS = {
        "4.5": 10_000,
        "5.5": 100_000,
        "6.5": 1_000_000,
    }
    NPLC_VALUES = (0.02, 0.2, 1.0, 2.0, 10.0, 20.0, 100.0, 200.0)
    RESOLUTION_MODES = {
        "4.5_fast": ("4.5", 0.02, False),
        "4.5_slow": ("5.5", 1.0, True),
        "5.5_fast": ("5.5", 0.2, False),
        "5.5_slow": ("6.5", 10.0, True),
        "6.5_fast": ("6.5", 10.0, True),
        "6.5_slow": ("6.5", 100.0, True),
    }

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
            ranges=(0.1, 1.0, 10.0, 100.0, 750.0),
        ),
        "dc_current": MeasurementCapability(
            label="DC current",
            unit="A",
            autorange=True,
            ranges=(0.01, 0.1, 1.0, 3.0),
        ),
        "ac_current": MeasurementCapability(
            label="AC current",
            unit="A",
            autorange=True,
        ),
        "resistance": MeasurementCapability(
            label="Resistance",
            unit="Ω",
            autorange=True,
        ),
        "resistance_4w": MeasurementCapability(
            label="4-wire resistance",
            unit="Ω",
            autorange=True,
        ),
        "frequency": MeasurementCapability(
            label="Frequency",
            unit="Hz",
            autorange=True,
        ),
        "period": MeasurementCapability(
            label="Period",
            unit="s",
            autorange=True,
        ),
        "continuity": MeasurementCapability(
            label="Continuity",
            unit="Ω",
        ),
        "diode": MeasurementCapability(
            label="Diode",
            unit="V",
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
        self._selected_resolutions: dict[str, str] = {}
        self._selected_nplc: dict[str, float] = {}
        self._selected_resolution_modes: dict[str, str] = {}

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
        """Open serial communication without changing the active function."""
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
            self._enter_remote()
            self.connected = True
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
        self._record_command(command)
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
        self._record_command(command)
        if command.strip().upper() == "READ?":
            return self.transport.query(command, timeout=10)
        return self.transport.query(command)

    def identify(self) -> str:
        """Return the instrument identity response."""
        return self.query("*IDN?")

    def read_panel_status(self) -> dict[str, str | float | bool]:
        """Read the active measurement setup without changing it."""
        function_response = self.query("FUNC?").strip().strip('"').upper()
        functions = {
            "VOLT": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLT:DC": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLTAGE": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLTAGE:DC": ("dc_voltage", "VOLT:DC", "Voltage DC", "V"),
            "VOLT:AC": ("ac_voltage", "VOLT:AC", "Voltage AC", "V"),
            "VOLTAGE:AC": ("ac_voltage", "VOLT:AC", "Voltage AC", "V"),
            "CURR": ("dc_current", "CURR:DC", "Current DC", "A"),
            "CURR:DC": ("dc_current", "CURR:DC", "Current DC", "A"),
            "CURRENT": ("dc_current", "CURR:DC", "Current DC", "A"),
            "CURRENT:DC": ("dc_current", "CURR:DC", "Current DC", "A"),
            "CURR:AC": ("ac_current", "CURR:AC", "Current AC", "A"),
            "CURRENT:AC": ("ac_current", "CURR:AC", "Current AC", "A"),
            "RES": ("resistance", "RES", "Resistance", "Ω"),
            "RESISTANCE": ("resistance", "RES", "Resistance", "Ω"),
            "FRES": ("resistance_4w", "FRES", "Resistance 4W", "Ω"),
            "FRESISTANCE": ("resistance_4w", "FRES", "Resistance 4W", "Ω"),
            "FREQ": ("frequency", "FREQ:VOLT", "Frequency", "Hz"),
            "FREQUENCY": ("frequency", "FREQ:VOLT", "Frequency", "Hz"),
            "PER": ("period", "PER:VOLT", "Period", "s"),
            "PERIOD": ("period", "PER:VOLT", "Period", "s"),
            "CONT": ("continuity", None, "Continuity", "Ω"),
            "CONTINUITY": ("continuity", None, "Continuity", "Ω"),
            "DIOD": ("diode", None, "Diode", "V"),
            "DIODE": ("diode", None, "Diode", "V"),
        }
        try:
            function, command, parameter, unit = functions[function_response]
        except KeyError as exc:
            raise CommunicationError(
                f"Unsupported active function reported by the instrument: "
                f"{function_response!r}."
            ) from exc

        autorange = command is not None
        if command is not None:
            autorange_response = (
                self.query(f"{command}:RANG:AUTO?").strip().strip('"').upper()
            )
            autorange = autorange_response in {"1", "+1", "ON"}
        try:
            value = float(self.query("READ?").strip())
            range_value = (
                float(self.query(f"{command}:RANG?").strip())
                if command is not None else None
            )
        except ValueError as exc:
            raise CommunicationError(
                "The instrument returned an invalid panel status value."
            ) from exc

        self._prepared_function = (
            function
            if autorange or range_value is None
            else f"{function}:{range_value:g}"
        )
        self._dc_voltage_prepared = function == "dc_voltage"
        status = {
            "function": function,
            "parameter": parameter,
            "unit": unit,
            "autorange": autorange,
            "range_value": range_value,
            "value": value,
        }
        if function in {
            "dc_voltage",
            "dc_current",
            "resistance",
            "resistance_4w",
        }:
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
            status["nplc"] = nplc
            status["resolution"] = resolution
            try:
                resolution_value = float(
                    self.query(f"{command}:RES?").strip()
                )
                autozero_response = (
                    self.query("ZERO:AUTO?").strip().strip('"').upper()
                )
            except ValueError as exc:
                raise CommunicationError(
                    "The instrument returned invalid resolution status."
                ) from exc
            autozero = autozero_response in {"1", "+1", "ON"}
            counts = range_value / resolution_value
            displayed_resolution = min(
                self.RESOLUTION_COUNTS,
                key=lambda mode: abs(self.RESOLUTION_COUNTS[mode] - counts),
            )
            exact_modes = {
                (0.02, False): "4.5_fast",
                (1.0, True): "4.5_slow",
                (0.2, False): "5.5_fast",
                (100.0, True): "6.5_slow",
            }
            resolution_mode = exact_modes.get((nplc, autozero))
            if abs(nplc - 10.0) <= 1e-9 and autozero:
                remembered_mode = self._selected_resolution_modes.get(function)
                resolution_mode = (
                    remembered_mode
                    if remembered_mode in {"5.5_slow", "6.5_fast"}
                    else "5.5_slow_or_6.5_fast"
                )
            if resolution_mode in self.RESOLUTION_MODES:
                displayed_resolution = self.RESOLUTION_MODES[
                    resolution_mode
                ][0]
            status["resolution"] = displayed_resolution
            status["resolution_mode"] = resolution_mode
            status["autozero"] = autozero
            status["decimals"] = max(
                0,
                -math.floor(
                    math.log10(
                        range_value / self.RESOLUTION_COUNTS[displayed_resolution],
                    )
                ),
            )
        return status

    def set_resolution(self, function: str, resolution: str) -> float:
        """Set and verify display resolution through the function NPLC."""
        commands = {
            "dc_voltage": "VOLT:DC",
            "dc_current": "CURR:DC",
            "resistance": "RES",
            "resistance_4w": "FRES",
        }
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
        self._selected_nplc.pop(function, None)
        self._selected_resolution_modes.pop(function, None)
        return actual_nplc

    def set_resolution_mode(self, function: str, mode: str) -> dict:
        """Apply a front-panel-equivalent NPLC and autozero mode."""
        commands = {
            "dc_voltage": "VOLT:DC",
            "dc_current": "CURR:DC",
            "resistance": "RES",
            "resistance_4w": "FRES",
        }
        if function not in commands:
            raise CommunicationError(
                "Resolution control is unavailable for this function."
            )
        if mode not in self.RESOLUTION_MODES:
            raise CommunicationError("Unsupported resolution mode.")
        digits, requested_nplc, requested_autozero = self.RESOLUTION_MODES[mode]
        command = commands[function]
        self.execute(f"{command}:NPLC {requested_nplc:g}")
        self.execute(f"ZERO:AUTO {'ON' if requested_autozero else 'OFF'}")
        try:
            actual_nplc = float(self.query(f"{command}:NPLC?").strip())
            actual_autozero = self.query("ZERO:AUTO?").strip() in {"1", "+1"}
            range_value = float(self.query(f"{command}:RANG?").strip())
        except ValueError as exc:
            raise CommunicationError(
                "The instrument returned invalid resolution mode status."
            ) from exc
        if (
            abs(actual_nplc - requested_nplc) > 1e-9
            or actual_autozero != requested_autozero
        ):
            raise CommunicationError(
                "The instrument did not apply the requested resolution mode."
            )
        self._selected_resolution_modes[function] = mode
        self._selected_nplc[function] = requested_nplc
        self._selected_resolutions.pop(function, None)
        return {
            "resolution": digits,
            "resolution_mode": mode,
            "nplc": actual_nplc,
            "autozero": actual_autozero,
            "decimals": max(
                0,
                -math.floor(
                    math.log10(
                        range_value / self.RESOLUTION_COUNTS[digits],
                    )
                ),
            ),
        }

    def set_nplc(self, function: str, nplc: float) -> float:
        """Set and verify an exact supported integration time."""
        commands = {
            "dc_voltage": "VOLT:DC",
            "dc_current": "CURR:DC",
            "resistance": "RES",
            "resistance_4w": "FRES",
        }
        if function not in commands:
            raise CommunicationError(
                "NPLC control is unavailable for this function."
            )
        if nplc not in self.NPLC_VALUES:
            raise CommunicationError("Unsupported NPLC value.")
        command = commands[function]
        self.execute(f"{command}:NPLC {nplc:g}")
        try:
            actual_nplc = float(self.query(f"{command}:NPLC?").strip())
        except ValueError as exc:
            raise CommunicationError(
                "The instrument returned an invalid NPLC value."
            ) from exc
        if abs(actual_nplc - nplc) > 1e-9:
            raise CommunicationError(
                "The instrument did not apply the requested NPLC value."
            )
        self._selected_nplc[function] = nplc
        self._selected_resolutions.pop(function, None)
        self._selected_resolution_modes.pop(function, None)
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

    def set_display_enabled(self, enabled: bool) -> None:
        """Enable or disable front-panel display updates."""
        self.write(f"DISP {'ON' if enabled else 'OFF'}")

    def recover_panel_error(self) -> None:
        """Return a failed panel acquisition to idle without leaving remote."""
        if self.transport is None or not self.transport.is_open:
            return
        self.transport.reset_input_buffer()
        self.write("ABOR")
        time.sleep(0.1)
        self._prepared_function = None
        self._dc_voltage_prepared = False

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
                f"Unsupported Agilent 34401A DC voltage range: "
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

    def measure_ac_voltage(
        self,
        voltage_range: float | None = None,
    ) -> MeasurementResult:
        """Measure AC voltage using automatic or selected range."""
        if (
            voltage_range is not None
            and voltage_range not in self.CAPABILITIES["ac_voltage"].ranges
        ):
            raise MeasurementError(
                f"Unsupported Agilent 34401A AC voltage range: "
                f"{voltage_range} V."
            )
        configuration = (
            "ac_voltage"
            if voltage_range is None
            else f"ac_voltage:{voltage_range:g}"
        )
        return self._measure_function(
            function=configuration,
            configure_command=(
                "CONF:VOLT:AC"
                if voltage_range is None
                else f"CONF:VOLT:AC {voltage_range:g}"
            ),
            autorange_command=None,
            parameter="Voltage AC",
            unit="V",
        )

    def measure_dc_current(
        self,
        current_range: float | None = None,
    ) -> MeasurementResult:
        """Select DC current and read back its resulting range mode."""
        if (
            current_range is not None
            and current_range not in self.CAPABILITIES["dc_current"].ranges
        ):
            raise MeasurementError(
                f"Unsupported Agilent 34401A DC current range: "
                f"{current_range} A."
            )
        configuration = (
            "dc_current"
            if current_range is None
            else f"dc_current:{current_range:g}"
        )
        return self._measure_function(
            function=configuration,
            configure_command=(
                "CONF:CURR:DC"
                if current_range is None
                else f"CONF:CURR:DC {current_range:g}"
            ),
            autorange_command=None,
            parameter="Current DC",
            unit="A",
        )

    def measure_ac_current(self) -> MeasurementResult:
        """Measure AC current using autorange."""
        return self._measure_function(
            function="ac_current",
            configure_command="CONF:CURR:AC",
            autorange_command=None,
            parameter="Current AC",
            unit="A",
        )

    def measure_resistance(self) -> MeasurementResult:
        """Measure two-wire resistance using autorange."""
        return self._measure_function(
            function="resistance",
            configure_command="CONF:RES",
            autorange_command=None,
            parameter="Resistance",
            unit="Ω",
        )

    def measure_resistance_4w(self) -> MeasurementResult:
        """Measure four-wire resistance using autorange."""
        return self._measure_function(
            function="resistance_4w",
            configure_command="CONF:FRES",
            autorange_command=None,
            parameter="Resistance 4W",
            unit="Ω",
        )

    def measure_frequency(self) -> MeasurementResult:
        """Measure frequency using automatic input-voltage ranging."""
        return self._measure_function(
            function="frequency",
            configure_command="CONF:FREQ",
            autorange_command=None,
            parameter="Frequency",
            unit="Hz",
        )

    def measure_period(self) -> MeasurementResult:
        """Measure period using automatic input-voltage ranging."""
        return self._measure_function(
            function="period",
            configure_command="CONF:PER",
            autorange_command=None,
            parameter="Period",
            unit="s",
        )

    def measure_continuity(self) -> MeasurementResult:
        """Run the fixed-range continuity test."""
        return self._measure_function(
            function="continuity",
            configure_command="CONF:CONT",
            autorange_command=None,
            parameter="Continuity",
            unit="Ω",
        )

    def measure_diode(self) -> MeasurementResult:
        """Measure diode forward voltage in the instrument's fixed range."""
        return self._measure_function(
            function="diode",
            configure_command="CONF:DIOD",
            autorange_command=None,
            parameter="Diode",
            unit="V",
        )

    def _measure_function(
        self,
        *,
        function: str,
        configure_command: str,
        autorange_command: str | None,
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
                if autorange_command is not None:
                    self.write(autorange_command)
                    time.sleep(0.1)
                base_function = function.split(":", maxsplit=1)[0]
                selected_resolution = self._selected_resolutions.get(
                    base_function,
                )
                selected_nplc = self._selected_nplc.get(base_function)
                selected_mode = self._selected_resolution_modes.get(
                    base_function,
                )
                resolution_commands = {
                    "dc_voltage": "VOLT:DC",
                    "dc_current": "CURR:DC",
                    "resistance": "RES",
                    "resistance_4w": "FRES",
                }
                if selected_mode and base_function in resolution_commands:
                    _, nplc, autozero = self.RESOLUTION_MODES[selected_mode]
                    self.write(
                        f"{resolution_commands[base_function]}:NPLC {nplc:g}"
                    )
                    self.write(f"ZERO:AUTO {'ON' if autozero else 'OFF'}")
                    time.sleep(0.1)
                elif (
                    (selected_nplc is not None or selected_resolution)
                    and base_function in resolution_commands
                ):
                    nplc = (
                        selected_nplc
                        if selected_nplc is not None
                        else self.RESOLUTION_NPLC[selected_resolution]
                    )
                    self.write(
                        f"{resolution_commands[base_function]}:NPLC {nplc:g}"
                    )
                    time.sleep(0.1)
                self._prepared_function = function
                self._dc_voltage_prepared = function.startswith("dc_voltage")

            self.write("READ?")
            response = self.transport.read(timeout=10)
            value = float(response)
        except ValueError as exc:
            self._prepared_function = None
            self._dc_voltage_prepared = False
            raise MeasurementError(
                f"The Agilent 34401A returned an invalid reading: {response!r}."
            ) from exc
        except CommunicationError as exc:
            self._prepared_function = None
            self._dc_voltage_prepared = False
            raise MeasurementError(
                f"The Agilent 34401A {parameter} measurement failed: {exc}"
            ) from exc

        return MeasurementResult(parameter=parameter, value=value, unit=unit)

    def configure_dc_voltage_auto(self) -> FunctionConfiguration:
        """Enter remote mode before configuring and verifying DC voltage."""
        self._enter_remote()
        return super().configure_dc_voltage_auto()
