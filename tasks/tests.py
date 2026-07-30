"""Tests for the Task application."""

import json
from decimal import Decimal
from threading import Event
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.models import Instrument

from .models import (
    AutomationTask,
    TaskInstrument,
    TaskReading,
    TaskSample,
)
from .runner import run_automation_task, voltage_sequence


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
            address="mock://default",
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
        self.assertContains(response, '<h2 class="mb-0">Tasks</h2>', html=True)

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
        self.assertContains(response, "tasks/js/task_tabs.js?v=6")
        self.assertContains(response, "task-stop-button")
        self.assertContains(response, "task-complete-button")
        self.assertContains(response, "Add instrument")
        self.assertContains(response, "task-instrument-select")
        self.assertContains(response, "task-instrument-tabs")
        self.assertContains(response, "Task name")
        self.assertContains(response, "Short description")
        self.assertContains(response, "Measurement type")
        self.assertContains(response, "Single")
        self.assertContains(response, "Continuous")
        self.assertContains(response, "Loop")
        self.assertContains(response, "Interval (seconds)")
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
        self.assertNotContains(
            response,
            f'data-task-id="{other_task.pk}"',
        )
        self.assertContains(response, 'data-status="running"')

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
                "interval_seconds": "0.1",
                "requested_samples": "3",
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

        self.assertEqual(response.status_code, 201)
        task = AutomationTask.objects.get()
        self.assertEqual(task.user, self.user)
        self.assertEqual(task.name, "Bench sweep")
        self.assertEqual(
            task.description,
            "Check the virtual bench voltage sweep.",
        )
        self.assertEqual(task.measurement_mode, "loop")
        self.assertEqual(task.interval_seconds, 0.1)
        self.assertEqual(task.requested_samples, 3)
        self.assertEqual(task.task_instruments.count(), 2)
        payload = response.json()
        self.assertEqual(payload["id"], task.pk)
        self.assertEqual(payload["name"], "Bench sweep")
        self.assertEqual(payload["status"], AutomationTask.Status.PENDING)
        self.assertEqual(payload["sample_count"], 0)
        start.assert_called_once_with(task.pk)

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
        self.client.force_login(self.user)

        response = self.client.post(reverse("task_complete", args=[task.pk]))

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(response.json()["status"], "completed")

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
            },
        )
        sample = TaskSample.objects.create(
            task=task,
            index=1,
            voltage_setpoint=5,
        )
        TaskReading.objects.create(
            sample=sample,
            task_instrument=assignment,
            parameter="Voltage setpoint",
            value=5,
            unit="V",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("task_export_csv", args=[task.pk]))
        content = b"".join(response.streaming_content).decode("utf-8-sig")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Time,Task PSU", content)
        self.assertIn(",5.000000 V", content)

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
            address="mock://default",
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
            "temperature_min": Decimal("20.00"),
            "temperature_max": Decimal("21.00"),
            "temperature_resolution": Decimal("0.10"),
            "temperature_seed": 7,
        }
        values.update(overrides)
        return AutomationTask.objects.create(**values)

    def test_voltage_sequences_are_inclusive(self):
        """Sweep and Cycle include configured endpoints."""
        task = self.create_task()
        self.assertEqual(
            voltage_sequence(task),
            (Decimal("0.000"), Decimal("1.000"), Decimal("2.000")),
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

    def test_single_runner_stores_one_measurement(self):
        """Single mode stops after the first synchronized reading."""
        task = self.create_task(
            measurement_mode=AutomationTask.MeasurementMode.SINGLE,
        )

        run_automation_task(task.pk)

        task.refresh_from_db()
        self.assertEqual(task.status, AutomationTask.Status.COMPLETED)
        self.assertEqual(task.samples.count(), 1)

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
        ).count(), 6)
        voltage_readings = TaskReading.objects.filter(
            sample__task=task,
            parameter="Voltage DC",
        )
        self.assertEqual(voltage_readings.count(), 3)
