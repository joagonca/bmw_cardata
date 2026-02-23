"""Sensor platform for BMW CarData integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DRIVETRAIN_CONV,
    ELECTRIC_SENSOR_KEYS,
    KNOWN_SENSORS,
)
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity

# Keys for Battery calculation (subset of ELECTRIC_SENSOR_KEYS)
_BATTERY_ELECTRIC_RANGE_KEY = "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange"
_BATTERY_TARGET_RANGE_KEY = "vehicle.powertrain.electric.range.target"

# Map device class strings to actual classes
DEVICE_CLASS_MAP = {
    "distance": SensorDeviceClass.DISTANCE,
    "pressure": SensorDeviceClass.PRESSURE,
}

# Map unit strings to HA unit constants
UNIT_MAP = {
    "km": UnitOfLength.KILOMETERS,
    "kPa": UnitOfPressure.KPA,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData sensors."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data
    drive_train = coordinator.vehicle_info.get("drive_train")
    is_electric = drive_train != DRIVETRAIN_CONV

    # Create entities for all known sensors
    entities: list[BMWCarDataSensor] = []

    for key, (name, unit, device_class, icon) in KNOWN_SENSORS.items():
        # Skip electric-only sensors for conventional vehicles
        if not is_electric and key in ELECTRIC_SENSOR_KEYS:
            continue

        entities.append(
            BMWCarDataSensor(
                coordinator=coordinator,
                key=key,
                name=name,
                unit=unit,
                device_class=device_class,
                icon=icon,
            )
        )

    async_add_entities(entities)

    # Add calculated Battery sensor only for electric vehicles
    if is_electric:
        async_add_entities([BMWBatterySensor(coordinator)])


class BMWCarDataSensor(BMWCarDataEntity, SensorEntity):
    """Representation of a BMW CarData sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: BMWCarDataCoordinator,
        key: str,
        name: str,
        unit: str | None,
        device_class: str | None,
        icon: str | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, key, name)

        # Set unit
        if unit:
            self._attr_native_unit_of_measurement = UNIT_MAP.get(unit, unit)

        # Set device class
        if device_class:
            self._attr_device_class = DEVICE_CLASS_MAP.get(device_class)

        # Set icon
        if icon:
            self._attr_icon = icon

        # Odometer should be total_increasing
        if "travelledDistance" in key:
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        try:
            if "." in state:
                self._last_value = float(state)
            else:
                self._last_value = int(state)
        except (ValueError, TypeError):
            self._last_value = None

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        value = self._last_value
        if value is None:
            return None

        # Ensure numeric value
        if isinstance(value, (int, float)):
            return value

        # Try to parse as number
        try:
            if "." in str(value):
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            return None


class BMWBatterySensor(BMWCarDataEntity, SensorEntity):
    """Calculated Battery sensor (Electric Range / Target Electric Range * 100)."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:battery"

    def __init__(self, coordinator: BMWCarDataCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, key="calculated_battery", name="Battery")
        # Per-key caches so a partial MQTT update (only one key present) can
        # still produce a value using the last known reading for the other key.
        self._last_electric_range: float | None = None
        self._last_target_range: float | None = None

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        try:
            self._last_value = float(state)
        except (ValueError, TypeError):
            self._last_value = None

    def _process_coordinator_data(self) -> None:
        """Compute battery percentage, falling back to cached source values if one key is absent."""
        def _extract(key: str) -> float | None:
            data = self.coordinator.data.get(key)
            if data is None:
                return None
            value = data.get("value") if isinstance(data, dict) else data
            try:
                return float(value)
            except (ValueError, TypeError):
                return None

        electric_range = _extract(_BATTERY_ELECTRIC_RANGE_KEY)
        target_range = _extract(_BATTERY_TARGET_RANGE_KEY)

        # Update per-key caches whenever fresh data arrives
        if electric_range is not None:
            self._last_electric_range = electric_range
        if target_range is not None:
            self._last_target_range = target_range

        # Use cached value for whichever source key is absent in this update
        effective_electric = electric_range if electric_range is not None else self._last_electric_range
        effective_target = target_range if target_range is not None else self._last_target_range

        if effective_electric is None or effective_target is None or effective_target == 0:
            return

        self._last_value = (effective_electric / effective_target) * 100
        self._has_received_data = True

    @property
    def native_value(self) -> float | None:
        """Return the calculated battery percentage."""
        return self._last_value


