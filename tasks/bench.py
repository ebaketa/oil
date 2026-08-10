"""Deterministic virtual-bench signal sources for automation tasks."""

import random
from decimal import Decimal, ROUND_HALF_UP


class VirtualMockBench:
    """Couple a Mock PSU output to repeatable simulated measurements."""

    VOLTAGE_RANGES = (
        (Decimal("0.5"), Decimal("0.00001")),
        (Decimal("5"), Decimal("0.0001")),
        (Decimal("50"), Decimal("0.001")),
        (Decimal("500"), Decimal("0.01")),
    )

    def __init__(
        self,
        *,
        seed: int,
        temperature_min: Decimal,
        temperature_max: Decimal,
        temperature_resolution: Decimal,
    ) -> None:
        self._random = random.Random(seed)
        self.temperature_min = temperature_min
        self.temperature_max = temperature_max
        self.temperature_resolution = temperature_resolution

    def measure_voltage(self, output_voltage: float) -> Decimal:
        """Measure voltage on the smallest fitting 50,000-count range."""
        input_value = Decimal(str(output_voltage))
        resolution = self.voltage_resolution(input_value)
        error_counts = self._random.choice((-2, -1, 0, 0, 0, 1, 2))
        value = input_value + Decimal(error_counts) * resolution
        return max(Decimal("0"), value).quantize(
            resolution,
            rounding=ROUND_HALF_UP,
        )

    @classmethod
    def voltage_resolution(cls, voltage) -> Decimal:
        """Return resolution for the smallest range containing the voltage."""
        magnitude = abs(Decimal(str(voltage)))
        for full_scale, resolution in cls.VOLTAGE_RANGES:
            if magnitude <= full_scale:
                return resolution
        raise ValueError("Voltage exceeds the simulated 500 V DMM range.")

    @classmethod
    def voltage_decimal_places(cls, voltage) -> int:
        """Return display precision selected by voltage autoranging."""
        return -cls.voltage_resolution(voltage).as_tuple().exponent

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
