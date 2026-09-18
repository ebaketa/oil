"""Tests for the Baketa BTDL-DS18B20 driver."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from .base import MeasurementResult
from .btdl_ds18b20 import BTDLDS18B20Driver
from .exceptions import MeasurementError
from .factory import create_driver
from .transports import InstrumentTransport, MockTransport


class BTDLDS18B20DriverTests(SimpleTestCase):
    def test_factory_and_capabilities(self):
        driver = create_driver(
            SimpleNamespace(
                driver="btdl_ds18b20",
                address="/dev/ttyACM1",
            ),
        )

        self.assertIsInstance(driver, BTDLDS18B20Driver)
        self.assertEqual(driver.port, "/dev/ttyACM1")
        self.assertEqual(
            tuple(driver.capabilities()),
            ("temperatures", "temperature_ds1820", "temperature_ds18b20"),
        )

    def test_measures_each_sensor_family_separately(self):
        transport = MockTransport(
            {
                "MEAS:TEMP? DS1820": "21.3",
                "MEAS:TEMP? DS18B20": "21.6875",
            },
        )
        driver = BTDLDS18B20Driver("/dev/ttyACM1", transport=transport)

        with driver:
            ds1820 = driver.measure_temperature_ds1820()
            ds18b20 = driver.measure_temperature_ds18b20()

        self.assertEqual(
            ds1820,
            MeasurementResult(
                parameter="Temperature DS1820/DS18S20",
                value=21.5,
                unit="°C",
            ),
        )
        self.assertEqual(
            ds18b20,
            MeasurementResult(
                parameter="Temperature DS18B20",
                value=21.7,
                unit="°C",
            ),
        )

    def test_measures_both_temperatures_in_one_query(self):
        transport = MockTransport({"MEAS:TEMP?": "21.3,21.6875"})
        driver = BTDLDS18B20Driver("/dev/ttyACM1", transport=transport)

        with driver:
            results = driver.measure_temperatures()

        self.assertEqual(
            results,
            (
                MeasurementResult("Temperature DS1820/DS18S20", 21.5, "°C"),
                MeasurementResult("Temperature DS18B20", 21.7, "°C"),
            ),
        )

    def test_missing_selected_sensor_reports_firmware_error(self):
        transport = MockTransport(
            {
                "MEAS:TEMP? DS18B20": "9.9E37",
                "SYST:ERR:NEXT?": '203,"Selected sensor not found"',
            },
        )
        driver = BTDLDS18B20Driver("/dev/ttyACM1", transport=transport)

        with driver, self.assertRaisesMessage(
            MeasurementError,
            '203,"Selected sensor not found"',
        ):
            driver.measure_temperature_ds18b20()

    def test_sensor_inventory_queries(self):
        transport = MockTransport(
            {
                "SYST:SENS:COUNT?": "2",
                "SYST:SENS:ADDR? 2": '"28AABBCCDDEEFF01"',
            },
        )
        driver = BTDLDS18B20Driver("/dev/ttyACM1", transport=transport)

        with driver:
            self.assertEqual(driver.sensor_count(), 2)
            self.assertEqual(driver.sensor_address(2), "28AABBCCDDEEFF01")

    def test_sets_and_verifies_ds18b20_resolution(self):
        transport = MagicMock(spec=InstrumentTransport)
        transport.is_open = True
        transport.query.side_effect = ["1", '0,"No error"', "12"]
        driver = BTDLDS18B20Driver("/dev/ttyACM1", transport=transport)

        self.assertEqual(driver.set_ds18b20_resolution(12), 12)
        transport.write.assert_called_once_with("CONF:TEMP:DS18B20 12")
        self.assertEqual(
            [call.args[0] for call in transport.query.call_args_list],
            [
                "*OPC?",
                "SYST:ERR?",
                "CONF:TEMP:DS18B20?",
            ],
        )

    def test_rejects_invalid_ds18b20_resolution_locally(self):
        driver = BTDLDS18B20Driver("/dev/ttyACM1")

        with self.assertRaisesMessage(ValueError, "9, 10, 11, or 12"):
            driver.set_ds18b20_resolution(8)
