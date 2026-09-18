"""Tests for the Baketa BTDL-NTC driver."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from .base import MeasurementResult
from .btdl_ntc import BTDLNTCDriver
from .exceptions import CommunicationError, ConnectionError, MeasurementError
from .factory import create_driver
from .transports import InstrumentTransport, MockTransport


class BTDLNTCDriverTests(SimpleTestCase):
    """Verify BTDL-NTC communication without physical hardware."""

    def test_factory_creates_driver_from_inventory(self):
        driver = create_driver(
            SimpleNamespace(driver="btdl_ntc", address="/dev/ttyACM0"),
        )

        self.assertIsInstance(driver, BTDLNTCDriver)
        self.assertEqual(driver.port, "/dev/ttyACM0")

    def test_identifies_and_measures_temperature(self):
        transport = MockTransport(
            {
                "*IDN?": "Baketa,BTDL-NTC,003,1.2.0",
                "MEAS:TEMP?": "25.0",
            },
        )
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        with driver:
            identity = driver.identify()
            result = driver.measure_temperature()

        self.assertEqual(identity, "Baketa,BTDL-NTC,003,1.2.0")
        self.assertEqual(
            result,
            MeasurementResult(parameter="Temperature", value=25.0, unit="°C"),
        )
        self.assertEqual(transport.command_history, ["*IDN?", "MEAS:TEMP?"])

    def test_failed_sensor_reading_reports_scpi_error(self):
        transport = MockTransport(
            {
                "MEAS:TEMP?": "9.9E37",
                "SYST:ERR:NEXT?": '202,"Sensor read failed"',
            },
        )
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        with driver, self.assertRaisesMessage(
            MeasurementError,
            '202,"Sensor read failed"',
        ):
            driver.measure_temperature()

        self.assertEqual(
            transport.command_history,
            ["MEAS:TEMP?", "SYST:ERR:NEXT?"],
        )

    def test_reads_error_queue_count(self):
        transport = MockTransport({"SYST:ERR:COUNT?": "2"})
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        with driver:
            count = driver.error_count()

        self.assertEqual(count, 2)
        self.assertEqual(transport.command_history, ["SYST:ERR:COUNT?"])

    def test_reset_and_clear_status_are_verified(self):
        transport = MagicMock(spec=InstrumentTransport)
        transport.is_open = True
        transport.query.side_effect = [
            "1", '0,"No error"', "1", '0,"No error"',
        ]
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        driver.reset_device()
        driver.clear_status()

        self.assertEqual(
            [call.args[0] for call in transport.method_calls],
            [
                "*RST", "*OPC?", "SYST:ERR?", "*CLS", "*OPC?", "SYST:ERR?",
            ],
        )

    def test_non_numeric_temperature_is_rejected(self):
        transport = MockTransport({"MEAS:TEMP?": "not-a-number"})
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        with driver, self.assertRaises(MeasurementError):
            driver.measure_temperature()

    @patch("drivers.btdl_ntc.time.sleep")
    @patch("drivers.transports.serial.serial.Serial")
    def test_serial_connection_uses_19200_baud_8n1(
        self,
        serial_factory,
        sleep,
    ):
        serial_factory.return_value = MagicMock(is_open=True)
        driver = BTDLNTCDriver("/dev/ttyACM0")

        driver.connect()

        serial_factory.assert_called_once()
        options = serial_factory.call_args.kwargs
        self.assertEqual(options["baudrate"], 19200)
        self.assertEqual(options["bytesize"], 8)
        self.assertEqual(options["parity"], "N")
        self.assertEqual(options["stopbits"], 1)
        sleep.assert_called_once_with(3.0)
        serial_factory.return_value.reset_input_buffer.assert_called_once_with()
        driver.disconnect()

    def test_operations_require_an_open_connection(self):
        driver = BTDLNTCDriver("/dev/ttyACM0")

        with self.assertRaises(CommunicationError):
            driver.identify()

    def test_transport_open_failure_is_connection_error(self):
        transport = MagicMock()
        transport.open.side_effect = CommunicationError("busy")
        driver = BTDLNTCDriver("/dev/ttyACM0", transport=transport)

        with self.assertRaises(ConnectionError):
            driver.connect()
