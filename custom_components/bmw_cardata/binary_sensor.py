"""Binary sensor platform for BMW CarData integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import KNOWN_BINARY_SENSORS
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity
from .utils import generate_entity_name_from_key

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData binary sensors."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data

    # Create entities for all known binary sensors
    entities: list[BMWCarDataBinarySensor] = []

    for key, (name, device_class, icon) in KNOWN_BINARY_SENSORS.items():
        entities.append(
            BMWCarDataBinarySensor(
                coordinator=coordinator,
                key=key,
                name=name,
                device_class=device_class,
                icon=icon,
            )
        )

    async_add_entities(entities)

    # Register callback for dynamically discovered binary sensors
    @callback
    def on_new_key(key: str, value: Any) -> None:
        """Handle newly discovered binary sensor keys."""
        # Only create binary sensors for boolean values
        if not isinstance(value, bool):
            return
        if key in KNOWN_BINARY_SENSORS:
            return

        _LOGGER.info(
            "[%s] Creating dynamic binary sensor: %s",
            coordinator.vin[-6:],
            key,
        )

        async_add_entities(
            [
                BMWCarDataBinarySensor(
                    coordinator=coordinator,
                    key=key,
                    name=generate_entity_name_from_key(key),
                    device_class=None,
                    icon="mdi:car-info",
                )
            ]
        )

    entry.async_on_unload(coordinator.register_new_key_callback(on_new_key))


class BMWCarDataBinarySensor(BMWCarDataEntity, BinarySensorEntity):
    """Representation of a BMW CarData binary sensor."""

    def __init__(
        self,
        coordinator: BMWCarDataCoordinator,
        key: str,
        name: str,
        device_class: str | None,
        icon: str | None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, key, name)

        # Set device class
        if device_class:
            self._attr_device_class = device_class

        # Set icon
        if icon:
            self._attr_icon = icon

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string."""
        self._last_value = state.lower() == "on"

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self._last_value
        if value is None:
            return None

        # Handle various boolean representations
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() in ("true", "on", "yes", "1")

        if isinstance(value, (int, float)):
            return bool(value)

        return None


