"""Task integration tests for the BTDL-NTC instrument."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import Instrument

from .models import TaskInstrument


class BTDLNTCTaskTests(TestCase):
    """Verify BTDL-NTC task defaults and chart configuration."""

    @patch("tasks.views.TaskRunner.start")
    def test_temperature_can_use_secondary_chart_axis(self, start):
        user = get_user_model().objects.create_user(
            username="btdl-task-user",
            password="test-password",
        )
        sensor = Instrument.objects.create(
            name="BTDL temperature",
            manufacturer="Baketa",
            model_name="BTDL-NTC",
            driver=Instrument.Driver.BTDL_NTC,
            address="/dev/serial/by-id/btdl-test",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "BTDL secondary axis",
                "measurement_mode": "single",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": sensor.pk,
                            "configuration": {
                                "function": "temperature",
                                "source": "external",
                                "chart_axis": "secondary",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        assignment = TaskInstrument.objects.get(instrument=sensor)
        self.assertEqual(assignment.configuration["chart_axis"], "secondary")
        self.assertEqual(response.json()["result_columns"][0]["axis"], "secondary")
        start.assert_called_once()

    @patch("tasks.views.TaskRunner.start")
    def test_ds18b20_resolution_is_saved_with_bounded_display_precision(
        self,
        start,
    ):
        user = get_user_model().objects.create_user(
            username="ds18b20-task-user",
            password="test-password",
        )
        sensor = Instrument.objects.create(
            name="BTDL DS18B20",
            manufacturer="Baketa",
            model_name="BTDL-DS18B20",
            driver=Instrument.Driver.BTDL_DS18B20,
            address="/dev/serial/by-id/btdl-ds18b20-test",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "DS18B20 precision",
                "measurement_mode": "single",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": sensor.pk,
                            "configuration": {
                                "function": "temperature_ds18b20",
                                "source": "external",
                                "chart_axis": "secondary",
                                "ds18b20_resolution_bits": "11",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        assignment = TaskInstrument.objects.get(instrument=sensor)
        self.assertEqual(
            assignment.configuration["ds18b20_resolution_bits"],
            11,
        )
        self.assertEqual(response.json()["result_columns"][0]["decimals"], 1)
        start.assert_called_once()

    @patch("tasks.views.TaskRunner.start")
    def test_combined_temperature_functions_create_two_columns_each(self, start):
        user = get_user_model().objects.create_user(
            username="combined-temperature-user",
            password="test-password",
        )
        ds_sensor = Instrument.objects.create(
            name="Dual DS temperatures",
            manufacturer="Baketa",
            model_name="BTDL-DS18B20",
            driver=Instrument.Driver.BTDL_DS18B20,
            address="/dev/serial/by-id/dual-ds-test",
        )
        bmx_sensor = Instrument.objects.create(
            name="Dual BMx temperatures",
            manufacturer="Baketa",
            model_name="BTDL-BMx280",
            driver=Instrument.Driver.BTDL_BMX280,
            address="/dev/serial/by-id/dual-bmx-test",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Four temperatures",
                "measurement_mode": "single",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": ds_sensor.pk,
                            "configuration": {
                                "function": "temperatures",
                                "source": "external",
                                "chart_axis": "primary",
                                "ds18b20_resolution_bits": "12",
                            },
                        },
                        {
                            "instrument_id": bmx_sensor.pk,
                            "configuration": {
                                "function": "temperatures",
                                "source": "external",
                                "chart_axis": "secondary",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        columns = response.json()["result_columns"]
        self.assertEqual(len(columns), 4)
        self.assertEqual(
            [column["parameter"] for column in columns],
            [
                "Temperature DS1820/DS18S20",
                "Temperature DS18B20",
                "Temperature channel 1",
                "Temperature channel 2",
            ],
        )
        self.assertEqual([column["decimals"] for column in columns], [1, 1, 2, 2])
        start.assert_called_once()

    @patch("tasks.views.TaskRunner.start")
    def test_bmx280_can_log_multiple_selected_values(self, start):
        user = get_user_model().objects.create_user(
            username="bmx-values-user",
            password="test-password",
        )
        sensor = Instrument.objects.create(
            name="Room environment",
            manufacturer="Baketa",
            model_name="BTDL-BMx280",
            driver=Instrument.Driver.BTDL_BMX280,
            address="/dev/serial/by-id/bmx-values-test",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Environment",
                "measurement_mode": "single",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": sensor.pk,
                            "configuration": {
                                "function": "environment",
                                "measurements": [
                                    "temperature_1",
                                    "pressure_1",
                                    "humidity_2",
                                ],
                                "sensor_types": {
                                    "1": "BMP280",
                                    "2": "BME280",
                                },
                                "measurement_axes": {
                                    "temperature_1": "primary",
                                    "pressure_1": "axis3",
                                    "humidity_2": "secondary",
                                },
                                "source": "external",
                                "chart_axis": "primary",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        assignment = TaskInstrument.objects.get(instrument=sensor)
        self.assertEqual(
            assignment.configuration["measurements"],
            ["temperature_1", "pressure_1", "humidity_2"],
        )
        self.assertEqual(
            [
                column["parameter"]
                for column in response.json()["result_columns"]
            ],
            [
                "Temperature channel 1",
                "Pressure channel 1",
                "Humidity channel 2",
            ],
        )
        self.assertEqual(
            [column["label"] for column in response.json()["result_columns"]],
            [
                "Room environment BMP280 — Temperature",
                "Room environment BMP280 — Pressure",
                "Room environment BME280 — Humidity",
            ],
        )
        self.assertEqual(
            [column["axis"] for column in response.json()["result_columns"]],
            ["primary", "axis3", "secondary"],
        )
        start.assert_called_once()
