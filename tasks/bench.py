"""Deterministic virtual-bench signal sources for automation tasks."""

import random
from decimal import Decimal, ROUND_HALF_UP


class VirtualMockBench:
    """Couple a Mock PSU output to repeatable simulated measurements."""

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
        """Return PSU voltage with deterministic ±2 mV meter error."""
        error_mv = self._random.choice((-2, -1, 0, 0, 0, 1, 2))
        value = Decimal(str(output_voltage)) + Decimal(error_mv) / 1000
        return max(Decimal("0"), value).quantize(Decimal("0.0001"))

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
