"""Unit tests for OIL instrument drivers without physical hardware."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .agilent_34401a import Agilent34401ADriver
from .base import FunctionConfiguration, MeasurementResult
from .exceptions import (
    CommunicationError,
    ConfigurationError,
    ConnectionError,
    MeasurementError,
)
from .factory import create_driver
from .keysight_34461a import Keysight34461ADriver
from .mock import MockInstrumentDriver
from .mock_dc_power_supply import MockDCPowerSupplyDriver
from .registry import DriverRegistry
from .rnd_ka3005p import RNDKA3005PDriver
from .transports import InstrumentTransport
from .transports import MockTransport


class Agilent34401ADriverTests(SimpleTestCase):
    """Verify Agilent serial communication and measurement handling."""

    @patch("drivers.agilent_34401a.time.sleep")
    @patch("serial.tools.list_ports.comports")
    @patch("drivers.transports.serial.serial.Serial")
    def test_connect_prepares_dc_voltage_measurement(
        self,
        serial_factory,
        comports,
        _sleep,
    ):
        """Connecting follows the original reader's initialization lifecycle."""
        connection = MagicMock(is_open=True, in_waiting=0)
        serial_factory.return_value = connection
        comports.return_value = [
            SimpleNamespace(
                serial_number="A9Z22QXP",
                device="/dev/ttyUSB0",
            ),
        ]
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        driver.connect()

        self.assertTrue(driver.connected)
        serial_factory.assert_called_once()
        self.assertEqual(
            serial_factory.call_args.kwargs["stopbits"],
            2,
        )
        self.assertTrue(driver._dc_voltage_prepared)

    @patch("drivers.agilent_34401a.time.sleep")
    @patch("serial.tools.list_ports.comports")
    @patch("drivers.transports.serial.serial.Serial")
    def test_identification_session_returns_local_control(
        self,
        serial_factory,
        comports,
        _sleep,
    ):
        """Identification ends by returning front-panel control."""
        connection = MagicMock(is_open=True, in_waiting=0)
        connection.readline.return_value = b"HEWLETT-PACKARD,34401A,0,1.0\n"
        serial_factory.return_value = connection
        comports.return_value = [
            SimpleNamespace(
                serial_number="A9Z22QXP",
                device="/dev/ttyUSB0",
            ),
        ]
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        with patch.object(driver, "_prepare_dc_voltage"):
            with driver:
                identity = driver.identify()

        self.assertEqual(identity, "HEWLETT-PACKARD,34401A,0,1.0")
        self.assertEqual(
            [call.args[0] for call in connection.write.call_args_list],
            [
                b"*IDN?\n",
                b"SYSTem:LOCal\n",
            ],
        )
        connection.close.assert_called_once()

    def test_display_control_uses_34401a_display_command(self):
        """Task display control emits the documented OFF and ON commands."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        with patch.object(driver, "write") as write:
            driver.set_display_enabled(False)
            driver.set_display_enabled(True)

        self.assertEqual(
            [call.args[0] for call in write.call_args_list],
            ["DISP OFF", "DISP ON"],
        )

    @patch("serial.tools.list_ports.comports")
    def test_port_can_be_discovered_by_usb_serial_number(self, comports):
        """The driver resolves an FTDI port from its configured serial number."""
        comports.return_value = [
            SimpleNamespace(serial_number="OTHER", device="/dev/ttyUSB0"),
            SimpleNamespace(serial_number="A9Z22QXP", device="/dev/ttyUSB1"),
        ]
        driver = Agilent34401ADriver(usb_serial_number="A9Z22QXP")

        self.assertEqual(driver._resolve_port(), "/dev/ttyUSB1")

    @patch("serial.tools.list_ports.comports", return_value=[])
    def test_missing_usb_serial_number_raises_connection_error(self, _comports):
        """Discovery reports a domain error when no matching adapter exists."""
        driver = Agilent34401ADriver(usb_serial_number="missing")

        with self.assertRaises(ConnectionError):
            driver._resolve_port()

    def test_measurement_returns_normalized_result(self):
        """A numeric response becomes a unit-bearing measurement result."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")
        driver.transport = MagicMock(spec=InstrumentTransport)
        driver.transport.is_open = True
        driver.transport.read.return_value = "1.2345"
        driver._prepared_function = "dc_voltage"

        result = driver.measure_dc_voltage()

        driver.transport.write.assert_called_once_with("READ?")
        driver.transport.read.assert_called_once_with(timeout=10)
        self.assertEqual(
            result,
            MeasurementResult(parameter="Voltage DC", value=1.2345, unit="V"),
        )

    @patch("drivers.agilent_34401a.time.sleep")
    def test_ac_voltage_and_resistance_reconfigure_serial_function(self, _sleep):
        """Function changes use the documented SCPI autorange sequences."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")
        driver.transport = MagicMock(spec=InstrumentTransport)
        driver.transport.is_open = True
        driver.transport.read.side_effect = ("2.5", "1000")
        driver._prepared_function = "dc_voltage"

        ac_result = driver.measure_ac_voltage()
        resistance_result = driver.measure_resistance()

        self.assertEqual(
            [call.args[0] for call in driver.transport.write.call_args_list],
            [
                "*CLS",
                "CONF:VOLT:AC",
                "VOLT:AC:RANG:AUTO ON",
                "READ?",
                "*CLS",
                "CONF:RES",
                "RES:RANG:AUTO ON",
                "READ?",
            ],
        )
        self.assertEqual(
            ac_result,
            MeasurementResult(parameter="Voltage AC", value=2.5, unit="V"),
        )
        self.assertEqual(
            resistance_result,
            MeasurementResult(parameter="Resistance", value=1000.0, unit="Ω"),
        )

    def test_measurement_rejects_invalid_response(self):
        """A malformed serial response becomes a measurement error."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")
        driver.transport = MagicMock(spec=InstrumentTransport)
        driver.transport.is_open = True
        driver.transport.read.return_value = "invalid"
        driver._prepared_function = "dc_voltage"

        with self.assertRaises(MeasurementError):
            driver.measure_dc_voltage()

    @patch("drivers.agilent_34401a.time.sleep")
    def test_prepare_dcv_uses_proven_serial_sequence(self, sleep):
        """DCV setup follows the timing proven by the original reader."""
        transport = MagicMock(spec=InstrumentTransport)
        transport.is_open = True
        driver = Agilent34401ADriver(
            port="/dev/ttyUSB0",
            transport=transport,
        )

        driver._prepare_dc_voltage()

        transport.reset_input_buffer.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in transport.write.call_args_list],
            [
                "SYSTem:REMote",
                "*CLS",
                "CONF:VOLT:DC",
                "VOLT:DC:RANG:AUTO ON",
            ],
        )
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.5, 0.5, 0.1, 0.1],
        )

    @patch("drivers.agilent_34401a.time.sleep")
    def test_execute_uses_error_queue_without_opc_query(self, sleep):
        """34401A serial confirmation avoids its blocking OPC query path."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        with (
            patch.object(driver, "write") as write,
            patch.object(driver, "query", return_value='+0,"No error"') as query,
        ):
            driver.execute("CONF:VOLT:DC")

        write.assert_called_once_with("CONF:VOLT:DC")
        sleep.assert_called_once_with(0.5)
        query.assert_called_once_with("SYST:ERR?")

    def test_dcv_auto_uses_agilent_execute_and_read_back(self):
        """34401A DCV mode is confirmed from function and autorange queries."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        with (
            patch.object(driver, "_enter_remote") as enter_remote,
            patch.object(driver, "execute") as execute,
            patch.object(
                driver,
                "query",
                side_effect=['+0,"No error"', '"VOLT"', "1"],
            ),
        ):
            result = driver.configure_dc_voltage_auto()

        enter_remote.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in execute.call_args_list],
            ["CONF:VOLT:DC", "VOLT:DC:RANG:AUTO ON"],
        )
        self.assertEqual(
            result,
            FunctionConfiguration(function="Voltage DC", autorange=True),
        )


class Keysight34461ADriverTests(SimpleTestCase):
    """Verify Keysight USBTMC communication and measurement handling."""

    def test_connect_does_not_send_instrument_commands(self):
        """Connecting opens USBTMC without changing instrument settings."""
        device = MagicMock(closed=False)
        open_device = MagicMock(return_value=device)
        driver = Keysight34461ADriver(
            "/dev/usbtmc2",
            open_device=open_device,
        )

        driver.connect()

        self.assertTrue(driver.connected)
        open_device.assert_called_once_with("/dev/usbtmc2", "rb+", buffering=0)
        device.write.assert_not_called()

    def test_identification_session_returns_local_control(self):
        """Identification ends by returning front-panel control."""
        device = MagicMock(closed=False)
        device.read.return_value = b"KEYSIGHT TECHNOLOGIES,34461A,MY123,1.0\n"
        driver = Keysight34461ADriver(open_device=MagicMock(return_value=device))

        with driver:
            identity = driver.identify()

        self.assertEqual(identity, "KEYSIGHT TECHNOLOGIES,34461A,MY123,1.0")
        self.assertEqual(
            [call.args[0] for call in device.write.call_args_list],
            [b"*IDN?\n", b"SYST:LOC\n"],
        )
        device.close.assert_called_once()

    def test_display_control_uses_truevolt_display_state_command(self):
        """Task display control emits the documented OFF and ON commands."""
        driver = Keysight34461ADriver()

        with patch.object(driver, "write") as write:
            driver.set_display_enabled(False)
            driver.set_display_enabled(True)

        self.assertEqual(
            [call.args[0] for call in write.call_args_list],
            ["DISP OFF", "DISP ON"],
        )

    def test_connect_wraps_device_open_error(self):
        """An inaccessible USBTMC node becomes a connection error."""
        driver = Keysight34461ADriver(
            open_device=MagicMock(side_effect=PermissionError),
        )

        with self.assertRaises(ConnectionError):
            driver.connect()

        self.assertFalse(driver.connected)

    def test_empty_response_raises_communication_error(self):
        """An empty USBTMC read is reported as a communication failure."""
        driver = Keysight34461ADriver()
        driver.device = MagicMock(read=MagicMock(return_value=b""))

        with self.assertRaises(CommunicationError):
            driver.read_response()

    @patch("drivers.keysight_34461a.time.sleep")
    def test_measurement_returns_normalized_result(self, sleep):
        """A numeric USBTMC response becomes an autoranged DCV result."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "write") as write,
            patch.object(driver, "read_response", return_value="-0.015"),
        ):
            result = driver.measure_dc_voltage()

        self.assertEqual(
            [call.args[0] for call in write.call_args_list],
            ["*CLS", "CONF:VOLT:DC", "VOLT:DC:RANG:AUTO ON", "READ?"],
        )
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.5, 0.1, 0.1],
        )
        self.assertEqual(
            result,
            MeasurementResult(parameter="Voltage DC", value=-0.015, unit="V"),
        )

    @patch("drivers.keysight_34461a.time.sleep")
    def test_measurement_loop_configures_dcv_auto_only_once(self, sleep):
        """One connection reuses DCV Auto configuration for later readings."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "write") as write,
            patch.object(driver, "read_response", side_effect=["1.0", "2.0"]),
        ):
            first = driver.measure_dc_voltage()
            second = driver.measure_dc_voltage()

        self.assertEqual(
            [call.args[0] for call in write.call_args_list],
            [
                "*CLS",
                "CONF:VOLT:DC",
                "VOLT:DC:RANG:AUTO ON",
                "READ?",
                "READ?",
            ],
        )
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.5, 0.1, 0.1],
        )
        self.assertEqual(first.value, 1.0)
        self.assertEqual(second.value, 2.0)

    @patch("drivers.keysight_34461a.time.sleep")
    def test_ac_voltage_and_resistance_use_autorange_commands(self, _sleep):
        """AC voltage and resistance return normalized autoranged results."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "write") as write,
            patch.object(driver, "read_response", side_effect=["3.5", "470"]),
        ):
            ac_result = driver.measure_ac_voltage()
            resistance_result = driver.measure_resistance()

        self.assertEqual(
            [call.args[0] for call in write.call_args_list],
            [
                "*CLS",
                "CONF:VOLT:AC",
                "VOLT:AC:RANG:AUTO ON",
                "READ?",
                "*CLS",
                "CONF:RES",
                "RES:RANG:AUTO ON",
                "READ?",
            ],
        )
        self.assertEqual(
            ac_result,
            MeasurementResult(parameter="Voltage AC", value=3.5, unit="V"),
        )
        self.assertEqual(
            resistance_result,
            MeasurementResult(parameter="Resistance", value=470.0, unit="Ω"),
        )

    def test_execute_confirms_completion_and_no_scpi_error(self):
        """A command succeeds only after OPC and error-queue confirmation."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "write") as write,
            patch.object(
                driver,
                "query",
                side_effect=["1", '+0,"No error"'],
            ) as query,
        ):
            driver.execute("VOLT:DC:RANG:AUTO ON")

        write.assert_called_once_with("VOLT:DC:RANG:AUTO ON")
        self.assertEqual(
            [call.args[0] for call in query.call_args_list],
            ["*OPC?", "SYST:ERR?"],
        )

    def test_execute_rejects_scpi_error(self):
        """A completed but rejected command raises a communication error."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "write"),
            patch.object(
                driver,
                "query",
                side_effect=["1", '-113,"Undefined header"'],
            ),
        ):
            with self.assertRaises(CommunicationError):
                driver.execute("INVALID")

    def test_dcv_auto_reads_configuration_back(self):
        """DCV Auto succeeds only when read-back confirms both settings."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "execute") as execute,
            patch.object(
                driver,
                "query",
                side_effect=['+0,"No error"', '"VOLT:DC"', "1"],
            ),
        ):
            result = driver.configure_dc_voltage_auto()

        self.assertEqual(
            [call.args[0] for call in execute.call_args_list],
            ["CONF:VOLT:DC", "VOLT:DC:RANG:AUTO ON"],
        )
        self.assertEqual(
            result,
            FunctionConfiguration(function="Voltage DC", autorange=True),
        )

    def test_dcv_auto_rejects_wrong_read_back_mode(self):
        """A different active function fails configuration verification."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "execute"),
            patch.object(
                driver,
                "query",
                side_effect=['+0,"No error"', '"VOLT:AC"', "1"],
            ),
        ):
            with self.assertRaises(ConfigurationError):
                driver.configure_dc_voltage_auto()

    def test_error_queue_is_drained_until_no_error(self):
        """Stale errors are returned and removed before a new operation."""
        driver = Keysight34461ADriver()

        with patch.object(
            driver,
            "query",
            side_effect=[
                '-410,"Query INTERRUPTED"',
                '-113,"Undefined header"',
                '+0,"No error"',
            ],
        ):
            errors = driver.clear_error_queue()

        self.assertEqual(
            errors,
            (
                '-410,"Query INTERRUPTED"',
                '-113,"Undefined header"',
            ),
        )

    def test_context_manager_always_disconnects(self):
        """Leaving a driver context restores and closes the device."""
        driver = Keysight34461ADriver()

        with (
            patch.object(driver, "connect") as connect,
            patch.object(driver, "disconnect") as disconnect,
        ):
            with driver as active_driver:
                self.assertIs(active_driver, driver)

        connect.assert_called_once()
        disconnect.assert_called_once()


class DriverFactoryTests(SimpleTestCase):
    """Verify stored driver names create the expected implementations."""

    def test_factory_creates_agilent_driver_with_serial_port(self):
        """Agilent inventory configuration maps its address to a serial port."""
        driver = create_driver(
            SimpleNamespace(
                driver="agilent_34401a",
                address="/dev/ttyUSB2",
            ),
        )

        self.assertIsInstance(driver, Agilent34401ADriver)
        self.assertEqual(driver.port, "/dev/ttyUSB2")

    def test_factory_creates_keysight_driver_with_usbtmc_path(self):
        """Keysight inventory configuration maps its address to USBTMC."""
        driver = create_driver(
            SimpleNamespace(
                driver="keysight_34461a",
                address="/dev/usbtmc1",
            ),
        )

        self.assertIsInstance(driver, Keysight34461ADriver)
        self.assertEqual(driver.device_path, "/dev/usbtmc1")

    def test_factory_rejects_an_unregistered_driver_name(self):
        """Unknown inventory names retain the existing factory error."""
        with self.assertRaisesMessage(
            ValueError,
            "Unsupported instrument driver: missing",
        ):
            create_driver(
                SimpleNamespace(driver="missing", address="/dev/missing"),
            )

    def test_factory_creates_mock_driver_with_profile_address(self):
        """Mock inventory configuration maps its address to a simulation."""
        driver = create_driver(
            SimpleNamespace(
                driver="mock-dmm",
                address="mock-dmm://default",
            ),
        )

        self.assertIsInstance(driver, MockInstrumentDriver)
        self.assertEqual(driver.address, "mock-dmm://default")

    def test_factory_creates_mock_dc_power_supply(self):
        """Power-supply inventory maps to its dedicated mock driver."""
        driver = create_driver(
            SimpleNamespace(
                driver="mock_dc_power_supply",
                address="mock-psu://default",
            ),
        )

        self.assertIsInstance(driver, MockDCPowerSupplyDriver)
        self.assertEqual(driver.address, "mock-psu://default")

    def test_factory_creates_rnd_ka3005p_power_supply(self):
        """RND inventory configuration maps its address to a serial port."""
        driver = create_driver(
            SimpleNamespace(
                driver="rnd_ka3005p",
                address="/dev/ttyACM0",
            ),
        )

        self.assertIsInstance(driver, RNDKA3005PDriver)
        self.assertEqual(driver.port, "/dev/ttyACM0")


class DriverRegistryTests(SimpleTestCase):
    """Verify driver discovery and extension through the central registry."""

    def tearDown(self):
        """Remove the test-only alias without changing built-in drivers."""
        DriverRegistry.unregister("test_keysight")

    def test_builtin_drivers_are_registered(self):
        """The registry exposes both persistent built-in driver names."""
        self.assertEqual(
            DriverRegistry.names(),
            (
                "agilent_34401a",
                "keysight_34461a",
                "mock-dmm",
                "mock_dc_power_supply",
                "rnd_ka3005p",
            ),
        )

    def test_registered_driver_can_be_created_without_factory_changes(self):
        """A new registry entry immediately participates in driver creation."""
        DriverRegistry.register("test_keysight", Keysight34461ADriver)

        driver = create_driver(
            SimpleNamespace(
                driver="test_keysight",
                address="/dev/usbtmc9",
            ),
        )

        self.assertIsInstance(driver, Keysight34461ADriver)
        self.assertEqual(driver.device_path, "/dev/usbtmc9")

    def test_duplicate_name_cannot_replace_a_registered_driver(self):
        """A different implementation cannot silently hijack a driver name."""
        with self.assertRaisesMessage(
            ValueError,
            "Driver name is already registered: agilent_34401a",
        ):
            DriverRegistry.register(
                "agilent_34401a",
                Keysight34461ADriver,
            )

    def test_capabilities_are_available_without_creating_a_driver(self):
        """Registry metadata can build forms without touching hardware."""
        capabilities = DriverRegistry.capabilities("mock-dmm")

        self.assertEqual(
            tuple(capabilities),
            (
                "dc_voltage",
                "ac_voltage",
                "dc_current",
                "ac_current",
                "resistance",
                "temperature",
            ),
        )
        capability = capabilities["dc_voltage"]
        self.assertEqual(capability.label, "DC voltage")
        self.assertEqual(capability.unit, "V")
        self.assertTrue(capability.autorange)

        with self.assertRaises(TypeError):
            capabilities["other"] = capability


class MockInstrumentDriverTests(SimpleTestCase):
    """Verify deterministic simulated instrument behavior."""

    def test_context_manager_identifies_and_disconnects(self):
        """The mock follows the same connection lifecycle as real drivers."""
        driver = MockInstrumentDriver()

        with driver:
            identity = driver.identify()
            self.assertTrue(driver.connected)

        self.assertEqual(identity, MockInstrumentDriver.IDENTITY)
        self.assertFalse(driver.connected)
        self.assertEqual(driver.command_history, ("*IDN?",))


class RNDKA3005PDriverTests(SimpleTestCase):
    """Verify RND supply protocol and safety validation without hardware."""

    def create_driver(self, responses=None):
        """Return a driver using an in-memory serial-like transport."""
        transport = MockTransport(responses or {})
        return RNDKA3005PDriver("/dev/ttyACM0", transport=transport)

    def test_identification_uses_documented_command(self):
        """The driver identifies the supply and closes the connection."""
        driver = self.create_driver({"*IDN?": "RND 320-KA3005P V1.3"})

        with driver:
            identity = driver.identify()

        self.assertEqual(identity, "RND 320-KA3005P V1.3")
        self.assertFalse(driver.connected)
        self.assertEqual(driver.transport.command_history, ["*IDN?"])

    def test_voltage_output_and_measurement_commands(self):
        """Voltage programming and output control use channel-one syntax."""
        driver = self.create_driver({"VOUT1?": "12.34"})

        with driver:
            self.assertEqual(driver.set_voltage("12.34"), 12.34)
            driver.enable_output()
            measured = driver.measure_output_voltage()
            driver.disable_output()

        self.assertEqual(measured, 12.34)
        self.assertEqual(
            driver.transport.command_history,
            ["VSET1:12.34", "OUT1", "VOUT1?", "OUT0"],
        )

    @patch("drivers.rnd_ka3005p.time.sleep")
    def test_consecutive_commands_leave_controller_processing_time(self, sleep):
        """Back-to-back writes and queries respect the device command interval."""
        driver = self.create_driver({"VOUT1?": "1.00"})

        with driver:
            driver.set_voltage("1.00")
            driver.measure_output_voltage()

        self.assertTrue(sleep.called)
        self.assertGreater(sleep.call_args.args[0], 0)
        self.assertLessEqual(
            sleep.call_args.args[0],
            driver.COMMAND_INTERVAL_SECONDS,
        )

    def test_current_limit_uses_milliamp_resolution(self):
        """Current programming supports the documented 1 mA steps."""
        driver = self.create_driver()

        with driver:
            self.assertEqual(driver.set_current("1.234"), 1.234)

        self.assertEqual(driver.transport.command_history, ["ISET1:1.234"])

    def test_rejects_unsafe_voltage_and_current_values(self):
        """Values outside device limits or resolution are rejected."""
        driver = self.create_driver()

        with driver:
            for value in ("30.01", "-0.01", "1.001"):
                with self.subTest(voltage=value):
                    with self.assertRaises(ConfigurationError):
                        driver.set_voltage(value)
            for value in ("5.001", "-0.001", "1.0005"):
                with self.subTest(current=value):
                    with self.assertRaises(ConfigurationError):
                        driver.set_current(value)

    @patch("drivers.rnd_ka3005p.SerialTransport")
    def test_connect_uses_documented_9600_8n1_raw_serial(self, transport_class):
        """Production transport uses 9600 baud, one stop bit, no terminator."""
        transport = MagicMock(is_open=True)
        transport_class.return_value = transport
        driver = RNDKA3005PDriver("/dev/ttyUSB0")

        driver.connect()

        transport_class.assert_called_once_with(
            "/dev/ttyUSB0",
            baudrate=9600,
            timeout=1,
            stopbits=1,
            write_termination="",
            response_termination=None,
        )
        self.assertTrue(driver.connected)


class MockDCPowerSupplyDriverTests(SimpleTestCase):
    """Verify deterministic programmable power-supply behavior."""

    def test_identifies_and_starts_with_disabled_zero_volt_output(self):
        """A fresh mock supply is safe and reports its stable identity."""
        driver = MockDCPowerSupplyDriver()

        with driver:
            identity = driver.identify()
            measured_voltage = driver.measure_output_voltage()

        self.assertEqual(identity, driver.IDENTITY)
        self.assertEqual(driver.voltage_setpoint, 0.0)
        self.assertEqual(measured_voltage, 0.0)
        self.assertFalse(driver.output_enabled)

    def test_sets_voltage_from_zero_to_sixty_in_millivolt_steps(self):
        """Boundary and intermediate millivolt setpoints are accepted."""
        driver = MockDCPowerSupplyDriver()

        with driver:
            self.assertEqual(driver.set_voltage(0), 0.0)
            self.assertEqual(driver.set_voltage("12.345"), 12.345)
            self.assertEqual(driver.set_voltage(60), 60.0)
            self.assertEqual(driver.query("VOLT?"), "60.000")

    def test_rejects_out_of_range_and_sub_millivolt_setpoints(self):
        """Unsafe voltages and unsupported resolution are rejected."""
        driver = MockDCPowerSupplyDriver()

        with driver:
            for voltage in (-0.001, 60.001):
                with self.subTest(voltage=voltage):
                    with self.assertRaisesMessage(
                        ConfigurationError,
                        "between 0.000 V and 60.000 V",
                    ):
                        driver.set_voltage(voltage)
            with self.assertRaisesMessage(
                ConfigurationError,
                "0.001 V steps",
            ):
                driver.set_voltage("1.2345")

    def test_output_returns_setpoint_only_while_enabled(self):
        """Output state controls the simulated terminal voltage."""
        driver = MockDCPowerSupplyDriver()

        with driver:
            driver.set_voltage("24.500")
            self.assertEqual(driver.measure_output_voltage(), 0.0)
            driver.enable_output()
            self.assertEqual(driver.measure_output_voltage(), 24.5)
            self.assertTrue(driver.output_enabled)
            driver.disable_output()
            self.assertEqual(driver.measure_output_voltage(), 0.0)

    def test_disconnect_always_disables_output(self):
        """Leaving a session places the simulated supply in a safe state."""
        driver = MockDCPowerSupplyDriver()

        with driver:
            driver.set_voltage(5)
            driver.enable_output()

        self.assertFalse(driver.output_enabled)
        self.assertEqual(driver.voltage_setpoint, 5.0)

    def test_connection_error_profile_is_deterministic(self):
        """The failure profile rejects connection attempts."""
        driver = MockDCPowerSupplyDriver(
            "mock-psu://connection-error",
        )

        with self.assertRaisesMessage(
            ConnectionError,
            "mock DC power supply could not connect",
        ):
            driver.connect()


class MockInstrumentDriverAdditionalTests(SimpleTestCase):
    """Verify deterministic readings and failure profiles."""

    def test_measurements_cycle_through_configured_values(self):
        """Repeated readings deterministically cycle through test values."""
        driver = MockInstrumentDriver(readings=(1.25, 2.5))

        with driver:
            values = [
                driver.measure_dc_voltage().value,
                driver.measure_dc_voltage().value,
                driver.measure_dc_voltage().value,
            ]

        self.assertEqual(values, [1.25, 2.5, 1.25])

    def test_ac_voltage_and_resistance_have_normalized_units(self):
        """The mock exposes both new functions through the shared contract."""
        driver = MockInstrumentDriver(readings=(2.5, 1000))

        with driver:
            ac_result = driver.measure_ac_voltage()
            resistance_result = driver.measure_resistance()

        self.assertEqual(
            ac_result,
            MeasurementResult(parameter="Voltage AC", value=2.5, unit="V"),
        )
        self.assertEqual(
            resistance_result,
            MeasurementResult(parameter="Resistance", value=1000.0, unit="Ω"),
        )

    def test_current_and_temperature_have_realistic_default_readings(self):
        """The extended mock normalizes current and temperature readings."""
        driver = MockInstrumentDriver()

        with driver:
            dc_current = driver.measure_dc_current()
            ac_current = driver.measure_ac_current()
            temperature = driver.measure_temperature()

        self.assertEqual(
            dc_current,
            MeasurementResult(parameter="Current DC", value=0.01, unit="A"),
        )
        self.assertEqual(
            ac_current,
            MeasurementResult(
                parameter="Current AC",
                value=0.00707,
                unit="A",
            ),
        )
        self.assertEqual(
            temperature,
            MeasurementResult(
                parameter="Temperature",
                value=23.0,
                unit="°C",
            ),
        )

    def test_dcv_auto_configuration_uses_standard_scpi_contract(self):
        """The mock supports the shared DC voltage configuration checks."""
        driver = MockInstrumentDriver()

        with driver:
            configuration = driver.configure_dc_voltage_auto()

        self.assertEqual(
            configuration,
            FunctionConfiguration(function="Voltage DC", autorange=True),
        )

    def test_timeout_profile_simulates_measurement_failure(self):
        """The timeout profile raises a domain measurement error."""
        driver = MockInstrumentDriver("mock-dmm://timeout")

        with driver:
            with self.assertRaisesMessage(
                MeasurementError,
                "The mock measurement timed out.",
            ):
                driver.measure_dc_voltage()

    def test_connection_error_profile_simulates_unavailable_hardware(self):
        """The connection-error profile fails before becoming connected."""
        driver = MockInstrumentDriver("mock-dmm://connection-error")

        with self.assertRaisesMessage(
            ConnectionError,
            "The mock instrument could not connect.",
        ):
            driver.connect()

        self.assertFalse(driver.connected)
