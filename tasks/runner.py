"""Background execution for persistent automation tasks."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal
from itertools import chain, islice, repeat
from time import monotonic
from threading import Event, Lock

from django.db import close_old_connections
from django.utils import timezone

from services.connection_manager import ConnectionManager

from .bench import VirtualMockBench
from .models import AutomationTask, TaskReading, TaskSample


def voltage_sequence(task: AutomationTask) -> tuple[Decimal, ...]:
    """Build a bounded inclusive fixed, sweep, or cycle sequence."""
    start = task.start_voltage
    stop = task.stop_voltage
    step = task.voltage_step

    if task.voltage_mode == AutomationTask.VoltageMode.FIXED:
        return tuple(start for _index in range(task.cycle_count))

    direction = Decimal("1") if stop > start else Decimal("-1")
    signed_step = step * direction
    values = []
    value = start
    while (direction > 0 and value <= stop) or (
        direction < 0 and value >= stop
    ):
        values.append(value)
        value += signed_step
    if values[-1] != stop:
        values.append(stop)

    if task.voltage_mode == AutomationTask.VoltageMode.SWEEP:
        return tuple(values)

    reverse_values = values[-2::-1]
    complete_cycle = values + reverse_values
    if task.cycle_count == 1:
        return tuple(complete_cycle)
    subsequent_cycle = values[1:] + reverse_values
    return tuple(
        complete_cycle + subsequent_cycle * (task.cycle_count - 1),
    )


def measurement_sequence(task, base_sequence):
    """Apply the selected measurement mode to an instrument sequence."""
    if task.measurement_mode == AutomationTask.MeasurementMode.SINGLE:
        return base_sequence[:1]
    if task.measurement_mode == AutomationTask.MeasurementMode.LOOP:
        return tuple(
            islice(
                chain(base_sequence, repeat(base_sequence[-1])),
                task.requested_samples,
            ),
        )
    if len(base_sequence) > 1:
        return base_sequence
    return repeat(base_sequence[-1])


def run_automation_task(task_id: int, stop_event: Event | None = None) -> None:
    """Execute one task and persist synchronized samples."""
    close_old_connections()
    event = stop_event or Event()
    task = (
        AutomationTask.objects.select_related(
            "power_supply",
            "voltage_meter",
            "temperature_meter",
        )
        .prefetch_related("task_instruments__instrument")
        .get(pk=task_id)
    )
    task.status = AutomationTask.Status.RUNNING
    task.started_at = timezone.now()
    task.finished_at = None
    task.error = ""
    task.stop_requested = False
    task.save(
        update_fields=(
            "status",
            "started_at",
            "finished_at",
            "error",
            "stop_requested",
        ),
    )

    assignments = list(task.task_instruments.all())
    flexible = bool(assignments)
    supply_assignment = next(
        (
            assignment
            for assignment in assignments
            if assignment.instrument.is_power_supply
        ),
        None,
    )
    if flexible and supply_assignment:
        supply_config = supply_assignment.configuration
        task.voltage_mode = supply_config["mode"]
        task.start_voltage = Decimal(supply_config["start_voltage"])
        task.stop_voltage = Decimal(supply_config["stop_voltage"])
        task.voltage_step = Decimal(supply_config["voltage_step"])
        task.cycle_count = int(supply_config.get("cycle_count", 1))

    benches = {}
    for assignment in assignments:
        config = assignment.configuration
        if config.get("function") == "temperature":
            benches[assignment.pk] = VirtualMockBench(
                seed=int(config.get("seed", 1)),
                temperature_min=Decimal(config["minimum"]),
                temperature_max=Decimal(config["maximum"]),
                temperature_resolution=Decimal(config["resolution"]),
            )
    legacy_bench = VirtualMockBench(
        seed=task.temperature_seed,
        temperature_min=task.temperature_min,
        temperature_max=task.temperature_max,
        temperature_resolution=task.temperature_resolution,
    )

    try:
        with ExitStack() as stack:
            if flexible:
                instruments = {
                    assignment.instrument_id: assignment.instrument
                    for assignment in assignments
                }
            else:
                instruments = {
                    task.power_supply_id: task.power_supply,
                }
                if task.voltage_meter_id:
                    instruments[task.voltage_meter_id] = task.voltage_meter
                if task.temperature_meter_id:
                    instruments[
                        task.temperature_meter_id
                    ] = task.temperature_meter
            drivers = {
                instrument_id: stack.enter_context(
                    ConnectionManager.temporary_session(instrument),
                )
                for instrument_id, instrument in instruments.items()
            }
            for assignment in assignments:
                driver = drivers[assignment.instrument_id]
                if assignment.configuration.get("display_off", False):
                    stack.callback(driver.set_display_enabled, True)
                    driver.set_display_enabled(False)
                prepare = getattr(driver, "prepare_measurement", None)
                function = assignment.configuration.get("function")
                if prepare is not None and function:
                    prepare(function)
            supply_id = (
                supply_assignment.instrument_id
                if supply_assignment
                else task.power_supply_id
            )
            supply = drivers.get(supply_id)

            base_sequence = (
                voltage_sequence(task)
                if supply
                else (Decimal("0"),)
            )
            sequence = measurement_sequence(task, base_sequence)
            trigger_started = monotonic() + task.start_delay_seconds
            for index, voltage in enumerate(sequence, start=1):
                trigger_deadline = (
                    trigger_started + (index - 1) * task.interval_seconds
                )
                wait_seconds = max(0, trigger_deadline - monotonic())
                if wait_seconds and event.wait(wait_seconds):
                    task.status = AutomationTask.Status.STOPPED
                    break
                task.refresh_from_db(fields=("stop_requested",))
                if event.is_set() or task.stop_requested:
                    task.status = AutomationTask.Status.STOPPED
                    break

                triggered_at = timezone.now()
                if supply:
                    supply.set_voltage(voltage)
                    if index == 1:
                        supply.enable_output()
                    if (
                        supply_assignment
                        and supply_assignment.configuration.get(
                            "readback_voltage",
                            False,
                        )
                    ):
                        settling_seconds = getattr(
                            supply,
                            "VOLTAGE_SETTLING_SECONDS",
                            0,
                        )
                        if settling_seconds and event.wait(settling_seconds):
                            task.status = AutomationTask.Status.STOPPED
                            break
                measured_voltage = None
                temperature = None
                sample = TaskSample.objects.create(
                    task=task,
                    index=index,
                    voltage_setpoint=voltage,
                    timestamp=triggered_at,
                )

                if flexible:
                    for assignment in assignments:
                        if assignment is supply_assignment:
                            TaskReading.objects.create(
                                sample=sample,
                                task_instrument=assignment,
                                parameter="Voltage setpoint",
                                value=voltage,
                                unit="V",
                            )
                            if assignment.configuration.get(
                                "readback_voltage",
                                False,
                            ):
                                TaskReading.objects.create(
                                    sample=sample,
                                    task_instrument=assignment,
                                    parameter="Output voltage readback",
                                    value=Decimal(
                                        str(supply.measure_output_voltage()),
                                    ),
                                    unit="V",
                                )
                            continue
                        config = assignment.configuration
                        function = config["function"]
                        if function == "temperature":
                            value = benches[
                                assignment.pk
                            ].measure_temperature()
                            parameter = "Temperature"
                            unit = "°C"
                            if temperature is None:
                                temperature = value
                        elif (
                            function == "dc_voltage"
                            and config.get("source") == "virtual"
                        ):
                            value = legacy_bench.measure_voltage(
                                supply.measure_output_voltage(),
                            )
                            parameter = "Voltage DC"
                            unit = "V"
                            if measured_voltage is None:
                                measured_voltage = value
                        else:
                            driver = drivers[assignment.instrument_id]
                            method = getattr(driver, f"measure_{function}")
                            result = method()
                            value = Decimal(str(result.value))
                            parameter = result.parameter
                            unit = result.unit
                            if function == "dc_voltage" and measured_voltage is None:
                                measured_voltage = value
                        TaskReading.objects.create(
                            sample=sample,
                            task_instrument=assignment,
                            parameter=parameter,
                            value=value,
                            unit=unit,
                        )
                elif task.voltage_meter_id:
                    if (
                        task.voltage_source
                        == AutomationTask.VoltageSource.VIRTUAL
                    ):
                        measured_voltage = legacy_bench.measure_voltage(
                            supply.measure_output_voltage(),
                        )
                    else:
                        result = drivers[
                            task.voltage_meter_id
                        ].measure_dc_voltage()
                        measured_voltage = Decimal(str(result.value))

                if not flexible and task.temperature_meter_id:
                    temperature = legacy_bench.measure_temperature()

                sample.measured_voltage = measured_voltage
                sample.temperature = temperature
                sample.save(
                    update_fields=("measured_voltage", "temperature"),
                )

            else:
                task.status = AutomationTask.Status.COMPLETED

            if supply:
                supply.disable_output()
    except Exception as exc:
        task.status = AutomationTask.Status.FAILED
        task.error = str(exc) or exc.__class__.__name__
    finally:
        task.finished_at = timezone.now()
        task.save(update_fields=("status", "error", "finished_at"))
        close_old_connections()


class TaskRunner:
    """Schedule and stop in-process automation task workers."""

    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oil-task")
    _events: dict[int, Event] = {}
    _lock = Lock()

    @classmethod
    def start(cls, task_id: int) -> None:
        with cls._lock:
            if task_id in cls._events:
                raise ValueError("Task is already scheduled.")
            event = Event()
            cls._events[task_id] = event

        def execute():
            try:
                run_automation_task(task_id, event)
            finally:
                with cls._lock:
                    cls._events.pop(task_id, None)

        cls._executor.submit(execute)

    @classmethod
    def stop(cls, task_id: int) -> None:
        AutomationTask.objects.filter(pk=task_id).update(stop_requested=True)
        with cls._lock:
            event = cls._events.get(task_id)
            if event:
                event.set()
                return

        # In-process events disappear when the application server restarts.
        # Finalize a persisted active task when no local worker remains.
        AutomationTask.objects.filter(
            pk=task_id,
            status__in=(
                AutomationTask.Status.PENDING,
                AutomationTask.Status.RUNNING,
            ),
        ).update(
            status=AutomationTask.Status.STOPPED,
            finished_at=timezone.now(),
        )
