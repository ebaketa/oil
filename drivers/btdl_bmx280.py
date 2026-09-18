"""Driver for the Baketa BTDL-BMx280 environmental instrument."""

import math

from .base import MeasurementCapability, MeasurementResult
from .btdl_ntc import BTDLNTCDriver
from .exceptions import CommunicationError, MeasurementError


class BTDLBMx280Driver(BTDLNTCDriver):
    """Read BMP280 or BME280 sensors on the two fixed I2C channels."""

    CAPABILITIES = {
        "environment": MeasurementCapability(
            label="Selected environmental values",
            unit="",
        ),
        "temperatures": MeasurementCapability(
            label="Both temperatures (channels 1 + 2)",
            unit="°C",
        ),
        "temperature_1": MeasurementCapability(
            label="Temperature channel 1 (0x76)",
            unit="°C",
        ),
        "pressure_1": MeasurementCapability(
            label="Pressure channel 1 (0x76)",
            unit="hPa",
        ),
        "humidity_1": MeasurementCapability(
            label="Humidity channel 1 (0x76)",
            unit="%RH",
        ),
        "temperature_2": MeasurementCapability(
            label="Temperature channel 2 (0x77)",
            unit="°C",
        ),
        "pressure_2": MeasurementCapability(
            label="Pressure channel 2 (0x77)",
            unit="hPa",
        ),
        "humidity_2": MeasurementCapability(
            label="Humidity channel 2 (0x77)",
            unit="%RH",
        ),
    }
    SENSOR_TYPES = {"NONE", "BMP280", "BME280"}
    DEVICE_NAME = "BTDL-BMx280"
    CHANNEL_ADDRESSES = {1: "0x76", 2: "0x77"}
    QUANTITIES = {
        "temperature": ("TEMP", "Temperature", "°C"),
        "pressure": ("PRES", "Pressure", "hPa"),
        "humidity": ("HUM", "Humidity", "%RH"),
    }

    def _measure_quantity(
        self,
        quantity: str,
        channel: int,
        parameter: str,
        unit: str,
    ) -> MeasurementResult:
        self._validate_channel(channel)
        response = self.query(f"MEAS:{quantity}? {channel}")
        try:
            value = float(response)
        except ValueError as exc:
            raise MeasurementError(
                f"The BTDL-BMx280 returned an invalid {parameter.lower()}: "
                f"{response!r}.",
            ) from exc
        if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
            error = self.query("SYST:ERR:NEXT?")
            raise MeasurementError(
                f"The BTDL-BMx280 {parameter.lower()} reading failed: "
                f"{error}.",
            )
        return MeasurementResult(parameter=parameter, value=value, unit=unit)

    @staticmethod
    def _validate_channel(channel: int) -> None:
        if channel not in (1, 2):
            raise ValueError("BMx280 channel must be 1 or 2.")

    def measure_temperature_1(self) -> MeasurementResult:
        return self._measure_quantity("TEMP", 1, "Temperature", "°C")

    def measure_pressure_1(self) -> MeasurementResult:
        return self._measure_quantity("PRES", 1, "Pressure", "hPa")

    def measure_humidity_1(self) -> MeasurementResult:
        return self._measure_quantity("HUM", 1, "Humidity", "%RH")

    def measure_temperature_2(self) -> MeasurementResult:
        return self._measure_quantity("TEMP", 2, "Temperature", "°C")

    def measure_pressure_2(self) -> MeasurementResult:
        return self._measure_quantity("PRES", 2, "Pressure", "hPa")

    def measure_humidity_2(self) -> MeasurementResult:
        return self._measure_quantity("HUM", 2, "Humidity", "%RH")

    def measure_temperatures(self) -> tuple[MeasurementResult, MeasurementResult]:
        """Measure both fixed BMx280 channels in one query."""
        response = self.query("MEAS:TEMP?")
        values = response.split(",")
        if len(values) != 2:
            raise MeasurementError(
                f"The BTDL-BMx280 returned invalid temperatures: {response!r}.",
            )
        results = []
        for channel, raw in enumerate(values, start=1):
            try:
                value = float(raw)
            except ValueError as exc:
                raise MeasurementError(
                    f"The BTDL-BMx280 returned an invalid temperature: "
                    f"{raw!r}.",
                ) from exc
            if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
                error = self.query("SYST:ERR:NEXT?")
                raise MeasurementError(
                    f"The BTDL-BMx280 channel {channel} temperature "
                    f"reading failed: {error}.",
                )
            results.append(
                MeasurementResult(
                    f"Temperature channel {channel}",
                    value,
                    "°C",
                ),
            )
        return tuple(results)

    def sensor_inventory(self) -> tuple[dict[str, object], ...]:
        """Return detected sensor types and their measurable quantities."""
        sensors = []
        sensor_types = getattr(self, "_sensor_types", {})
        self._sensor_types = sensor_types
        for channel in (1, 2):
            sensor_type = self.sensor_type(channel)
            sensor_types[channel] = sensor_type
            if sensor_type == "NONE":
                continue
            quantities = ["temperature", "pressure"]
            if sensor_type == "BME280":
                quantities.append("humidity")
            sensors.append(
                {
                    "channel": channel,
                    "address": self.CHANNEL_ADDRESSES[channel],
                    "type": sensor_type,
                    "quantities": tuple(quantities),
                },
            )
        return tuple(sensors)

    def measure_environment(
        self,
        measurements: list[str] | tuple[str, ...] | None = None,
    ) -> tuple[MeasurementResult, ...]:
        """Measure the selected ``quantity_channel`` values."""
        if not measurements:
            raise ValueError("Select at least one BMx280 measurement.")
        # The firmware's common SCPI command READ? performs one acquisition
        # and returns all channels in one response.
        response = self.query("READ?")
        fields = response.split(",")
        if len(fields) != 8:
            raise MeasurementError(
                f"The BTDL-BMx280 returned invalid environmental data: "
                f"{response!r}.",
            )
        values = []
        try:
            values = [float(field) for field in fields]
        except ValueError as exc:
            raise MeasurementError(
                f"The BTDL-BMx280 returned invalid environmental data: "
                f"{response!r}.",
            ) from exc
        results = []
        seen = set()
        for measurement in measurements:
            if measurement in seen:
                continue
            seen.add(measurement)
            try:
                quantity, raw_channel = measurement.rsplit("_", 1)
                channel = int(raw_channel)
                command, parameter, unit = self.QUANTITIES[quantity]
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"Unsupported BMx280 measurement: {measurement!r}.",
                ) from exc
            self._validate_channel(channel)
            offset = (channel - 1) * 4
            quantity_offset = {"temperature": 0, "humidity": 1, "pressure": 2}[quantity]
            value = values[offset + quantity_offset]
            if not math.isfinite(value) or value >= self.ERROR_SENTINEL:
                raise MeasurementError(
                    f"The BTDL-BMx280 {parameter.lower()} channel {channel} "
                    "reading failed.",
                )
            results.append(
                MeasurementResult(
                    f"{parameter} channel {channel}",
                    value,
                    unit,
                ),
            )
        return tuple(results)

    def sensor_count(self) -> int:
        """Return the number of detected BMP280/BME280 sensors."""
        response = self.query("SYST:SENS:COUNT?")
        try:
            count = int(response)
        except ValueError as exc:
            raise CommunicationError(
                f"The BTDL-BMx280 returned an invalid sensor count: "
                f"{response!r}.",
            ) from exc
        if count not in (0, 1, 2):
            raise CommunicationError(
                f"The BTDL-BMx280 returned an invalid sensor count: {count}.",
            )
        return count

    def scan_sensors(self) -> int:
        """Rescan both fixed I2C addresses and return the detected count."""
        self.execute("SYST:SENS:SCAN")
        return self.sensor_count()

    def sensor_address(self, channel: int) -> str:
        """Return the fixed I2C address reported for one channel."""
        self._validate_channel(channel)
        response = self.query(f"SYST:SENS:ADDR? {channel}").strip('"')
        expected = self.CHANNEL_ADDRESSES[channel]
        if response.lower() != expected:
            raise CommunicationError(
                f"The BTDL-BMx280 returned an invalid I2C address: "
                f"{response!r}.",
            )
        return expected

    def sensor_type(self, channel: int) -> str:
        """Return NONE, BMP280, or BME280 for one fixed channel."""
        self._validate_channel(channel)
        response = self.query(f"SYST:SENS:TYPE? {channel}").strip().upper()
        if response not in self.SENSOR_TYPES:
            raise CommunicationError(
                f"The BTDL-BMx280 returned an invalid sensor type: "
                f"{response!r}.",
            )
        return response
