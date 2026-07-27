"""Shared contract for instrument communication transports."""

from abc import ABC, abstractmethod


class InstrumentTransport(ABC):
    """Transfer SCPI messages without knowing instrument functions."""

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """Return whether the underlying communication channel is open."""

    @abstractmethod
    def open(self) -> None:
        """Open the underlying communication channel."""

    @abstractmethod
    def close(self) -> None:
        """Close the underlying communication channel."""

    @abstractmethod
    def write(self, command: str) -> None:
        """Write one SCPI command."""

    @abstractmethod
    def read(self, timeout: float | None = None) -> str:
        """Read one decoded SCPI response."""

    def query(self, command: str, timeout: float | None = None) -> str:
        """Write one command and return its response."""
        self.write(command)
        return self.read(timeout=timeout)

    def reset_input_buffer(self) -> None:
        """Discard unread input when the transport supports it."""
