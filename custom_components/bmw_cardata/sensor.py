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

    def _get_value(self, key: str) -> float | None:
        """Get numeric value from coordinator data."""
        data = self.coordinator.data.get(key)
        if data is None:
            return None

        value = data.get("value") if isinstance(data, dict) else data
        if value is None:
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @property
    def native_value(self) -> float | None:
        """Return the calculated battery percentage."""
        electric_range = self._get_value(_BATTERY_ELECTRIC_RANGE_KEY)
        target_range = self._get_value(_BATTERY_TARGET_RANGE_KEY)

        if electric_range is None or target_range is None:
            return None

        if target_range == 0:
            return None

        return (electric_range / target_range) * 100


