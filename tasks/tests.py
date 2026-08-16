"""Tests for the Task application."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Instrument
from drivers.base import MeasurementResult
from drivers.exceptions import MeasurementError

from .bench import VirtualMockBench
from .models import (
    AutomationTask,
    TaskInstrument,
    TaskReading,
    TaskSample,
)
from .runner import measurement_sequence, run_automation_task, voltage_sequence


class VirtualMockBenchTests(TestCase):
    """Verify 50,000-count voltage autoranging and resolution."""

    def create_bench(self):
        return VirtualMockBench(
            seed=1,
            temperature_min=Decimal("20"),
            temperature_max=Decimal("21"),
            temperature_resolution=Decimal("0.1"),
        )

    def test_voltage_ranges_select_expected_resolution(self):
        self.assertEqual(
            [
                self.create_bench().voltage_resolution(value)
                for value in ("0.499", "4.99", "49.9", "499")
            ],
            [
                Decimal("0.00001"),
                Decimal("0.0001"),
                Decimal("0.001"),
                Decimal("0.01"),
            ],
        )

    def test_200000_count_mode_uses_five_and_a_half_digit_ranges(self):
        self.assertEqual(
            [
                self.create_bench().voltage_resolution(value, "200000")
                for value in ("0.199", "1.99", "19.9", "199", "999")
            ],
            [
                Decimal("0.000001"),
                Decimal("0.00001"),
                Decimal("0.0001"),
                Decimal("0.001"),
                Decimal("0.01"),
            ],
        )

    def test_digit_class_modes_publish_expected_resolution(self):
        expected = {
            "2000": ("1.999", Decimal("0.001")),
            "4000": ("3.999", Decimal("0.001")),
            "20000": ("19.999", Decimal("0.001")),
            "60000": ("59.999", Decimal("0.001")),
            "200000": ("199.999", Decimal("0.001")),
            "1200000": ("1.199999", Decimal("0.000001")),
        }
        for mode, (value, resolution) in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(
                    self.create_bench().voltage_resolution(value, mode),
                    resolution,
                )

    def test_voltage_measurement_error_is_at_most_two_counts(self):
        for voltage in ("0.499", "4.99", "30"):
            with self.subTest(voltage=voltage):
                bench = self.create_bench()
                resolution = bench.voltage_resolution(voltage)
                reading = bench.measure_voltage(float(voltage))
                self.assertLessEqual(
                    abs(reading - Decimal(voltage)),
                    resolution * 2,
                )

    def test_voltage_above_highest_range_is_rejected(self):
        with self.assertRaisesMessage(ValueError, "exceeds"):
            self.create_bench().measure_voltage(500.01)


class TaskViewTests(TestCase):
    """Verify access and navigation for the Tasks workspace."""

    def setUp(self):
        """Create a user for authenticated requests."""
        self.user = get_user_model().objects.create_user(
            username="task-user",
            password="test-password",
        )
        self.instrument = Instrument.objects.create(
            name="Task Mock",
            manufacturer="OIL",
            model_name="Mock",
            driver=Instrument.Driver.MOCK,
            address="mock-dmm://default",
        )
        self.power_supply = Instrument.objects.create(
            name="Task PSU",
            manufacturer="OIL",
            model_name="Mock PSU",
            driver=Instrument.Driver.MOCK_DC_POWER_SUPPLY,
            address="mock-psu://default",
        )

    def test_task_page_requires_authentication(self):
        """Anonymous users are redirected to the login page."""
        response = self.client.get(reverse("task_list"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('task_list')}",
        )

    def test_task_page_is_available_to_authenticated_users(self):
        """Authenticated users can open the Tasks workspace."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<div class="oil-header-page-title">Task</div>',
            html=True,
        )

    def test_navigation_contains_task_link(self):
        """The shared navigation links to the Tasks workspace."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(response, f'href="{reverse("task_list")}"', count=2)

    def test_task_page_provides_new_tab_controls(self):
        """The workspace includes controls and templates for task tabs."""
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(response, 'id="task-new-button"')
        self.assertContains(response, 'id="task-open-button"')
        self.assertContains(response, 'id="task-delete-button"')
        self.assertContains(response, 'id="task-tabs"')
        self.assertContains(response, 'id="task-tab-content"')
        self.assertContains(response, 'id="task-tab-template"')
        self.assertContains(response, 'id="task-pane-template"')
        self.assertContains(response, 'id="saved-task-pane-template"')
        self.assertContains(response, 'id="saved-tasks-tab"')
        self.assertContains(response, 'id="task-status-filter"')
        self.assertContains(response, "tasks/js/task_tabs.js?v=39")
        self.assertContains(response, "task-stop-button")
        self.assertContains(response, "task-complete-button")
        self.assertContains(response, "saved-task-elapsed")
        self.assertContains(response, "Acquisition time")
        self.assertContains(response, "Live chart")
        self.assertContains(response, "task-live-chart")
        self.assertContains(response, '<option value="week">Week</option>')
        self.assertContains(response, '<option value="month">Month</option>')
        self.assertNotContains(response, "Last week")
        self.assertContains(response, "task-sample-table-scroll")
        self.assertContains(response, "Add instrument")
        self.assertContains(response, "task-instrument-select")
        self.assertContains(response, "task-instrument-tabs")
        self.assertContains(response, "Task name")
        self.assertContains(response, "Short description")
        self.assertContains(response, "Measurement type")
        self.assertContains(response, "Start delay (seconds)")
        self.assertContains(response, "Single")
        self.assertContains(response, "Continuous")
        self.assertContains(response, "Loop")
        self.assertContains(response, "Trigger:")
        self.assertNotContains(response, "Trigger period")
        self.assertContains(response, "HH : MM : SS : hundredth")
        self.assertContains(response, "Number of measurements")
        self.assertNotContains(response, "Task settings")
        self.assertContains(response, "Back")

    def test_saved_task_list_is_limited_to_current_user(self):
        """Users only see their own saved measurement tasks."""
        own_task = AutomationTask.objects.create(
            user=self.user,
            name="Own task",
            power_supply=self.power_supply,
            voltage_meter=self.instrument,
            voltage_mode=AutomationTask.VoltageMode.SWEEP,
            voltage_source=AutomationTask.VoltageSource.VIRTUAL,
            start_voltage=0,
            stop_voltage=1,
            voltage_step=1,
            interval_seconds=1,
            status=AutomationTask.Status.RUNNING,
            started_at=timezone.now(),
        )
        other_user = get_user_model().objects.create_user(
            username="other-task-user",
            password="test-password",
        )
        other_task = AutomationTask.objects.create(
            user=other_user,
            name="Other task",
            power_supply=self.power_supply,
            voltage_meter=self.instrument,
            start_voltage=0,
            stop_voltage=1,
            voltage_step=1,
            interval_seconds=1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(
            response,
            f'data-task-id="{own_task.pk}"',
        )
        self.assertContains(response, f"<td>{own_task.pk:04d}</td>", html=True)
        self.assertNotContains(
            response,
            f'data-task-id="{other_task.pk}"',
        )
        self.assertContains(response, 'data-status="running"')

    def test_saved_tasks_are_listed_newest_first(self):
        """A newer saved task appears above an older task."""
        older = AutomationTask.objects.create(user=self.user, name="Older task")
        newer = AutomationTask.objects.create(user=self.user, name="Newer task")
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))
        content = response.content.decode()

        self.assertLess(
            content.index(f'data-task-id="{newer.pk}"'),
            content.index(f'data-task-id="{older.pk}"'),
        )

    def test_saved_task_list_includes_measurement_count(self):
        """Saved task rows contain the number of related measurements."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Completed task",
            power_supply=self.power_supply,
            voltage_meter=self.instrument,
            start_voltage=0,
            stop_voltage=1,
            voltage_step=1,
            interval_seconds=1,
            status=AutomationTask.Status.COMPLETED,
            started_at=timezone.now(),
        )
        TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=1,
            measured_voltage=1.001,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(response, 'data-measurement-count="1"')
        self.assertContains(response, "task-row-started")
        self.assertContains(response, "task-row-state")
        self.assertContains(response, "Completed")

    def test_saved_task_list_displays_database_id(self):
        """The saved task table includes each task's database ID."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Numbered task",
            interval_seconds=1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_list"))

        self.assertContains(response, '<th scope="col">ID</th>', html=True)
        self.assertContains(response, f"<td>{task.pk:04d}</td>", html=True)
        self.assertContains(response, "task-row table-active")
        self.assertContains(response, 'aria-selected="true"')

    @patch("tasks.views.TaskRunner.start")
    def test_create_endpoint_saves_and_schedules_valid_task(self, start):
        """A valid form creates an owned persistent background task."""
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Bench sweep",
                "description": "Check the virtual bench voltage sweep.",
                "measurement_mode": "loop",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "5",
                "trigger_hundredths": "25",
                "requested_samples": "1000",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": self.power_supply.pk,
                            "configuration": {
                                "mode": "sweep",
                                "start_voltage": "0.000",
                                "stop_voltage": "2.000",
                                "voltage_step": "1.000",
                                "cycle_count": "1",
                                "readback_voltage": True,
                            },
                        },
                        {
                            "instrument_id": self.instrument.pk,
                            "configuration": {
                                "function": "dc_voltage",
                                "source": "virtual",
                                "count_mode": "200000",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201)
        task = AutomationTask.objects.get()
        self.assertEqual(task.user, self.user)
        self.assertEqual(task.name, "Bench sweep")
        self.assertEqual(
            task.description,
            "Check the virtual bench voltage sweep.",
        )
        self.assertEqual(task.measurement_mode, "loop")
        self.assertEqual(task.interval_seconds, 5.25)
        self.assertEqual(task.start_delay_seconds, 1)
        self.assertEqual(task.requested_samples, 1000)
        self.assertEqual(task.task_instruments.count(), 2)
        self.assertEqual(
            task.task_instruments.get(
                instrument=self.instrument,
            ).configuration["count_mode"],
            "200000",
        )
        self.assertTrue(
            task.task_instruments.get(
                instrument=self.power_supply,
            ).configuration["readback_voltage"],
        )
        payload = response.json()
        self.assertEqual(payload["id"], task.pk)
        self.assertEqual(payload["name"], "Bench sweep")
        self.assertEqual(payload["status"], AutomationTask.Status.PENDING)
        self.assertEqual(payload["sample_count"], 0)
        self.assertEqual(
            payload["trigger_period"],
            {"hours": 0, "minutes": 0, "seconds": 5, "hundredths": 25},
        )
        start.assert_called_once_with(task.pk)

    @patch("tasks.views.TaskRunner.start")
    def test_create_accepts_mock_rnd_as_virtual_dmm_source(self, start):
        """Mock DMM can read voltage from the RND supply simulator."""
        mock_rnd = Instrument.objects.create(
            name="Task RND simulator",
            manufacturer="RND Lab",
            model_name="320-3005P",
            driver=Instrument.Driver.MOCK_RND_320_3005P,
            address="mock-rnd-psu://default",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "RND virtual sweep",
                "measurement_mode": "loop",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "requested_samples": "3",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": mock_rnd.pk,
                            "configuration": {
                                "mode": "sweep",
                                "start_voltage": "0.00",
                                "stop_voltage": "2.00",
                                "voltage_step": "1.00",
                                "cycle_count": "1",
                                "sweep_back": "true",
                                "readback_voltage": True,
                                "output_tolerance_value": "100",
                                "output_tolerance_unit": "uV",
                            },
                        },
                        {
                            "instrument_id": self.instrument.pk,
                            "configuration": {
                                "function": "dc_voltage",
                                "source": "virtual",
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        assignment = TaskInstrument.objects.get(instrument=mock_rnd)
        self.assertEqual(
            assignment.configuration["output_tolerance_mv"],
            "0.100",
        )
        self.assertEqual(
            assignment.configuration["output_tolerance_value"],
            "100",
        )
        self.assertEqual(assignment.configuration["output_tolerance_unit"], "uV")
        self.assertTrue(assignment.configuration["sweep_back"])
        start.assert_called_once()

    @patch("tasks.views.TaskRunner.start")
    def test_fixed_supply_accepts_only_set_voltage(self, start):
        """Fixed mode normalizes one setpoint without sweep fields."""
        mock_rnd = Instrument.objects.create(
            name="Fixed RND simulator",
            manufacturer="RND Lab",
            model_name="320-3005P",
            driver=Instrument.Driver.MOCK_RND_320_3005P,
            address="mock-rnd-psu://fixed",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Continuous fixed output",
                "measurement_mode": "continuous",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "requested_samples": "2",
                "instruments": json.dumps(
                    [
                        {
                            "instrument_id": mock_rnd.pk,
                            "configuration": {
                                "mode": "fixed",
                                "set_voltage": "4.99",
                                "output_tolerance_mv": "1",
                                "readback_voltage": True,
                            },
                        },
                    ],
                ),
            },
        )

        self.assertEqual(response.status_code, 201, response.content)
        config = TaskInstrument.objects.get(instrument=mock_rnd).configuration
        self.assertEqual(config["set_voltage"], "4.99")
        self.assertEqual(config["start_voltage"], "4.99")
        self.assertEqual(config["stop_voltage"], "4.99")
        self.assertEqual(config["voltage_step"], "0.01")
        start.assert_called_once()

    @patch("tasks.views.TaskRunner.start")
    def test_rpi_temperature_can_use_secondary_chart_axis(self, start):
        sensor = Instrument.objects.create(
            name="RPi temperature",
            manufacturer="Raspberry Pi",
            model_name="CPU thermal sensor",
            driver=Instrument.Driver.RPI_CPU_TEMPERATURE,
            address="/sys/class/thermal/thermal_zone0/temp",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("task_create"),
            {
                "name": "Secondary temperature axis",
                "measurement_mode": "single",
                "trigger_hours": "0",
                "trigger_minutes": "0",
                "trigger_seconds": "1",
                "trigger_hundredths": "0",
                "requested_samples": "2",
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

    def test_task_detail_does_not_expose_another_users_task(self):
        """Task details are private to their owner."""
        other_user = get_user_model().objects.create_user(
            username="detail-owner",
            password="test-password",
        )
        task = AutomationTask.objects.create(
            user=other_user,
            name="Private",
            power_supply=self.power_supply,
            voltage_meter=self.instrument,
            start_voltage=0,
            stop_voltage=1,
            voltage_step=1,
            interval_seconds=1,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_detail", args=[task.pk]))

        self.assertEqual(response.status_code, 404)

    def test_chart_data_downsamples_long_ranges(self):
        """A chart range stays bounded while reporting its full sample count."""
        task = AutomationTask.objects.create(user=self.user, name="Chart task")
        started = timezone.now() - timedelta(seconds=1004)
        TaskSample.objects.bulk_create(
            TaskSample(
                task=task,
                index=index,
                voltage_setpoint=0,
                timestamp=started + timedelta(seconds=index - 1),
            )
            for index in range(1, 1006)
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("task_chart_data", args=[task.pk]),
            {"range": "month"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sample_count"], 1005)
        self.assertLessEqual(len(response.json()["samples"]), 1000)

    def test_task_detail_hides_an_in_progress_sample(self):
        """Polling exposes a sample only after its acquisition has finished."""
        task = AutomationTask.objects.create(user=self.user, name="Active task")
        TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=0,
            status=TaskSample.Status.COMPLETED,
            acquisition_time_seconds=Decimal("0.500"),
        )
        TaskSample.objects.create(
            task=task,
            index=2,
            voltage_setpoint=0,
            status=TaskSample.Status.ACQUIRING,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_detail", args=[task.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sample_count"], 1)
        self.assertEqual(
            [sample["index"] for sample in response.json()["samples"]],
            [1],
        )

    def test_owner_can_stop_task_after_server_restart(self):
        """A task without an in-process worker can still be stopped."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Interrupted by restart",
            status=AutomationTask.Status.RUNNING,
            started_at=timezone.now(),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_stop", args=[task.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"stopping": True})
        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.STOPPED)
        self.assertTrue(task.stop_requested)
        self.assertIsNotNone(task.finished_at)

    def test_owner_can_delete_completed_task(self):
        """Deleting a task also removes its assignments and readings."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Delete me",
            status=AutomationTask.Status.COMPLETED,
        )
        assignment = TaskInstrument.objects.create(
            task=task,
            instrument=self.instrument,
            configuration={
                "function": "dc_voltage",
                "source": "external",
            },
        )
        sample = TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=0,
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Voltage DC",
            value=1,
            unit="V",
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_delete", args=[task.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": True, "id": task.pk})
        self.assertFalse(AutomationTask.objects.filter(pk=task.pk).exists())
        self.assertFalse(TaskSample.objects.filter(pk=sample.pk).exists())
        self.assertFalse(
            TaskInstrument.objects.filter(pk=assignment.pk).exists(),
        )
        self.assertFalse(TaskReading.objects.exists())

    def test_active_task_cannot_be_deleted(self):
        """A running task must be stopped before it can be deleted."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Still running",
            status=AutomationTask.Status.RUNNING,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_delete", args=[task.pk]))

        self.assertEqual(response.status_code, 409)
        self.assertTrue(AutomationTask.objects.filter(pk=task.pk).exists())

    def test_owner_can_mark_stopped_task_as_completed(self):
        """An owner can finalize a task after stopping it."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Stopped task",
            status=AutomationTask.Status.STOPPED,
        )
        sample = TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=1,
            acquisition_time_seconds=Decimal("0.523"),
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_complete", args=[task.pk]))

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["samples"][0]["index"], sample.index)
        self.assertEqual(
            response.json()["samples"][0]["acquisition_time_seconds"],
            "0.523",
        )

    def test_running_task_cannot_be_marked_as_completed(self):
        """An active task must be stopped before it can be finalized."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Running task",
            status=AutomationTask.Status.RUNNING,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_complete", args=[task.pk]))

        self.assertEqual(response.status_code, 409)
        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.RUNNING)

    def test_user_cannot_complete_another_users_task(self):
        """A user cannot finalize another owner's stopped task."""
        other_user = get_user_model().objects.create_user(
            username="complete-owner",
        )
        task = AutomationTask.objects.create(
            user=other_user,
            name="Another stopped task",
            status=AutomationTask.Status.STOPPED,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_complete", args=[task.pk]))

        self.assertEqual(response.status_code, 404)
        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.STOPPED)

    def test_user_cannot_delete_another_users_task(self):
        """A direct delete request cannot remove another owner's task."""
        other_user = get_user_model().objects.create_user(
            username="delete-owner",
        )
        task = AutomationTask.objects.create(
            user=other_user,
            name="Private task",
            status=AutomationTask.Status.COMPLETED,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_delete", args=[task.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(AutomationTask.objects.filter(pk=task.pk).exists())

    def test_completed_task_exports_pivoted_instrument_csv(self):
        """CSV contains one column per configured task instrument."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="CSV task",
            power_supply=self.power_supply,
            status=AutomationTask.Status.COMPLETED,
        )
        assignment = TaskInstrument.objects.create(
            task=task,
            instrument=self.power_supply,
            configuration={
                "mode": "fixed",
                "start_voltage": "5.000",
                "stop_voltage": "5.000",
                "voltage_step": "1.000",
                "cycle_count": 1,
                "readback_voltage": True,
            },
        )
        sample = TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=5,
            acquisition_time_seconds="0.174",
            timestamp=datetime(2026, 8, 11, 12, 32, 5, 174000, tzinfo=UTC),
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Voltage setpoint",
            value=5,
            unit="V",
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Output voltage readback",
            value="4.98",
            unit="V",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_export_csv", args=[task.pk]))
        content = b"".join(response.streaming_content).decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(
            "ID;Time;Acquisition Time (s);"
            "Task PSU — Set voltage (V);Task PSU — Read voltage (V)",
            content,
        )
        self.assertIn(
            "1;2026-08-11T14:32:05.174+02:00;0,174;5,000;4,980",
            content,
        )

    def test_csv_uses_european_format_for_complete_instrument_row(self):
        """CSV exports one unit-labelled numeric row per trigger."""
        mock_rnd = Instrument.objects.create(
            name="Mock RND",
            manufacturer="RND Lab",
            model_name="320-3005P",
            driver=Instrument.Driver.MOCK_RND_320_3005P,
            address="mock-rnd-psu://csv",
        )
        rpi_sensor = Instrument.objects.create(
            name="RPi CPU Temperature",
            manufacturer="Raspberry Pi",
            model_name="CPU thermal sensor",
            driver=Instrument.Driver.RPI_CPU_TEMPERATURE,
            address="/sys/class/thermal/thermal_zone0/temp",
        )
        task = AutomationTask.objects.create(
            user=self.user,
            name="European CSV",
            status=AutomationTask.Status.COMPLETED,
        )
        rnd_assignment = TaskInstrument.objects.create(
            task=task,
            instrument=mock_rnd,
            order=0,
            configuration={"mode": "fixed", "readback_voltage": True},
        )
        dmm_assignment = TaskInstrument.objects.create(
            task=task,
            instrument=self.instrument,
            order=1,
            configuration={"function": "dc_voltage", "source": "virtual"},
        )
        temperature_assignment = TaskInstrument.objects.create(
            task=task,
            instrument=rpi_sensor,
            order=2,
            configuration={"function": "temperature", "source": "external"},
        )
        sample = TaskSample.objects.create(
            task=task,
            index=125,
            voltage_setpoint=5,
            acquisition_time_seconds="0.174",
            timestamp=datetime(2026, 8, 11, 12, 32, 5, 174000, tzinfo=UTC),
        )
        for assignment, parameter, value, unit in (
            (rnd_assignment, "Voltage setpoint", "5.00", "V"),
            (rnd_assignment, "Output voltage readback", "5.00", "V"),
            (dmm_assignment, "Voltage DC", "4.9999", "V"),
            (temperature_assignment, "Temperature", "48.75", "°C"),
        ):
            TaskReading.objects.create(
                sample=sample,
                task_instrument=assignment,
                parameter=parameter,
                value=value,
                unit=unit,
            )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_export_csv", args=[task.pk]))
        content = b"".join(response.streaming_content).decode("utf-8-sig")

        self.assertIn(
            "ID;Time;Acquisition Time (s);Mock RND — Set voltage (V);"
            "Mock RND — Read voltage (V);Task Mock (V);"
            "RPi CPU Temperature (°C)",
            content,
        )
        self.assertIn(
            "125;2026-08-11T14:32:05.174+02:00;0,174;"
            "5,00;5,00;4,9999;48,75",
            content,
        )

    def test_user_cannot_export_another_users_task(self):
        """Direct CSV URLs do not expose another owner's task."""
        other_user = get_user_model().objects.create_user(
            username="csv-owner",
        )
        task = AutomationTask.objects.create(
            user=other_user,
            name="Private CSV",
            power_supply=self.power_supply,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_export_csv", args=[task.pk]))

        self.assertEqual(response.status_code, 404)


class AutomationRunnerTests(TestCase):
    """Exercise a complete virtual-bench automation task."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="runner-user",
        )
        self.power_supply = Instrument.objects.create(
            name="Runner PSU",
            manufacturer="OIL",
            model_name="Mock PSU",
            driver=Instrument.Driver.MOCK_DC_POWER_SUPPLY,
            address="mock-psu://default",
        )
        self.meter = Instrument.objects.create(
            name="Runner DMM",
            manufacturer="OIL",
            model_name="Mock DMM",
            driver=Instrument.Driver.MOCK,
            address="mock-dmm://default",
        )

    def create_task(self, **overrides):
        values = {
            "user": self.user,
            "name": "Virtual sweep",
            "power_supply": self.power_supply,
            "voltage_meter": self.meter,
            "temperature_meter": self.meter,
            "voltage_mode": AutomationTask.VoltageMode.SWEEP,
            "voltage_source": AutomationTask.VoltageSource.VIRTUAL,
            "start_voltage": Decimal("0.000"),
            "stop_voltage": Decimal("2.000"),
            "voltage_step": Decimal("1.000"),
            "measurement_mode": AutomationTask.MeasurementMode.LOOP,
            "requested_samples": 3,
            "interval_seconds": 0.1,
            "start_delay_seconds": 0,
            "temperature_min": Decimal("20.00"),
            "temperature_max": Decimal("21.00"),
            "temperature_resolution": Decimal("0.10"),
            "temperature_seed": 7,
        }
        values.update(overrides)
        return AutomationTask.objects.create(**values)

    def test_resume_continues_after_last_stored_sample(self):
        """A restarted task preserves history and uses the next sample index."""
        started_at = timezone.now() - timedelta(minutes=5)
        task = self.create_task(
            status=AutomationTask.Status.RUNNING,
            started_at=started_at,
        )
        TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=Decimal("0.000"),
            status=TaskSample.Status.COMPLETED,
        )
        interrupted = TaskSample.objects.create(
            task=task,
            index=2,
            voltage_setpoint=Decimal("1.000"),
            status=TaskSample.Status.ACQUIRING,
        )

        run_automation_task(task.pk, resume=True)

        task.refresh_from_db()
        interrupted.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(task.started_at, started_at)
        self.assertEqual(interrupted.status, TaskSample.Status.FAILED)
        self.assertIn("restart", interrupted.error)
        self.assertEqual(
            list(task.samples.values_list("index", flat=True)),
            [1, 2, 3],
        )
        self.assertEqual(
            task.samples.get(index=3).status,
            TaskSample.Status.COMPLETED,
        )

    def test_voltage_sequences_are_inclusive(self):
        """Sweep and Cycle include configured endpoints."""
        task = self.create_task()
        self.assertEqual(
            voltage_sequence(task),
            (Decimal("0.000"), Decimal("1.000"), Decimal("2.000")),
        )

        task.sweep_back = True
        self.assertEqual(
            voltage_sequence(task),
            (
                Decimal("0.000"),
                Decimal("1.000"),
                Decimal("2.000"),
                Decimal("1.000"),
                Decimal("0.000"),
            ),
        )

        task.voltage_mode = AutomationTask.VoltageMode.CYCLE
        task.cycle_count = 2
        self.assertEqual(
            voltage_sequence(task),
            (
                Decimal("0.000"),
                Decimal("1.000"),
                Decimal("2.000"),
                Decimal("1.000"),
                Decimal("0.000"),
                Decimal("1.000"),
                Decimal("2.000"),
                Decimal("1.000"),
                Decimal("0.000"),
            ),
        )

    def test_continuous_sweep_finishes_at_program_endpoint(self):
        """Continuous acquisition runs one finite PSU sweep and then finishes."""
        task = self.create_task(
            voltage_mode=AutomationTask.VoltageMode.SWEEP,
            cycle_count=1,
            measurement_mode=AutomationTask.MeasurementMode.CONTINUOUS,
        )
        base_sequence = voltage_sequence(task)

        values = tuple(measurement_sequence(task, base_sequence))

        self.assertEqual(
            values,
            (
                Decimal("0.000"),
                Decimal("1.000"),
                Decimal("2.000"),
            ),
        )

    @patch("threading.Event.wait", return_value=False)
    def test_runner_stores_virtual_voltage_and_temperature(self, _wait):
        """A complete sweep stores coupled voltage and bounded temperature."""
        task = self.create_task()

        run_automation_task(task.pk)

        task.refresh_from_db()
        samples = list(task.samples.all())
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(len(samples), 3)
        self.assertEqual(
            [sample.voltage_setpoint for sample in samples],
            [Decimal("0.000"), Decimal("1.000"), Decimal("2.000")],
        )
        for sample in samples:
            self.assertGreaterEqual(sample.measured_voltage, Decimal("0"))
            self.assertGreaterEqual(sample.temperature, Decimal("20"))
            self.assertLessEqual(sample.temperature, Decimal("21"))
            self.assertIsNotNone(sample.acquisition_time_seconds)
            self.assertGreaterEqual(
                sample.acquisition_time_seconds,
                Decimal("0"),
            )

    def test_single_runner_stores_one_measurement(self):
        """Single mode stops after the first synchronized reading."""
        task = self.create_task(
            measurement_mode=AutomationTask.MeasurementMode.SINGLE,
        )

        run_automation_task(task.pk)

        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(task.samples.count(), 1)

    @patch("drivers.rpi_cpu_temperature.Path.read_text", return_value="48750\n")
    def test_runner_reads_raspberry_pi_cpu_temperature(self, _read_text):
        """A physical temperature capability is read through its driver."""
        sensor = Instrument.objects.create(
            name="RPi CPU",
            manufacturer="Raspberry Pi",
            model_name="CPU thermal sensor",
            driver=Instrument.Driver.RPI_CPU_TEMPERATURE,
            address="/sys/class/thermal/thermal_zone0/temp",
        )
        task = AutomationTask.objects.create(
            user=self.user,
            name="RPi temperature",
            measurement_mode=AutomationTask.MeasurementMode.SINGLE,
            interval_seconds=1,
        )
        assignment = TaskInstrument.objects.create(
            task=task,
            instrument=sensor,
            configuration={
                "function": "temperature",
                "source": "external",
            },
        )

        run_automation_task(task.pk)

        task.refresh_from_db()
        reading = TaskReading.objects.get(
            sample__task=task,
            task_instrument=assignment,
        )
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(reading.parameter, "Temperature")
        self.assertEqual(reading.value, Decimal("48.750"))
        self.assertEqual(reading.unit, "°C")

    def test_continuous_runner_waits_until_stopped(self):
        """Continuous mode keeps measuring until its stop event is set."""
        task = self.create_task(
            measurement_mode=AutomationTask.MeasurementMode.CONTINUOUS,
        )
        stop_event = Event()

        def stop_after_first_measurement(_interval):
            stop_event.set()
            return True

        with patch.object(
            stop_event,
            "wait",
            side_effect=stop_after_first_measurement,
        ):
            run_automation_task(task.pk, stop_event)

        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.STOPPED)
        self.assertEqual(task.samples.count(), 1)

    @patch("threading.Event.wait", return_value=False)
    def test_flexible_runner_uses_added_instrument_configurations(self, _wait):
        """Dynamic instrument assignments drive generic stored readings."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Flexible sweep",
            measurement_mode=AutomationTask.MeasurementMode.LOOP,
            interval_seconds=0.1,
            requested_samples=3,
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.power_supply,
            order=0,
            configuration={
                "mode": "sweep",
                "start_voltage": "0.000",
                "stop_voltage": "2.000",
                "voltage_step": "1.000",
                "cycle_count": 1,
                "readback_voltage": True,
            },
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.meter,
            order=1,
            configuration={
                "function": "dc_voltage",
                "source": "virtual",
            },
        )

        run_automation_task(task.pk)

        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(task.samples.count(), 3)
        self.assertEqual(TaskReading.objects.filter(
            sample__task=task,
        ).count(), 9)
        self.assertEqual(
            TaskReading.objects.filter(
                sample__task=task,
                parameter="Output voltage readback",
            ).count(),
            3,
        )
        voltage_readings = TaskReading.objects.filter(
            sample__task=task,
            parameter="Voltage DC",
        )
        self.assertEqual(voltage_readings.count(), 3)

    @patch("threading.Event.wait", return_value=False)
    def test_mock_dmm_reads_mock_rnd_virtual_voltage(self, _wait):
        """RND simulator readback drives virtual Mock DMM measurements."""
        mock_rnd = Instrument.objects.create(
            name="Runner RND simulator",
            manufacturer="RND Lab",
            model_name="320-3005P",
            driver=Instrument.Driver.MOCK_RND_320_3005P,
            address="mock-rnd-psu://default",
        )
        task = AutomationTask.objects.create(
            user=self.user,
            name="RND virtual sweep",
            measurement_mode=AutomationTask.MeasurementMode.LOOP,
            interval_seconds=0.1,
            requested_samples=3,
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=mock_rnd,
            order=0,
            configuration={
                "mode": "sweep",
                "start_voltage": "0.00",
                "stop_voltage": "2.00",
                "voltage_step": "1.00",
                "cycle_count": 1,
                "readback_voltage": True,
                "output_tolerance_mv": "1",
            },
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.meter,
            order=1,
            configuration={"function": "dc_voltage", "source": "virtual"},
        )

        run_automation_task(task.pk)

        task.refresh_from_db()
        readings = list(
            TaskReading.objects.filter(
                sample__task=task,
                parameter="Voltage DC",
            ).values_list("value", flat=True),
        )
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        output_readings = list(
            TaskReading.objects.filter(
                sample__task=task,
                parameter="Output voltage readback",
            ).values_list("value", flat=True),
        )
        self.assertEqual(
            output_readings,
            [Decimal("0"), Decimal("1"), Decimal("2")],
        )
        self.assertEqual(len(readings), 3)
        for reading, setpoint in zip(
            readings,
            (Decimal("0"), Decimal("1"), Decimal("2")),
            strict=True,
        ):
            self.assertLessEqual(abs(reading - setpoint), Decimal("0.002"))

    def test_different_physical_instruments_are_read_in_parallel(self):
        """Separate DMM connections begin acquisition concurrently."""
        second_meter = Instrument.objects.create(
            name="Runner DMM 2",
            manufacturer="OIL",
            model_name="Mock DMM",
            driver=Instrument.Driver.MOCK,
            address="mock-dmm://second",
        )
        task = AutomationTask.objects.create(
            user=self.user,
            name="Parallel DMM read",
            measurement_mode=AutomationTask.MeasurementMode.SINGLE,
            interval_seconds=1,
        )
        for order, instrument in enumerate((self.meter, second_meter)):
            TaskInstrument.objects.create(
                task=task,
                instrument=instrument,
                order=order,
                configuration={
                    "function": "dc_voltage",
                    "source": "external",
                },
            )

        rendezvous = Barrier(2)

        def measure(_driver):
            rendezvous.wait(timeout=1)
            return MeasurementResult("Voltage DC", 1.0, "V")

        with patch(
            "drivers.mock.MockInstrumentDriver.measure_dc_voltage",
            autospec=True,
            side_effect=measure,
        ):
            run_automation_task(task.pk)

        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(
            TaskReading.objects.filter(sample__task=task).count(),
            2,
        )

    def test_failed_sample_does_not_stop_later_acquisitions(self):
        """A transient instrument error marks one sample and continues."""
        task = AutomationTask.objects.create(
            user=self.user,
            name="Recover after failed sample",
            measurement_mode=AutomationTask.MeasurementMode.LOOP,
            requested_samples=2,
            interval_seconds=0.01,
        )
        TaskInstrument.objects.create(
            task=task,
            instrument=self.meter,
            configuration={
                "function": "dc_voltage",
                "source": "external",
            },
        )

        with patch(
            "drivers.mock.MockInstrumentDriver.measure_dc_voltage",
            autospec=True,
            side_effect=(
                MeasurementError("temporary timeout"),
                MeasurementResult("Voltage DC", 1.25, "V"),
            ),
        ):
            run_automation_task(task.pk)

        task.refresh_from_db()
        samples = list(task.samples.all())
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(
            [sample.status for sample in samples],
            [TaskSample.Status.FAILED, TaskSample.Status.COMPLETED],
        )
        self.assertIn("temporary timeout", samples[0].error)
        self.assertEqual(samples[1].readings.count(), 1)
