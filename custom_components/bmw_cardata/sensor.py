"""Sensor platform for BMW CarData integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import KNOWN_SENSORS, DOMAIN
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity

_LOGGER = logging.getLogger(__name__)

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

    # Create entities for all known sensors
    entities: list[BMWCarDataSensor] = []

    for key, (name, unit, device_class, icon) in KNOWN_SENSORS.items():
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

    # Add calculated Battery sensor
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


class BMWBatterySensor(CoordinatorEntity[BMWCarDataCoordinator], SensorEntity):
    """Calculated Battery sensor (Electric Range / Target Electric Range * 100)."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:battery"

    # Keys for calculation
    _electric_range_key = "vehicle.drivetrain.electricEngine.kombiRemainingElectricRange"
    _target_range_key = "vehicle.powertrain.electric.range.target"

    def __init__(self, coordinator: BMWCarDataCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.vin}_calculated_battery"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        vehicle_info = self.coordinator.vehicle_info
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.vin)},
            name=f"{vehicle_info.get('brand', 'BMW')} {vehicle_info.get('model', self.coordinator.vin[:8])}",
            manufacturer=vehicle_info.get("brand", "BMW"),
            model=vehicle_info.get("model"),
            sw_version=vehicle_info.get("series"),
        )

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
        electric_range = self._get_value(self._electric_range_key)
        target_range = self._get_value(self._target_range_key)

        if electric_range is None or target_range is None:
            return None

        if target_range == 0:
            return None

        return (electric_range / target_range) * 100

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.is_mqtt_connected or self.native_value is not None


