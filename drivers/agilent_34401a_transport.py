"""OIL adapter around the proven standalone Agilent reader."""

from .a34401a_reader import A34401AReader

class Agilent34401ATransport:
    """Expose the original reader through the transport interface."""

    def __init__(
        self,
        port: str,
        usb_serial_number: str = "A9Z22QXP",
    ) -> None:
        """Open the original reader and expose its serial connection."""
        self.reader = A34401AReader()
        self.ser = self.reader.ser

    def get_data(self) -> str | None:
        """Trigger one reading and return it when available."""
        return self.reader.get_data()

    def close(self) -> None:
        """Restore the display and local control, then close the port."""
        self.reader.close()
