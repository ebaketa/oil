"""Linux USBTMC transport for newline-delimited SCPI instruments."""

from collections.abc import Callable
from typing import BinaryIO

from drivers.exceptions import CommunicationError

from .base import InstrumentTransport


class USBTMCTransport(InstrumentTransport):
    """Transfer SCPI messages through a Linux USBTMC device node."""

    def __init__(
        self,
        device_path: str,
        *,
        read_size: int = 400,
        open_device: Callable[..., BinaryIO] = open,
    ) -> None:
        """Store USBTMC settings without opening the device."""
        self.device_path = device_path
        self.read_size = read_size
        self._open_device = open_device
        self.device: BinaryIO | None = None

    @property
    def is_open(self) -> bool:
        """Return whether the USBTMC device is open."""
        return bool(self.device is not None and not self.device.closed)

    def open(self) -> None:
        """Open the USBTMC device in unbuffered binary mode."""
        if self.is_open:
            return
        try:
            self.device = self._open_device(
                self.device_path,
                "rb+",
                buffering=0,
            )
        except OSError as exc:
            self.device = None
            raise CommunicationError(
                f"Could not open USBTMC device {self.device_path}."
            ) from exc

    def close(self) -> None:
        """Close the USBTMC device."""
        device, self.device = self.device, None
        if device is not None and not device.closed:
            try:
                device.close()
            except OSError as exc:
                raise CommunicationError(
                    f"Could not close USBTMC device {self.device_path}."
                ) from exc

    def write(self, command: str) -> None:
        """Write one newline-terminated SCPI command."""
        if not self.is_open:
            raise CommunicationError("The USBTMC transport is not open.")
        try:
            self.device.write(f"{command.rstrip()}\n".encode())
        except OSError as exc:
            raise CommunicationError(
                f"Could not write to USBTMC device {self.device_path}."
            ) from exc

    def read(self, timeout: float | None = None) -> str:
        """Read and decode one USBTMC response."""
        if not self.is_open:
            raise CommunicationError("The USBTMC transport is not open.")
        try:
            response = self.device.read(self.read_size)
        except OSError as exc:
            raise CommunicationError(
                f"Could not read from USBTMC device {self.device_path}."
            ) from exc

        if not response:
            raise CommunicationError("The USBTMC device returned an empty response.")
        return response.decode("utf-8", errors="replace").strip()
