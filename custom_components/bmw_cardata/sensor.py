"""Sensor platform for BMW CarData integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfPressure
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KNOWN_SENSORS
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity
from .utils import generate_entity_name_from_key

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

    # Register callback for dynamically discovered sensors
    @callback
    def on_new_key(key: str, value: Any) -> None:
        """Handle newly discovered sensor keys."""
        # Only create sensors for numeric values (not booleans)
        if isinstance(value, bool):
            return
        if not isinstance(value, (int, float)):
            return
        if key in KNOWN_SENSORS:
            return

        _LOGGER.info(
            "[%s] Creating dynamic sensor: %s",
            coordinator.vin[-6:],
            key,
        )

        async_add_entities(
            [
                BMWCarDataSensor(
                    coordinator=coordinator,
                    key=key,
                    name=generate_entity_name_from_key(key),
                    unit=None,
                    device_class=None,
                    icon="mdi:car-info",
                )
            ]
        )

    entry.async_on_unload(coordinator.register_new_key_callback(on_new_key))


class BMWCarDataSensor(BMWCarDataEntity, SensorEntity):
    """Representation of a BMW CarData sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT

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

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        value = self._get_value()
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

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes."""
        timestamp = self._get_timestamp()
        if timestamp:
            return {"last_changed": timestamp}
        return None
