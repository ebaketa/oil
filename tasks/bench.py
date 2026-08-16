"""Deterministic virtual-bench signal sources for automation tasks."""

import random
from decimal import Decimal, ROUND_HALF_UP

from drivers.mock import MockInstrumentDriver


class VirtualMockBench:
    """Couple a Mock PSU output to repeatable simulated measurements."""

    DEFAULT_COUNT_MODE = MockInstrumentDriver.DEFAULT_COUNT_MODE
    VOLTAGE_COUNT_MODES = MockInstrumentDriver.VOLTAGE_COUNT_MODES
    COUNT_MODE_LABELS = MockInstrumentDriver.COUNT_MODE_LABELS

    def __init__(
        self,
        *,
        seed: int,
        temperature_min: Decimal,
        temperature_max: Decimal,
        temperature_resolution: Decimal,
        count_mode: str = DEFAULT_COUNT_MODE,
    ) -> None:
        self._random = random.Random(seed)
        self.temperature_min = temperature_min
        self.temperature_max = temperature_max
        self.temperature_resolution = temperature_resolution
        self.validate_count_mode(count_mode)
        self.count_mode = count_mode

    def measure_voltage(
        self,
        output_voltage: float,
        count_mode: str | None = None,
    ) -> Decimal:
        """Measure voltage on the smallest fitting 50,000-count range."""
        input_value = Decimal(str(output_voltage))
        mode = count_mode or self.count_mode
        resolution = self.voltage_resolution(input_value, mode)
        error_counts = self._random.choice((-2, -1, 0, 0, 0, 1, 2))
        value = input_value + Decimal(error_counts) * resolution
        return max(Decimal("0"), value).quantize(
            resolution,
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def voltage_resolution(
        cls,
        voltage,
        count_mode: str = DEFAULT_COUNT_MODE,
    ) -> Decimal:
        """Return resolution for the smallest range containing the voltage."""
        cls.validate_count_mode(count_mode)
        magnitude = abs(Decimal(str(voltage)))
        for full_scale, resolution in cls.VOLTAGE_COUNT_MODES[count_mode]:
            if magnitude <= full_scale:
                return resolution
        maximum = cls.VOLTAGE_COUNT_MODES[count_mode][-1][0]
        raise ValueError(
            f"Voltage exceeds the simulated {maximum:g} V DMM range."
        )

    @classmethod
    def voltage_decimal_places(
        cls,
        voltage,
        count_mode: str = DEFAULT_COUNT_MODE,
    ) -> int:
        """Return display precision selected by voltage autoranging."""
        return -cls.voltage_resolution(voltage, count_mode).as_tuple().exponent

    @classmethod
    def validate_count_mode(cls, count_mode: str) -> str:
        """Reject unknown simulated count modes."""
        if count_mode not in cls.VOLTAGE_COUNT_MODES:
            raise ValueError("Select a valid Mock DMM count mode.")
        return count_mode

    def measure_temperature(self) -> Decimal:
        """Return a seeded random temperature within configured bounds."""
        span = self.temperature_max - self.temperature_min
        raw = self.temperature_min + Decimal(str(self._random.random())) * span
        steps = (raw / self.temperature_resolution).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
        value = steps * self.temperature_resolution
        return min(
            self.temperature_max,
            max(self.temperature_min, value),
        ).quantize(self.temperature_resolution)
