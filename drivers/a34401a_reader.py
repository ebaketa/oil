"""Original proven Agilent 34401A serial reader."""

import time

import serial
from serial.tools import list_ports


class A34401AReader:
    """Preserve the working lifecycle of the original standalone reader."""

    def __init__(self) -> None:
        """Discover, open, and configure the known Agilent FTDI interface."""
        self.a34401a_serial = "A9Z22QXP"
        self.a34401a_port = None

        for port in list_ports.comports():
            if port.serial_number == self.a34401a_serial:
                self.a34401a_port = port.device

        if self.a34401a_port is None:
            raise serial.SerialException(
                f"FTDI {self.a34401a_serial} was not found."
            )

        self.ser = serial.Serial(
            port=self.a34401a_port,
            baudrate=9600,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
            timeout=1,
        )
        time.sleep(0.5)
        self.ser.reset_input_buffer()
        self.ser.write("SYSTem:REMote\n".encode())
        time.sleep(0.5)
        self.ser.write("*CLS\n".encode())
        time.sleep(0.5)
        self.ser.write("CONF:VOLT:DC\n".encode())
        time.sleep(0.1)
        self.ser.write("VOLT:DC:RANG:AUTO ON\n".encode())
        time.sleep(0.1)

    def get_data(self) -> str | None:
        """Trigger and read one DC voltage value."""
        if self.ser and self.ser.is_open:
            self.ser.write("READ?\n".encode())
            deadline = time.monotonic() + 10
            while self.ser.in_waiting <= 0 and time.monotonic() < deadline:
                time.sleep(0.1)
            if self.ser.in_waiting > 0:
                return self.ser.readline().decode(
                    "utf-8",
                    errors="replace",
                ).strip()
        return None

    def close(self) -> None:
        """Restore display and local control before closing."""
        if self.ser and self.ser.is_open:
            self.ser.write("SYSTem:LOCal\n".encode())
            self.ser.close()
