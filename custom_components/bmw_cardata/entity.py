"""Base entity for BMW CarData integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BMWCarDataCoordinator


class BMWCarDataEntity(CoordinatorEntity[BMWCarDataCoordinator]):
    """Base class for BMW CarData entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BMWCarDataCoordinator,
        key: str,
        name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.vin}_{key}"
        # Cache the last known value to retain when key is not in update
        self._last_value = None
        self._last_timestamp: str | None = None
        self._has_received_data = False

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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if MQTT is connected and we've ever received data for this key
        return self.coordinator.is_mqtt_connected and self._has_received_data

    def _get_value(self):
        """Get the current value for this entity's key."""
        data = self.coordinator.data.get(self._key)
        if data is not None:
            # Update cached value
            if isinstance(data, dict) and "value" in data:
                self._last_value = data["value"]
                self._last_timestamp = data.get("timestamp")
            else:
                self._last_value = data
                self._last_timestamp = None
            self._has_received_data = True
        
        return self._last_value

    def _get_timestamp(self) -> str | None:
        """Get the timestamp of the last update for this key."""
        # Ensure we've pulled the latest data
        self._get_value()
        return self._last_timestamp
