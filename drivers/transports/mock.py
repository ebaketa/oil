"""In-memory transport for driver tests and demonstrations."""

from collections.abc import Mapping

from drivers.exceptions import CommunicationError

from .base import InstrumentTransport


class MockTransport(InstrumentTransport):
    """Record SCPI commands and return configured responses in memory."""

    def __init__(self, responses: Mapping[str, str] | None = None) -> None:
        """Create a closed transport with deterministic query responses."""
        self.responses = dict(responses or {})
        self.command_history: list[str] = []
        self._open = False
        self._pending_response: str | None = None

    @property
    def is_open(self) -> bool:
        """Return whether the simulated channel is open."""
        return self._open

    def open(self) -> None:
        """Open the simulated channel."""
        self._open = True

    def close(self) -> None:
        """Close the simulated channel."""
        self._open = False
        self._pending_response = None

    def write(self, command: str) -> None:
        """Record a command and stage its configured response."""
        if not self.is_open:
            raise CommunicationError("The mock transport is not open.")
        normalized = command.rstrip()
        self.command_history.append(normalized)
        self._pending_response = self.responses.get(normalized)

    def read(self, timeout: float | None = None) -> str:
        """Return the response staged by the most recent command."""
        if not self.is_open:
            raise CommunicationError("The mock transport is not open.")
        response, self._pending_response = self._pending_response, None
        if response is None:
            raise CommunicationError("The mock transport has no response.")
        return response
