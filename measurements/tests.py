"""Tests for measurement-domain exports."""

import csv
import io
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from instruments.models import Instrument

from .exports import CSV_COLUMNS
from .models import Measurement


class MeasurementCsvExportTests(TestCase):
    """Verify authenticated, safe, streaming CSV downloads."""

    @classmethod
    def setUpTestData(cls):
        """Create representative export data."""
        cls.user = get_user_model().objects.create_user(
            username="csv-user",
            password="test-password",
        )
        cls.instrument = Instrument.objects.create(
            name="Export DMM",
            manufacturer="Keysight",
            model_name="34461A",
            serial_number="MY123",
            driver=Instrument.Driver.KEYSIGHT_34461A,
            address="/dev/usbtmc0",
        )
        cls.measurement = Measurement.objects.create(
            instrument=cls.instrument,
            parameter="Voltage DC",
            value=-1.25,
            unit="V",
            notes="Reference, channel 1",
        )

    def setUp(self):
        """Authenticate the export client."""
        self.client.force_login(self.user)

    def export_rows(self):
        """Download and parse the streaming CSV response."""
        response = self.client.get(reverse("measurement_export_csv"))
        content = b"".join(response.streaming_content).decode("utf-8-sig")
        return response, list(csv.DictReader(io.StringIO(content)))

    def test_export_has_download_headers_and_stable_columns(self):
        """CSV downloads use a timestamped attachment and documented header."""
        response, rows = self.export_rows()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertRegex(
            response["Content-Disposition"],
            re.compile(
                r'^attachment; filename="oil-measurements-'
                r'\d{8}-\d{6}\.csv"$',
            ),
        )
        self.assertEqual(tuple(rows[0]), CSV_COLUMNS)

    def test_export_contains_normalized_measurement_and_instrument_data(self):
        """Each row includes identifiers, instrument metadata, and notes."""
        _response, rows = self.export_rows()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["measurement_id"], str(self.measurement.pk))
        self.assertEqual(row["instrument_id"], str(self.instrument.pk))
        self.assertEqual(row["instrument_name"], "Export DMM")
        self.assertEqual(row["manufacturer"], "Keysight")
        self.assertEqual(row["model"], "34461A")
        self.assertEqual(row["serial_number"], "MY123")
        self.assertEqual(row["parameter"], "Voltage DC")
        self.assertEqual(row["value"], "-1.25")
        self.assertEqual(row["unit"], "V")
        self.assertEqual(row["notes"], "Reference, channel 1")
        self.assertTrue(row["timestamp"])

    def test_user_text_is_protected_from_spreadsheet_formulas(self):
        """Potential formulas are exported as literal spreadsheet text."""
        self.instrument.name = "=HYPERLINK(\"https://example.invalid\")"
        self.instrument.save(update_fields=("name", "updated_at"))
        self.measurement.notes = "+SUM(1,1)"
        self.measurement.save(update_fields=("notes",))

        _response, rows = self.export_rows()

        self.assertTrue(rows[0]["instrument_name"].startswith("'="))
        self.assertTrue(rows[0]["notes"].startswith("'+"))
        self.assertEqual(rows[0]["value"], "-1.25")

    def test_anonymous_export_redirects_to_login(self):
        """CSV inventory data is unavailable without authentication."""
        self.client.logout()

        response = self.client.get(reverse("measurement_export_csv"))

        self.assertRedirects(
            response,
            (
                f"{reverse('login')}?next="
                f"{reverse('measurement_export_csv')}"
            ),
        )

    def test_export_rejects_post(self):
        """CSV export is a read-only endpoint."""
        response = self.client.post(reverse("measurement_export_csv"))

        self.assertEqual(response.status_code, 405)

    def test_measurement_page_links_to_export(self):
        """The Measurements page exposes the CSV download action."""
        response = self.client.get(reverse("measurement_list"))

        self.assertContains(response, reverse("measurement_export_csv"))
        self.assertContains(response, "Download CSV")

    def test_workflow_pages_export_their_visible_results(self):
        """Each measurement workflow exposes the shared table CSV exporter."""
        workflows = (
            ("measurement_create", "measurement-single-table"),
            ("measurement_continuous", "measurement-continuous-table"),
            ("measurement_loop", "measurement-loop-table"),
        )

        for url_name, table_id in workflows:
            with self.subTest(workflow=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Download CSV")
                self.assertContains(
                    response,
                    'main/js/measurement_csv.js',
                )
                self.assertContains(
                    response,
                    f'data-csv-target="{table_id}"',
                )
                self.assertContains(response, f'id="{table_id}"')
                content = response.content.decode()
                self.assertLess(
                    content.index("Download CSV"),
                    content.index("Back"),
                )
