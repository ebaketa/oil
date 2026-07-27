"""Serial/FTDI transport for newline-delimited SCPI instruments."""

import time
from collections.abc import Callable
from typing import Any

import serial

from drivers.exceptions import CommunicationError

from .base import InstrumentTransport


class SerialTransport(InstrumentTransport):
    """Transfer SCPI messages over a pyserial connection."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 1,
        response_timeout: float = 10,
        serial_factory: Callable[..., Any] | None = None,
    ) -> None:
        """Store serial settings without opening the device."""
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.response_timeout = response_timeout
        self._serial_factory = serial_factory
        self.connection: Any | None = None

    @property
    def is_open(self) -> bool:
        """Return whether the serial connection is open."""
        return bool(self.connection is not None and self.connection.is_open)

    def open(self) -> None:
        """Open the serial device using the 34401A-compatible 8N2 framing."""
        if self.is_open:
            return
        try:
            serial_factory = self._serial_factory or serial.Serial
            self.connection = serial_factory(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_TWO,
                timeout=self.timeout,
            )
        except (OSError, serial.SerialException) as exc:
            self.connection = None
            raise CommunicationError(
                f"Could not open serial device {self.port}."
            ) from exc

    def close(self) -> None:
        """Close the serial connection."""
        connection, self.connection = self.connection, None
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except (OSError, serial.SerialException) as exc:
                raise CommunicationError(
                    f"Could not close serial device {self.port}."
                ) from exc

    def write(self, command: str) -> None:
        """Write one newline-terminated SCPI command."""
        if not self.is_open:
            raise CommunicationError("The serial transport is not open.")
        try:
            self.connection.write(f"{command.rstrip()}\n".encode())
        except (OSError, serial.SerialException) as exc:
            raise CommunicationError(
                f"Could not write to serial device {self.port}."
            ) from exc

    def read(self, timeout: float | None = None) -> str:
        """Read one response, optionally polling for delayed data."""
        if not self.is_open:
            raise CommunicationError("The serial transport is not open.")

        try:
            if timeout is not None:
                deadline = time.monotonic() + timeout
                while (
                    self.connection.in_waiting <= 0
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.1)
                if self.connection.in_waiting <= 0:
                    raise CommunicationError("The serial response timed out.")
            response = self.connection.readline()
        except CommunicationError:
            raise
        except (OSError, serial.SerialException) as exc:
            raise CommunicationError(
                f"Could not read from serial device {self.port}."
            ) from exc

        if not response:
            raise CommunicationError("The serial response timed out.")
        return response.decode("utf-8", errors="replace").strip()

    def reset_input_buffer(self) -> None:
        """Discard unread serial input."""
        if not self.is_open:
            raise CommunicationError("The serial transport is not open.")
        try:
            self.connection.reset_input_buffer()
        except (OSError, serial.SerialException) as exc:
            raise CommunicationError(
                f"Could not reset serial device {self.port}."
            ) from exc
