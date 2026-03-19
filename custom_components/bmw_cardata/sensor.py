"""Sensor platform for BMW CarData integration."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfLength, UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CHARGING_STATUS_ICONS,
    COMBUSTION_SENSOR_KEYS,
    ELECTRIC_ENUM_SENSOR_KEYS,
    ELECTRIC_SENSOR_KEYS,
    KNOWN_ENUM_SENSORS,
    KNOWN_SENSORS,
)
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity

_LOGGER = logging.getLogger(__name__)

# Map device class strings to actual classes
DEVICE_CLASS_MAP = {
    "distance": SensorDeviceClass.DISTANCE,
    "pressure": SensorDeviceClass.PRESSURE,
    "battery": SensorDeviceClass.BATTERY,
    "energy": SensorDeviceClass.ENERGY,
}

# Map unit strings to HA unit constants
UNIT_MAP = {
    "km": UnitOfLength.KILOMETERS,
    "kPa": UnitOfPressure.KPA,
    "%": PERCENTAGE,
    "kWh": UnitOfEnergy.KILO_WATT_HOUR,
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
        # Skip electric-only sensors for conventional vehicles
        if not coordinator.is_electric and key in ELECTRIC_SENSOR_KEYS:
            continue

        # Skip combustion-only sensors for BEV vehicles
        if coordinator.is_bev and key in COMBUSTION_SENSOR_KEYS:
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

    # Create enum sensors
    enum_entities: list[BMWCarDataEnumSensor] = []

    # State-dependent icon mappings for enum sensors
    state_icon_map: dict[str, dict[str, str]] = {
        "vehicle.drivetrain.electricEngine.charging.status": CHARGING_STATUS_ICONS,
    }

    for key, (name, options, icon, translation_key) in KNOWN_ENUM_SENSORS.items():
        if not coordinator.is_electric and key in ELECTRIC_ENUM_SENSOR_KEYS:
            continue

        enum_entities.append(
            BMWCarDataEnumSensor(
                coordinator=coordinator,
                key=key,
                name=name,
                options=options,
                icon=icon,
                translation_key=translation_key,
                state_icons=state_icon_map.get(key),
            )
        )

    async_add_entities(enum_entities)


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

        # Energy delta is a total value, not a point-in-time measurement
        if device_class == "energy":
            self._attr_state_class = SensorStateClass.TOTAL

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


class BMWCarDataEnumSensor(BMWCarDataEntity, SensorEntity):
    """Representation of a BMW CarData enum sensor."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(
        self,
        coordinator: BMWCarDataCoordinator,
        key: str,
        name: str,
        options: list[str],
        icon: str | None,
        translation_key: str,
        state_icons: dict[str, str] | None = None,
    ) -> None:
        """Initialize the enum sensor."""
        super().__init__(coordinator, key, name)
        self._attr_options = options
        self._attr_translation_key = translation_key
        self._state_icons = state_icons
        self._default_icon = icon
        if icon and not state_icons:
            self._attr_icon = icon

    @property
    def icon(self) -> str | None:
        """Return a dynamic icon based on the current state."""
        if self._state_icons and self.native_value:
            return self._state_icons.get(self.native_value, self._default_icon)
        return self._default_icon

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        self._last_value = state

    @property
    def native_value(self) -> str | None:
        """Return the sensor value as a lowercase string."""
        value = self._last_value
        if value is None:
            return None
        result = str(value).lower()
        if result not in self._attr_options:
            _LOGGER.warning(
                "Unexpected value '%s' for %s — report to add it to const.py",
                result,
                self._key,
            )
            return None
        return result


