"""Driver for the Baketa BTDL-DS18B20 temperature instrument."""

import math
from decimal import Decimal, ROUND_HALF_UP

from .base import MeasurementCapability, MeasurementResult
from .btdl_ntc import BTDLNTCDriver
from .exceptions import CommunicationError, MeasurementError


class BTDLDS18B20Driver(BTDLNTCDriver):
    """Control DS1820/DS18S20 and DS18B20 sensors over BTDL SCPI."""

    CAPABILITIES = {
        "temperatures": MeasurementCapability(
            label="Both temperatures (DS1820 + DS18B20)",
            unit="°C",
        ),
        "temperature_ds1820": MeasurementCapability(
            label="Temperature DS1820/DS18S20",
            unit="°C",
        ),
        "temperature_ds18b20": MeasurementCapability(
            label="Temperature DS18B20",
            unit="°C",
        ),
    }
    DS18B20_RESOLUTIONS = (9, 10, 11, 12)
    DEVICE_NAME = "BTDL-DS18B20"

    def _temperature_result(
        self,
        command: str,
        parameter: str,
        step: Decimal,
    ) -> MeasurementResult:
        response = self.query(command)
        try:
            value = float(response)
        except ValueError as exc:
            raise MeasurementError(
                f"The BTDL-DS18B20 returned an invalid temperature: "
                f"{response!r}.",
            ) from exc
        if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
            error = self.query("SYST:ERR:NEXT?")
            raise MeasurementError(
                f"The BTDL-DS18B20 {parameter} reading failed: {error}.",
            )
        decimal_value = Decimal(str(value))
        if step == Decimal("0.5"):
            decimal_value = (
                (decimal_value * 2).quantize(
                    Decimal("1"),
                    rounding=ROUND_HALF_UP,
                ) / 2
            )
        else:
            decimal_value = decimal_value.quantize(
                step,
                rounding=ROUND_HALF_UP,
            )
        return MeasurementResult(
            parameter=parameter,
            value=float(decimal_value),
            unit="°C",
        )

    def measure_temperature_ds1820(self) -> MeasurementResult:
        """Measure the single DS1820 or DS18S20 sensor on the bus."""
        return self._temperature_result(
            "MEAS:TEMP? DS1820",
            "Temperature DS1820/DS18S20",
            Decimal("0.5"),
        )

    def measure_temperature_ds18b20(self) -> MeasurementResult:
        """Measure the single DS18B20 sensor on the bus."""
        return self._temperature_result(
            "MEAS:TEMP? DS18B20",
            "Temperature DS18B20",
            Decimal("0.1"),
        )

    def measure_temperatures(self) -> tuple[MeasurementResult, MeasurementResult]:
        """Measure DS1820/DS18S20 and DS18B20 in one shared conversion."""
        response = self.query("MEAS:TEMP?")
        values = response.split(",")
        if len(values) != 2:
            raise MeasurementError(
                f"The BTDL-DS18B20 returned invalid temperatures: "
                f"{response!r}.",
            )
        results = []
        for raw, parameter, step in (
            (values[0], "Temperature DS1820/DS18S20", Decimal("0.5")),
            (values[1], "Temperature DS18B20", Decimal("0.1")),
        ):
            try:
                value = float(raw)
            except ValueError as exc:
                raise MeasurementError(
                    f"The BTDL-DS18B20 returned an invalid temperature: "
                    f"{raw!r}.",
                ) from exc
            if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
                error = self.query("SYST:ERR:NEXT?")
                raise MeasurementError(
                    f"The BTDL-DS18B20 {parameter} reading failed: {error}.",
                )
            decimal_value = Decimal(str(value))
            if step == Decimal("0.5"):
                decimal_value = (
                    (decimal_value * 2).quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    ) / 2
                )
            else:
                decimal_value = decimal_value.quantize(
                    step,
                    rounding=ROUND_HALF_UP,
                )
            results.append(
                MeasurementResult(parameter, float(decimal_value), "°C"),
            )
        return tuple(results)

    def scan_sensors(self) -> int:
        """Rescan the OneWire bus and return the detected sensor count."""
        self.execute("SYST:SENS:SCAN")
        return self.sensor_count()

    def sensor_count(self) -> int:
        """Return the number of OneWire devices detected by the firmware."""
        response = self.query("SYST:SENS:COUNT?")
        try:
            count = int(response)
        except ValueError as exc:
            raise CommunicationError(
                f"The BTDL-DS18B20 returned an invalid sensor count: "
                f"{response!r}.",
            ) from exc
        if not 0 <= count <= 255:
            raise CommunicationError(
                f"The BTDL-DS18B20 returned an invalid sensor count: {count}.",
            )
        return count

    def sensor_address(self, channel: int) -> str:
        """Return one uppercase 16-character OneWire ROM identifier."""
        if not isinstance(channel, int) or isinstance(channel, bool) or channel < 1:
            raise ValueError("Sensor channel must be a positive integer.")
        response = self.query(f"SYST:SENS:ADDR? {channel}").strip('"').upper()
        if len(response) != 16 or any(
            character not in "0123456789ABCDEF" for character in response
        ):
            raise CommunicationError(
                f"The BTDL-DS18B20 returned an invalid ROM ID: {response!r}.",
            )
        return response

    def ds18b20_resolution(self) -> int:
        """Return the configured DS18B20 conversion resolution in bits."""
        response = self.query("CONF:TEMP:DS18B20?")
        try:
            bits = int(response)
        except ValueError as exc:
            raise CommunicationError(
                f"The BTDL-DS18B20 returned an invalid resolution: "
                f"{response!r}.",
            ) from exc
        if bits not in self.DS18B20_RESOLUTIONS:
            raise CommunicationError(
                f"The BTDL-DS18B20 returned an invalid resolution: {bits}.",
            )
        return bits

    def set_ds18b20_resolution(self, bits: int) -> int:
        """Set and verify volatile DS18B20 resolution from 9 through 12 bits."""
        if bits not in self.DS18B20_RESOLUTIONS:
            raise ValueError("DS18B20 resolution must be 9, 10, 11, or 12 bits.")
        self.execute(f"CONF:TEMP:DS18B20 {bits}")
        actual = self.ds18b20_resolution()
        if actual != bits:
            raise CommunicationError(
                "The BTDL-DS18B20 did not apply the requested resolution.",
            )
        return actual
