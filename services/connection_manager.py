"""Process-local lifecycle and concurrency management for instrument drivers."""

from contextlib import contextmanager
from threading import Lock, RLock
from typing import TYPE_CHECKING, Iterator

from drivers.base import BaseInstrumentDriver
from drivers.exceptions import ConnectionError
from drivers.factory import create_driver

if TYPE_CHECKING:
    from main.models import Instrument


class ConnectionManager:
    """Create, cache, lock, and close active instrument connections."""

    _connections: dict[int, BaseInstrumentDriver] = {}
    _instrument_locks: dict[int, RLock] = {}
    _locks_guard = Lock()

    @classmethod
    def _instrument_id(cls, instrument: "Instrument") -> int:
        """Return a saved instrument identifier suitable for cache keys."""
        if instrument.pk is None:
            raise ValueError("An instrument must be saved before connecting.")
        return instrument.pk

    @classmethod
    def _lock_for(cls, instrument: "Instrument") -> RLock:
        """Return the re-entrant lock assigned to an instrument."""
        instrument_id = cls._instrument_id(instrument)
        with cls._locks_guard:
            return cls._instrument_locks.setdefault(instrument_id, RLock())

    @classmethod
    def connect(cls, instrument: "Instrument") -> BaseInstrumentDriver:
        """Return an active cached driver, opening one when necessary."""
        instrument_id = cls._instrument_id(instrument)

        with cls._lock_for(instrument):
            current = cls._connections.get(instrument_id)
            if current is not None and current.connected:
                return current
            cls._connections.pop(instrument_id, None)

            driver = create_driver(instrument)
            try:
                driver.connect()
                if not driver.connected:
                    raise ConnectionError(
                        f"Driver did not connect to instrument {instrument_id}."
                    )
            except Exception:
                driver.disconnect()
                raise

            cls._connections[instrument_id] = driver
            return driver

    @classmethod
    @contextmanager
    def exclusive(
        cls,
        instrument: "Instrument",
    ) -> Iterator[BaseInstrumentDriver]:
        """Yield an active driver while exclusively locking its instrument."""
        instrument_id = cls._instrument_id(instrument)

        with cls._lock_for(instrument):
            driver = cls._connections.get(instrument_id)
            if driver is None or not driver.connected:
                cls._connections.pop(instrument_id, None)
                raise ConnectionError("Instrument is not connected.")
            yield driver

    @classmethod
    @contextmanager
    def session(
        cls,
        instrument: "Instrument",
    ) -> Iterator[BaseInstrumentDriver]:
        """Yield a locked connection and close it if this call opened it."""
        instrument_id = cls._instrument_id(instrument)

        with cls._lock_for(instrument):
            existing = cls._connections.get(instrument_id)
            already_connected = existing is not None and existing.connected
            driver = existing if already_connected else cls.connect(instrument)

            try:
                yield driver
            finally:
                if not already_connected:
                    cls._disconnect_locked(instrument_id)

    @classmethod
    def _disconnect_locked(cls, instrument_id: int) -> None:
        """Disconnect an instrument while its caller holds the lock."""
        driver = cls._connections.pop(instrument_id, None)
        if driver is not None:
            driver.disconnect()

    @classmethod
    def disconnect(cls, instrument: "Instrument") -> None:
        """Disconnect and remove the cached driver for an instrument."""
        instrument_id = cls._instrument_id(instrument)
        with cls._lock_for(instrument):
            cls._disconnect_locked(instrument_id)

    @classmethod
    def get(cls, instrument: "Instrument") -> BaseInstrumentDriver | None:
        """Return an active driver without opening a connection."""
        instrument_id = cls._instrument_id(instrument)
        with cls._lock_for(instrument):
            driver = cls._connections.get(instrument_id)
            if driver is not None and not driver.connected:
                cls._connections.pop(instrument_id, None)
                return None
            return driver

    @classmethod
    def is_connected(cls, instrument: "Instrument") -> bool:
        """Return whether the process has an active instrument connection."""
        return cls.get(instrument) is not None

    @classmethod
    def connected_ids(cls) -> frozenset[int]:
        """Return identifiers with active process-local connections."""
        active_ids = set()
        for instrument_id, driver in tuple(cls._connections.items()):
            if driver.connected:
                active_ids.add(instrument_id)
        return frozenset(active_ids)

    @classmethod
    def disconnect_all(cls) -> None:
        """Disconnect every active driver managed by this process."""
        for instrument_id in tuple(cls._connections):
            with cls._locks_guard:
                lock = cls._instrument_locks.setdefault(instrument_id, RLock())
            with lock:
                cls._disconnect_locked(instrument_id)
