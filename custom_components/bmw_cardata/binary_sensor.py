"""Binary sensor platform for BMW CarData integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DRIVETRAIN_ELECTRIC,
    KNOWN_BINARY_SENSORS,
)
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity


def _to_bool(value: object) -> bool | None:
    """Coerce a telemetry value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.lower()
        if low in ("true", "on", "yes", "1", "connected"):
            return True
        if low in ("false", "off", "no", "0", "disconnected"):
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData binary sensors."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data

    # Create entities for all known binary sensors
    entities: list[BMWCarDataBinarySensor] = []

    for key, (name, device_class, icon, drivetrain) in KNOWN_BINARY_SENSORS.items():
        # Skip electric-only sensors for conventional vehicles
        if not coordinator.is_electric and drivetrain == DRIVETRAIN_ELECTRIC:
            continue

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
        self._last_value = _to_bool(state)

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        value = self._last_value
        if value is None:
            return None

        return _to_bool(value)


