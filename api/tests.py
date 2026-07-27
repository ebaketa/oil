"""Tests for the session-authenticated OIL JSON API."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from drivers.exceptions import CommunicationError
from instruments.models import Instrument
from measurements.models import Measurement


class ApiTests(TestCase):
    """Verify API authentication, serialization, validation, and execution."""

    @classmethod
    def setUpTestData(cls):
        """Create an API user, instrument, and representative reading."""
        cls.user = get_user_model().objects.create_user(
            username="api-user",
            password="test-password",
        )
        cls.instrument = Instrument.objects.create(
            name="API DMM",
            manufacturer="Keysight",
            model_name="34461A",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
            status=Instrument.Status.REACHABLE,
        )
        cls.measurement = Measurement.objects.create(
            instrument=cls.instrument,
            parameter="Voltage DC",
            value=1.234,
            unit="V",
            notes="API fixture",
        )

    def setUp(self):
        """Authenticate the standard API client."""
        self.client.force_login(self.user)

    def test_anonymous_requests_return_json_401(self):
        """API authentication failures never redirect to an HTML login."""
        client = Client()

        for route_name, args in (
            ("api_instrument_list", ()),
            ("api_instrument_detail", (self.instrument.pk,)),
            ("api_measurement_list", ()),
            ("api_measurement_single", ()),
        ):
            with self.subTest(route_name=route_name):
                response = client.get(reverse(route_name, args=args))
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.json(),
                    {"error": "Authentication is required."},
                )

    def test_instrument_list_returns_inventory_json(self):
        """The inventory endpoint returns stable public instrument fields."""
        response = self.client.get(reverse("api_instrument_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        instrument = response.json()["results"][0]
        self.assertEqual(instrument["id"], self.instrument.pk)
        self.assertEqual(instrument["name"], "API DMM")
        self.assertEqual(instrument["model"], "34461A")
        self.assertEqual(instrument["driver"], "keysight_34461a")
        self.assertEqual(instrument["status"], "reachable")
        self.assertFalse(instrument["online"])

    def test_instrument_detail_includes_capabilities(self):
        """Instrument details expose only capabilities implemented by driver."""
        response = self.client.get(
            reverse("api_instrument_detail", args=[self.instrument.pk]),
        )

        self.assertEqual(response.status_code, 200)
        capabilities = response.json()["capabilities"]
        self.assertEqual(
            tuple(capabilities),
            ("dc_voltage", "ac_voltage", "resistance"),
        )
        self.assertEqual(capabilities["dc_voltage"]["unit"], "V")
        self.assertTrue(capabilities["dc_voltage"]["autorange"])

    def test_missing_instrument_returns_json_404(self):
        """An unknown inventory identifier returns a structured error."""
        response = self.client.get(
            reverse("api_instrument_detail", args=[999999]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json(),
            {"error": "Instrument was not found."},
        )

    def test_measurement_list_is_paginated(self):
        """Stored readings are returned with bounded pagination metadata."""
        response = self.client.get(
            reverse("api_measurement_list"),
            {"limit": 10, "offset": 0},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["limit"], 10)
        self.assertEqual(payload["offset"], 0)
        self.assertEqual(payload["results"][0]["value"], 1.234)
        self.assertEqual(payload["results"][0]["unit"], "V")

    def test_measurement_list_rejects_invalid_pagination(self):
        """Unbounded or malformed pagination is rejected."""
        response = self.client.get(
            reverse("api_measurement_list"),
            {"limit": 101},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("between 1 and 100", response.json()["error"])

    @patch("api.views.perform_measurement")
    def test_single_measurement_uses_shared_service(self, perform):
        """A valid JSON request delegates to the existing measurement service."""
        perform.return_value = self.measurement

        response = self.client.post(
            reverse("api_measurement_single"),
            data=json.dumps(
                {
                    "instrument_id": self.instrument.pk,
                    "function": "dc_voltage",
                    "notes": "API request",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], self.measurement.pk)
        self.assertEqual(response.json()["parameter"], "Voltage DC")
        perform.assert_called_once_with(
            self.instrument,
            "dc_voltage",
            notes="API request",
        )

    def test_single_measurement_rejects_invalid_json(self):
        """Malformed JSON does not reach hardware."""
        response = self.client.post(
            reverse("api_measurement_single"),
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid JSON", response.json()["error"])

    @patch("api.views.perform_measurement")
    def test_single_measurement_returns_validation_errors(self, perform):
        """Unknown instruments and functions are rejected before execution."""
        response = self.client.post(
            reverse("api_measurement_single"),
            data=json.dumps(
                {
                    "instrument_id": self.instrument.pk,
                    "function": "temperature",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(
            "not one of the available choices",
            response.json()["errors"]["measurement_type"][0]["message"],
        )
        perform.assert_not_called()

    @patch("api.views.perform_measurement")
    def test_single_measurement_returns_driver_error(self, perform):
        """Communication failures use a JSON gateway-error response."""
        perform.side_effect = CommunicationError("Device timed out.")

        response = self.client.post(
            reverse("api_measurement_single"),
            data=json.dumps(
                {
                    "instrument_id": self.instrument.pk,
                    "function": "dc_voltage",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"error": "Device timed out."})

    def test_single_measurement_requires_csrf_token(self):
        """Session-authenticated API mutations retain Django CSRF protection."""
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        response = client.post(
            reverse("api_measurement_single"),
            data=json.dumps(
                {
                    "instrument_id": self.instrument.pk,
                    "function": "dc_voltage",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_unsupported_method_returns_json_405(self):
        """Method errors include a JSON body and Allow header."""
        response = self.client.post(
            reverse("api_instrument_list"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "GET")
        self.assertIn("not allowed", response.json()["error"])
