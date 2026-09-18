from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Instrument
from tasks.models import AutomationTask, TaskInstrument, TaskReading, TaskSample

from .models import PanelLease


class DmmPanelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="panel-user")
        self.instrument = Instrument.objects.create(
            name="Panel Mock DMM",
            manufacturer="OIL",
            model_name="Mock DMM",
            driver=Instrument.Driver.MOCK,
            address="mock-dmm://panel",
        )
        self.client.force_login(self.user)

    def test_panel_lists_driver_capabilities(self):
        response = self.client.get(reverse("dmm_panel", args=[self.instrument.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.instrument.name)
        self.assertNotContains(response, "PRECISION DMM")
        self.assertContains(response, ">DCV</button>", html=False)
        self.assertContains(response, ">DCI</button>", html=False)
        self.assertContains(response, ">ACV</button>", html=False)
        self.assertContains(response, ">ACI</button>", html=False)
        self.assertContains(response, ">2W</button>", html=False)
        self.assertContains(response, ">4W</button>", html=False)
        self.assertContains(response, ">Freq</button>", html=False)
        self.assertContains(response, ">Cap</button>", html=False)
        self.assertContains(response, ">Dio</button>", html=False)
        self.assertContains(response, ">Cont</button>", html=False)
        self.assertContains(response, ">Temp</button>", html=False)
        self.assertContains(response, 'data-display-unit="VDC"')
        self.assertContains(response, 'data-display-unit="VAC"')
        self.assertContains(response, 'data-display-unit="ADC"')
        self.assertContains(response, 'data-display-unit="AAC"')
        self.assertContains(response, 'data-ranges="0.5,5,50,500"')
        self.assertContains(response, ">Auto Range</button>", html=False)
        self.assertContains(response, ">Range +</button>", html=False)
        self.assertContains(response, ">Range −</button>", html=False)
        self.assertContains(response, ">Resolution 4¾ · 50k</button>", html=False)

    def test_agilent_panel_reads_current_instrument_status(self):
        instrument = Instrument.objects.create(
            name="Bench Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        driver = MagicMock()
        driver.read_panel_status.return_value = {
            "function": "ac_voltage",
            "parameter": "Voltage AC",
            "unit": "V",
            "autorange": True,
            "range_value": 10.0,
            "value": 1.25,
        }

        with patch(
            "dmm_panel.views.ConnectionManager.persistent_session",
        ) as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.get(
                reverse("dmm_panel_status", args=[instrument.pk]),
                {"panel_token": "primary-panel-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["function"], "ac_voltage")
        self.assertEqual(response.json()["value"], 1.25)
        driver.read_panel_status.assert_called_once_with()

    def test_agilent_panel_exposes_actual_front_panel_functions(self):
        instrument = Instrument.objects.create(
            name="Bench Agilent functions",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )

        response = self.client.get(
            reverse("dmm_panel", args=[instrument.pk]),
        )

        self.assertEqual(response.status_code, 200)
        for label in (
            "DCV", "DCI", "ACV", "ACI", "Ω 2W", "Ω 4W",
            "Freq", "Period", "Cont )))", "Diode",
        ):
            self.assertContains(response, f">{label}</button>", html=False)
        self.assertNotContains(response, ">Cap</button>", html=False)
        self.assertNotContains(response, ">Temp</button>", html=False)

    def test_second_agilent_panel_receives_cached_read_only_status(self):
        instrument = Instrument.objects.create(
            name="Shared Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        driver = MagicMock()
        driver.read_panel_status.return_value = {
            "function": "dc_voltage",
            "parameter": "Voltage DC",
            "unit": "V",
            "autorange": True,
            "range_value": 10.0,
            "value": 1.25,
            "resolution": "6.5",
            "decimals": 5,
        }
        url = reverse("dmm_panel_status", args=[instrument.pk])

        with patch(
            "dmm_panel.views.ConnectionManager.persistent_session",
        ) as session:
            session.return_value.__enter__.return_value = driver
            owner_response = self.client.get(
                url,
                {"panel_token": "primary-panel-token"},
            )
            viewer_response = self.client.get(
                url,
                {"panel_token": "second-panel-token"},
            )

        self.assertIs(owner_response.json()["read_only"], False)
        self.assertIs(viewer_response.json()["read_only"], True)
        self.assertEqual(viewer_response.json()["value"], 1.25)
        driver.read_panel_status.assert_called_once_with()

    def test_agilent_panel_sets_measurement_resolution(self):
        instrument = Instrument.objects.create(
            name="Bench Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        driver = MagicMock()
        driver.set_resolution.return_value = 10.0
        PanelLease.objects.create(
            instrument=instrument,
            user=self.user,
            owner_token="primary-panel-token",
            last_seen=timezone.now(),
        )

        with patch("dmm_panel.views.ConnectionManager.session") as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.post(
                reverse("dmm_panel_resolution", args=[instrument.pk]),
                {
                    "function": "dc_voltage",
                    "resolution": "6.5",
                    "panel_token": "primary-panel-token",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"resolution": "6.5", "nplc": 10.0, "commands": []},
        )
        driver.set_resolution.assert_called_once_with("dc_voltage", "6.5")

    def test_agilent_panel_sets_exact_nplc(self):
        instrument = Instrument.objects.create(
            name="Bench Agilent NPLC",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        driver = MagicMock()
        driver.set_nplc.return_value = 20.0
        driver.drain_command_log.return_value = [
            "VOLT:DC:NPLC 20",
            "VOLT:DC:NPLC?",
        ]
        PanelLease.objects.create(
            instrument=instrument,
            user=self.user,
            owner_token="primary-panel-token",
            last_seen=timezone.now(),
        )

        with patch("dmm_panel.views.ConnectionManager.session") as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.post(
                reverse("dmm_panel_nplc", args=[instrument.pk]),
                {
                    "function": "dc_voltage",
                    "nplc": "20",
                    "panel_token": "primary-panel-token",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "nplc": 20.0,
                "commands": ["VOLT:DC:NPLC 20", "VOLT:DC:NPLC?"],
            },
        )
        driver.set_nplc.assert_called_once_with("dc_voltage", 20.0)

    def test_panel_measurement_error_does_not_escape_active_session(self):
        instrument = Instrument.objects.create(
            name="Remote Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        PanelLease.objects.create(
            instrument=instrument,
            user=self.user,
            owner_token="primary-panel-token",
            last_seen=timezone.now(),
        )
        driver = MagicMock()
        driver.measure_ac_voltage.side_effect = RuntimeError("ACV failed")

        with patch("dmm_panel.views.ConnectionManager.session") as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.post(
                reverse("dmm_panel_measure", args=[instrument.pk]),
                {
                    "function": "ac_voltage",
                    "range": "auto",
                    "panel_token": "primary-panel-token",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "ACV failed")
        session.return_value.__exit__.assert_called_once_with(None, None, None)

    def test_agilent_panel_clears_errors_when_owner_leaves(self):
        instrument = Instrument.objects.create(
            name="Leaving Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        PanelLease.objects.create(
            instrument=instrument,
            user=self.user,
            owner_token="primary-panel-token",
            last_seen=timezone.now(),
        )
        driver = MagicMock()
        driver.clear_error_queue.return_value = ('-113,"Undefined header"',)

        with patch(
            "dmm_panel.views.ConnectionManager.persistent_session",
        ) as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.post(
                reverse("dmm_panel_release", args=[instrument.pk]),
                {"panel_token": "primary-panel-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["cleared_errors"],
            ['-113,"Undefined header"'],
        )
        driver.clear_error_queue.assert_called_once_with()
        self.assertFalse(PanelLease.objects.filter(instrument=instrument).exists())

    def test_panel_cls_sends_clear_status_command(self):
        instrument = Instrument.objects.create(
            name="Clear Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        PanelLease.objects.create(
            instrument=instrument,
            user=self.user,
            owner_token="primary-panel-token",
            last_seen=timezone.now(),
        )
        driver = MagicMock()
        driver.drain_command_log.return_value = ["*CLS"]

        with patch(
            "dmm_panel.views.ConnectionManager.persistent_session",
        ) as session:
            session.return_value.__enter__.return_value = driver
            response = self.client.post(
                reverse("dmm_panel_clear", args=[instrument.pk]),
                {"panel_token": "primary-panel-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cleared": True, "commands": ["*CLS"]})
        driver.write.assert_called_once_with("*CLS")

    def test_fixed_range_is_validated_against_driver_capabilities(self):
        response = self.client.post(
            reverse("dmm_panel_measure", args=[self.instrument.pk]),
            {"function": "dc_voltage", "range": "5"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()["autorange"], False)
        self.assertEqual(response.json()["range_value"], 5.0)

    def test_unsupported_fixed_range_is_rejected(self):
        response = self.client.post(
            reverse("dmm_panel_measure", args=[self.instrument.pk]),
            {"function": "dc_voltage", "range": "1000"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Unsupported measurement range.")

    def test_mock_resolution_mode_changes_ranges_and_precision(self):
        response = self.client.post(
            reverse("dmm_panel_measure", args=[self.instrument.pk]),
            {
                "function": "dc_voltage",
                "range": "20",
                "count_mode": "200000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count_mode"], "200000")
        self.assertEqual(response.json()["decimals"], 4)
        self.assertEqual(response.json()["voltage_ranges"], [0.2, 2.0, 20.0, 200.0, 1000.0])

    def test_single_trigger_returns_normalized_reading(self):
        response = self.client.post(
            reverse("dmm_panel_measure", args=[self.instrument.pk]),
            {"function": "dc_voltage"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["parameter"], "Voltage DC")
        self.assertEqual(response.json()["unit"], "V")
        self.assertEqual(response.json()["decimals"], 4)
        self.assertIs(response.json()["autorange"], True)

    def test_active_task_blocks_front_panel_measurement(self):
        task = AutomationTask.objects.create(
            user=self.user,
            name="Busy DMM",
            status=AutomationTask.Status.RUNNING,
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.instrument,
            configuration={"function": "dc_voltage", "source": "external"},
        )

        response = self.client.post(
            reverse("dmm_panel_measure", args=[self.instrument.pk]),
            {"function": "dc_voltage"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("active task", response.json()["error"])

    def test_panel_list_marks_instrument_used_by_active_task(self):
        """Instrument panels distinguish task ownership from reachability."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Busy DMM",
            status=AutomationTask.Status.RUNNING,
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.instrument,
            configuration={"function": "dc_voltage", "source": "external"},
        )

        response = self.client.get(reverse("panel_list"))

        self.assertContains(response, '<div class="oil-header-page-title">Panels</div>', html=True)
        self.assertContains(response, "Active: 1 | Available: 0")
        self.assertContains(response, ">Back</a>", html=False)
        self.assertContains(response, f"In use · Task {task.pk}")

    def test_dashboard_links_to_panels_without_listing_instruments(self):
        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, reverse("panel_list"))
        self.assertEqual(response.context["panel_count"], 1)
        self.assertNotContains(response, "Open DMM Panel")

    def test_dashboard_counts_active_and_completed_tasks(self):
        AutomationTask.objects.create(
            user=self.user,
            name="Active",
            status=AutomationTask.Status.RUNNING,
        )
        AutomationTask.objects.create(
            user=self.user,
            name="Completed",
            status=AutomationTask.Status.COMPLETED,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.context["active_task_count"], 1)
        self.assertEqual(response.context["completed_task_count"], 1)

    def test_busy_panel_exposes_latest_task_reading(self):
        task = AutomationTask.objects.create(
            user=self.user,
            name="Live DMM",
            status=AutomationTask.Status.RUNNING,
        )
        assignment = TaskInstrument.objects.create(
            task=task,
            instrument=self.instrument,
            configuration={
                "function": "dc_voltage",
                "source": "virtual",
                "count_mode": "200000",
            },
        )
        sample = TaskSample.objects.create(
            task=task,
            index=125,
            voltage_setpoint=0,
            acquisition_time_seconds="0.100",
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Voltage DC",
            value="4.9999",
            unit="V",
        )

        panel_response = self.client.get(
            reverse("dmm_panel", args=[self.instrument.pk]),
        )
        live_response = self.client.get(
            reverse("dmm_panel_live", args=[self.instrument.pk]),
        )

        self.assertContains(
            panel_response,
            f'<div class="oil-header-page-title">{self.instrument.name}</div>',
            html=True,
        )
        self.assertContains(panel_response, task.name)
        self.assertContains(panel_response, f"Task {task.pk}")
        self.assertNotContains(panel_response, f"Task {task.pk} — {task.name}")
        self.assertEqual(live_response.status_code, 200)
        self.assertEqual(live_response.json()["sample_id"], 125)
        self.assertEqual(live_response.json()["value"], 4.9999)
        self.assertEqual(live_response.json()["unit"], "V")
        self.assertEqual(live_response.json()["decimals"], 6)
        self.assertEqual(live_response.json()["count_mode"], "200000")
        self.assertEqual(
            live_response.json()["voltage_ranges"],
            [0.2, 2.0, 20.0, 200.0, 1000.0],
        )
        self.assertIs(live_response.json()["autorange"], True)
        self.assertEqual(live_response.json()["minimum"], 4.9999)
        self.assertEqual(live_response.json()["maximum"], 4.9999)
        self.assertEqual(live_response.json()["average"], 4.9999)
        self.assertEqual(live_response.json()["recent_values"], [4.9999])

    def test_busy_agilent_panel_uses_task_measurement_resolution(self):
        instrument = Instrument.objects.create(
            name="Task Agilent",
            manufacturer="Agilent",
            model_name="34401A",
            driver=Instrument.Driver.AGILENT_34401A,
            address="/dev/ttyUSB0",
        )
        task = AutomationTask.objects.create(
            user=self.user,
            name="Precision task",
            status=AutomationTask.Status.RUNNING,
        )
        assignment = TaskInstrument.objects.create(
            task=task,
            instrument=instrument,
            configuration={
                "function": "dc_voltage",
                "source": "external",
                "resolution": "6.5",
            },
        )
        sample = TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=0,
            acquisition_time_seconds="0.100",
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Voltage DC",
            value="1.234567",
            unit="V",
        )

        response = self.client.get(
            reverse("dmm_panel_live", args=[instrument.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decimals"], 5)

    def test_non_measurement_instrument_has_no_panel(self):
        supply = Instrument.objects.create(
            name="PSU",
            manufacturer="OIL",
            model_name="Mock PSU",
            driver=Instrument.Driver.MOCK_DC_POWER_SUPPLY,
            address="mock-psu://panel",
        )

        response = self.client.get(reverse("dmm_panel", args=[supply.pk]))

        self.assertEqual(response.status_code, 404)
