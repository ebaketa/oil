"""Unit tests for reusable instrument transports."""

import errno
from unittest.mock import MagicMock, patch

import serial
from django.test import SimpleTestCase

from .exceptions import CommunicationError
from .transports import MockTransport, SerialTransport, USBTMCTransport


class SerialTransportTests(SimpleTestCase):
    """Verify serial framing, message transfer, and cleanup."""

    def create_transport(self):
        """Return a transport backed by a simulated open serial port."""
        connection = MagicMock(is_open=True, in_waiting=1)
        connection.readline.return_value = b"1.234\r\n"
        serial_factory = MagicMock(return_value=connection)
        transport = SerialTransport(
            "/dev/ttyUSB9",
            serial_factory=serial_factory,
        )
        return transport, connection, serial_factory

    def test_open_uses_8n2_framing(self):
        """Serial instruments open with the proven Agilent framing."""
        transport, connection, serial_factory = self.create_transport()

        transport.open()

        serial_factory.assert_called_once_with(
            port="/dev/ttyUSB9",
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
            timeout=1,
        )
        self.assertIs(transport.connection, connection)
        self.assertTrue(transport.is_open)

    def test_query_terminates_command_and_decodes_response(self):
        """A query sends one newline and returns stripped text."""
        transport, connection, _serial_factory = self.create_transport()
        transport.connection = connection

        response = transport.query("READ?")

        connection.write.assert_called_once_with(b"READ?\n")
        self.assertEqual(response, "1.234")

    def test_reset_and_close_delegate_to_serial_connection(self):
        """Input cleanup and close remain available to model drivers."""
        transport, connection, _serial_factory = self.create_transport()
        transport.connection = connection

        transport.reset_input_buffer()
        transport.close()

        connection.reset_input_buffer.assert_called_once_with()
        connection.close.assert_called_once_with()
        self.assertFalse(transport.is_open)

    def test_read_timeout_is_a_transport_error(self):
        """A delayed serial response fails after the requested deadline."""
        connection = MagicMock(is_open=True, in_waiting=0)
        transport = SerialTransport("/dev/ttyUSB9")
        transport.connection = connection

        with self.assertRaisesMessage(
            CommunicationError,
            "serial response timed out",
        ):
            transport.read(timeout=0)

    def test_raw_response_does_not_wait_for_a_newline(self):
        """Unterminated device responses finish after a short quiet period."""
        connection = MagicMock(is_open=True)
        type(connection).in_waiting = property(
            lambda _connection: 5 if not connection.read.called else 0,
        )
        connection.read.return_value = b"12.34"
        transport = SerialTransport(
            "/dev/ttyUSB9",
            response_termination=None,
        )
        transport.connection = connection

        response = transport.read(timeout=1)

        connection.read.assert_called_once_with(5)
        self.assertEqual(response, "12.34")


class USBTMCTransportTests(SimpleTestCase):
    """Verify Linux USBTMC open, transfer, and cleanup behavior."""

    def test_lifecycle_and_query_use_unbuffered_binary_device(self):
        """USBTMC opens once and exchanges newline-delimited SCPI."""
        device = MagicMock(closed=False)
        device.read.return_value = b"KEYSIGHT,34461A\n"
        open_device = MagicMock(return_value=device)
        transport = USBTMCTransport(
            "/dev/usbtmc3",
            open_device=open_device,
        )

        transport.open()
        response = transport.query("*IDN?")
        transport.close()

        open_device.assert_called_once_with(
            "/dev/usbtmc3",
            "rb+",
            buffering=0,
        )
        device.write.assert_called_once_with(b"*IDN?\n")
        device.read.assert_called_once_with(400)
        self.assertEqual(response, "KEYSIGHT,34461A")
        device.close.assert_called_once_with()
        self.assertFalse(transport.is_open)

    def test_empty_response_is_a_transport_error(self):
        """An empty device read is rejected before reaching the driver."""
        device = MagicMock(closed=False)
        device.read.return_value = b""
        transport = USBTMCTransport("/dev/usbtmc3")
        transport.device = device

        with self.assertRaisesMessage(
            CommunicationError,
            "empty response",
        ):
            transport.read()

    @patch("drivers.transports.usbtmc.fcntl.ioctl")
    def test_read_timeout_is_a_transport_error(self, ioctl):
        """USBTMC stops waiting when an instrument does not respond."""
        device = MagicMock(closed=False)
        device.fileno.return_value = 12
        device.read.side_effect = OSError(errno.ETIMEDOUT, "timed out")
        transport = USBTMCTransport("/dev/usbtmc3")
        transport.device = device

        with self.assertRaisesMessage(
            CommunicationError,
            "USBTMC response timed out",
        ):
            transport.read(timeout=0.01)

        ioctl.assert_called_once()
        device.read.assert_called_once_with(400)


class MockTransportTests(SimpleTestCase):
    """Verify deterministic in-memory command exchange."""

    def test_query_records_command_and_returns_configured_response(self):
        """Mock queries follow the same open/query/close contract."""
        transport = MockTransport({"*IDN?": "OIL,MOCK"})

        transport.open()
        response = transport.query("*IDN?")
        transport.close()

        self.assertEqual(response, "OIL,MOCK")
        self.assertEqual(transport.command_history, ["*IDN?"])
        self.assertFalse(transport.is_open)

    def test_missing_response_is_a_transport_error(self):
        """Unconfigured mock commands cannot silently return empty data."""
        transport = MockTransport()
        transport.open()

        with self.assertRaisesMessage(
            CommunicationError,
            "no response",
        ):
            transport.query("UNKNOWN?")
