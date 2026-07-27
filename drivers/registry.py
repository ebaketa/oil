"""Registry for instrument driver implementations."""

from typing import TYPE_CHECKING, Mapping

from .base import BaseInstrumentDriver, MeasurementCapability

if TYPE_CHECKING:
    from main.models import Instrument


class DriverRegistry:
    """Map persistent driver names to their implementation classes."""

    _drivers: dict[str, type[BaseInstrumentDriver]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        driver_class: type[BaseInstrumentDriver],
    ) -> None:
        """Register one driver class under its persistent inventory name."""
        if not name:
            raise ValueError("A driver registry name is required.")
        if not issubclass(driver_class, BaseInstrumentDriver):
            raise TypeError(
                "Registered drivers must inherit from BaseInstrumentDriver."
            )

        existing = cls._drivers.get(name)
        if existing is not None and existing is not driver_class:
            raise ValueError(f"Driver name is already registered: {name}")
        cls._drivers[name] = driver_class

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a registered driver name when it exists."""
        cls._drivers.pop(name, None)

    @classmethod
    def get(cls, name: str) -> type[BaseInstrumentDriver]:
        """Return the implementation registered for a persistent name."""
        try:
            return cls._drivers[name]
        except KeyError as exc:
            raise ValueError(f"Unsupported instrument driver: {name}") from exc

    @classmethod
    def create(cls, instrument: "Instrument") -> BaseInstrumentDriver:
        """Create the driver configured by an instrument inventory record."""
        return cls.get(instrument.driver).from_instrument(instrument)

    @classmethod
    def capabilities(
        cls,
        name: str,
    ) -> Mapping[str, MeasurementCapability]:
        """Return capabilities for a registered driver without creating it."""
        return cls.get(name).capabilities()

    @classmethod
    def names(cls) -> tuple[str, ...]:
        """Return registered persistent driver names in stable order."""
        return tuple(sorted(cls._drivers))
