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


class Agilent34401ADriverTests(SimpleTestCase):
    """Verify Agilent serial communication and measurement handling."""

    @patch("drivers.a34401a_reader.time.sleep")
    @patch("drivers.a34401a_reader.list_ports.comports")
    @patch("serial.Serial")
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

    @patch("drivers.a34401a_reader.time.sleep")
    @patch("drivers.a34401a_reader.list_ports.comports")
    @patch("serial.Serial")
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
                b"SYSTem:REMote\n",
                b"*CLS\n",
                b"CONF:VOLT:DC\n",
                b"VOLT:DC:RANG:AUTO ON\n",
                b"*IDN?\n",
                b"SYSTem:LOCal\n",
            ],
        )
        connection.close.assert_called_once()

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
        driver.transport = MagicMock()
        driver.transport.get_data.return_value = "1.2345"

        result = driver.measure_dc_voltage()

        driver.transport.get_data.assert_called_once_with()
        self.assertEqual(
            result,
            MeasurementResult(parameter="Voltage DC", value=1.2345, unit="V"),
        )

    def test_measurement_rejects_invalid_response(self):
        """A malformed serial response becomes a measurement error."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")
        driver.transport = MagicMock()
        driver.transport.get_data.return_value = "invalid"

        with self.assertRaises(MeasurementError):
            driver.measure_dc_voltage()

    @patch("drivers.agilent_34401a.time.sleep")
    def test_prepare_dcv_uses_proven_serial_sequence(self, sleep):
        """DCV setup follows the timing proven by the original reader."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")
        driver.serial_connection = MagicMock()

        driver._prepare_dc_voltage()

        driver.serial_connection.reset_input_buffer.assert_called_once_with()
        self.assertEqual(
            [call.args[0] for call in driver.serial_connection.write.call_args_list],
            [
                b"SYSTem:REMote\n",
                b"*CLS\n",
                b"CONF:VOLT:DC\n",
                b"VOLT:DC:RANG:AUTO ON\n",
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
            [0.5, 0.1, 0.1, 0.5],
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
            [0.5, 0.1, 0.1, 0.5, 0.5],
        )
        self.assertEqual(first.value, 1.0)
        self.assertEqual(second.value, 2.0)

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
