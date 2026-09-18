"""Tests for the Baketa BTDL-BMx280 driver."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from .base import MeasurementResult
from .btdl_bmx280 import BTDLBMx280Driver
from .exceptions import MeasurementError
from .factory import create_driver
from .transports import MockTransport


class BTDLBMx280DriverTests(SimpleTestCase):
    def test_factory_and_capabilities(self):
        driver = create_driver(
            SimpleNamespace(
                driver="btdl_bmx280",
                address="/dev/ttyACM2",
            ),
        )

        self.assertIsInstance(driver, BTDLBMx280Driver)
        self.assertEqual(driver.port, "/dev/ttyACM2")
        self.assertEqual(
            tuple(driver.capabilities()),
            (
                "environment", "temperatures", "temperature_1", "pressure_1",
                "humidity_1", "temperature_2", "pressure_2", "humidity_2",
            ),
        )

    def test_measures_environmental_quantities_by_fixed_channel(self):
        transport = MockTransport(
            {
                "MEAS:TEMP? 1": "23.45",
                "MEAS:PRES? 1": "1001.2345",
                "MEAS:HUM? 2": "48.75",
            },
        )
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver:
            temperature = driver.measure_temperature_1()
            pressure = driver.measure_pressure_1()
            humidity = driver.measure_humidity_2()

        self.assertEqual(
            temperature,
            MeasurementResult("Temperature", 23.45, "°C"),
        )
        self.assertEqual(
            pressure,
            MeasurementResult("Pressure", 1001.2345, "hPa"),
        )
        self.assertEqual(
            humidity,
            MeasurementResult("Humidity", 48.75, "%RH"),
        )

    def test_measures_both_channel_temperatures_in_one_query(self):
        transport = MockTransport({"MEAS:TEMP?": "23.45,24.10"})
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver:
            results = driver.measure_temperatures()

        self.assertEqual(
            results,
            (
                MeasurementResult("Temperature channel 1", 23.45, "°C"),
                MeasurementResult("Temperature channel 2", 24.1, "°C"),
            ),
        )

    def test_humidity_on_bmp280_reports_firmware_error(self):
        transport = MockTransport(
            {
                "MEAS:HUM? 1": "9.9E37",
                "SYST:ERR:NEXT?": '207,"Unknown error"',
            },
        )
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver, self.assertRaisesMessage(
            MeasurementError,
            '207,"Unknown error"',
        ):
            driver.measure_humidity_1()

    def test_reads_sensor_inventory(self):
        transport = MockTransport(
            {
                "SYST:SENS:COUNT?": "2",
                "SYST:SENS:ADDR? 1": '"0x76"',
                "SYST:SENS:TYPE? 1": "BMP280",
                "SYST:SENS:TYPE? 2": "BME280",
            },
        )
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver:
            self.assertEqual(driver.sensor_count(), 2)
            self.assertEqual(driver.sensor_address(1), "0x76")
            self.assertEqual(driver.sensor_type(1), "BMP280")
            self.assertEqual(driver.sensor_type(2), "BME280")

    def test_inventory_exposes_only_supported_quantities(self):
        transport = MockTransport(
            {
                "SYST:SENS:TYPE? 1": "BMP280",
                "SYST:SENS:TYPE? 2": "BME280",
            },
        )
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver:
            sensors = driver.sensor_inventory()

        self.assertEqual(
            sensors,
            (
                {
                    "channel": 1,
                    "address": "0x76",
                    "type": "BMP280",
                    "quantities": ("temperature", "pressure"),
                },
                {
                    "channel": 2,
                    "address": "0x77",
                    "type": "BME280",
                    "quantities": ("temperature", "pressure", "humidity"),
                },
            ),
        )

    def test_measures_selected_environmental_values(self):
        transport = MockTransport(
            {
                "READ?": "22.50,9.9E37,1001.25,1.2,23.10,48.25,1000.50,1.3",
            },
        )
        driver = BTDLBMx280Driver("/dev/ttyACM2", transport=transport)

        with driver:
            results = driver.measure_environment(
                ["temperature_1", "humidity_2"],
            )

        self.assertEqual(
            results,
            (
                MeasurementResult("Temperature channel 1", 22.5, "°C"),
                MeasurementResult("Humidity channel 2", 48.25, "%RH"),
            ),
        )
