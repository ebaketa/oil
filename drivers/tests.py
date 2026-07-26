"""Unit tests for OIL instrument drivers without physical hardware."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .agilent_34401a import Agilent34401ADriver
from .base import MeasurementResult
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .keysight_34461a import Keysight34461ADriver


class Agilent34401ADriverTests(SimpleTestCase):
    """Verify Agilent serial communication and measurement handling."""

    @patch("drivers.agilent_34401a.time.sleep")
    @patch("serial.Serial")
    def test_connect_configures_instrument(self, serial_factory, _sleep):
        """Connecting opens the configured port and sends SCPI setup commands."""
        connection = MagicMock(is_open=True)
        serial_factory.return_value = connection
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        driver.connect()

        self.assertTrue(driver.connected)
        serial_factory.assert_called_once()
        commands = [call.args[0] for call in connection.write.call_args_list]
        self.assertEqual(
            commands,
            [
                b"SYST:REM\n",
                b"DISP OFF\n",
                b"*CLS\n",
                b"CONF:VOLT:DC 10\n",
                b"VOLT:DC:NPLC 100\n",
            ],
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

        with patch.object(driver, "query", return_value="1.2345"):
            result = driver.measure_dc_voltage()

        self.assertEqual(
            result,
            MeasurementResult(parameter="Voltage DC", value=1.2345, unit="V"),
        )

    def test_measurement_rejects_invalid_response(self):
        """A malformed serial response becomes a measurement error."""
        driver = Agilent34401ADriver(port="/dev/ttyUSB0")

        with patch.object(driver, "query", return_value="invalid"):
            with self.assertRaises(MeasurementError):
                driver.measure_dc_voltage()


class Keysight34461ADriverTests(SimpleTestCase):
    """Verify Keysight USBTMC communication and measurement handling."""

    @patch("drivers.keysight_34461a.time.sleep")
    def test_connect_configures_instrument(self, _sleep):
        """Connecting opens USBTMC and sends SCPI setup commands."""
        device = MagicMock(closed=False)
        open_device = MagicMock(return_value=device)
        driver = Keysight34461ADriver(
            "/dev/usbtmc2",
            open_device=open_device,
        )

        driver.connect()

        self.assertTrue(driver.connected)
        open_device.assert_called_once_with("/dev/usbtmc2", "rb+", buffering=0)
        commands = [call.args[0] for call in device.write.call_args_list]
        self.assertEqual(
            commands,
            [
                b"*CLS\n",
                b"DISP:STAT OFF\n",
                b"CONF:VOLT:DC 10\n",
                b"VOLT:DC:NPLC 100\n",
            ],
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

    def test_measurement_returns_normalized_result(self):
        """A numeric USBTMC response becomes a measurement result."""
        driver = Keysight34461ADriver()

        with patch.object(driver, "query", return_value="-0.015"):
            result = driver.measure_dc_voltage()

        self.assertEqual(
            result,
            MeasurementResult(parameter="Voltage DC", value=-0.015, unit="V"),
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
