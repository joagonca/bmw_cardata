"""Base entity for BMW CarData integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BMWCarDataCoordinator


class BMWCarDataEntity(CoordinatorEntity[BMWCarDataCoordinator], RestoreEntity):
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

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        await super().async_added_to_hass()
        
        # Try to restore previous state
        if (last_state := await self.async_get_last_state()) is not None:
            # Restore the value based on entity type
            if last_state.state not in (None, "unknown", "unavailable"):
                self._restore_native_value(last_state.state)
                self._has_received_data = True
            
            # Restore timestamp from attributes
            if last_state.attributes:
                self._last_timestamp = last_state.attributes.get("last_changed")
        
        # Process any data already in coordinator
        self._process_coordinator_data()

    def _restore_native_value(self, state: str) -> None:
        """Restore the native value from state string. Override in subclasses."""
        self._last_value = state

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._process_coordinator_data()
        self.async_write_ha_state()

    def _process_coordinator_data(self) -> None:
        """Process and cache data from coordinator. Called once per update."""
        data = self.coordinator.data.get(self._key)
        if data is not None:
            if isinstance(data, dict) and "value" in data:
                self._last_value = data["value"]
                self._last_timestamp = data.get("timestamp")
            else:
                self._last_value = data
                self._last_timestamp = None
            self._has_received_data = True

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
        # Available if MQTT is connected or we have restored/cached data
        return self.coordinator.is_mqtt_connected or self._has_received_data
