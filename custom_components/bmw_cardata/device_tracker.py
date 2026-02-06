"""Device tracker platform for BMW CarData integration."""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    LOCATION_ALTITUDE_KEY,
    LOCATION_LATITUDE_KEY,
    LOCATION_LONGITUDE_KEY,
)
from .coordinator import BMWCarDataCoordinator
from .entity import BMWCarDataEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up BMW CarData device tracker."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data

    async_add_entities([BMWCarDataDeviceTracker(coordinator)])


class BMWCarDataDeviceTracker(BMWCarDataEntity, TrackerEntity):
    """BMW CarData device tracker for vehicle location.
    
    This entity enables zone-based automations (enter/leave events)
    and shows the vehicle on the Home Assistant map.
    """

    _attr_icon = "mdi:car"

    def __init__(self, coordinator: BMWCarDataCoordinator) -> None:
        """Initialize the device tracker."""
        super().__init__(
            coordinator,
            key="location",
            name="Location",
        )
        # Override unique_id to be simpler for the tracker
        self._attr_unique_id = f"{coordinator.vin}_device_tracker"
        # Cache location values
        self._last_latitude: float | None = None
        self._last_longitude: float | None = None
        self._last_altitude: float | None = None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if MQTT is connected and we've received location data
        return self.coordinator.is_mqtt_connected and self._has_received_data

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        data = self.coordinator.data.get(LOCATION_LATITUDE_KEY)
        if data is not None:
            value = data.get("value") if isinstance(data, dict) else data
            if isinstance(value, (int, float)):
                self._last_latitude = float(value)
                self._has_received_data = True
        return self._last_latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        data = self.coordinator.data.get(LOCATION_LONGITUDE_KEY)
        if data is not None:
            value = data.get("value") if isinstance(data, dict) else data
            if isinstance(value, (int, float)):
                self._last_longitude = float(value)
                self._has_received_data = True
        return self._last_longitude

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        """Return extra state attributes."""
        attrs: dict[str, float | str | None] = {}
        
        # Add altitude if available
        altitude_data = self.coordinator.data.get(LOCATION_ALTITUDE_KEY)
        if altitude_data is not None:
            value = altitude_data.get("value") if isinstance(altitude_data, dict) else altitude_data
            if isinstance(value, (int, float)):
                self._last_altitude = float(value)
        
        if self._last_altitude is not None:
            attrs["altitude"] = self._last_altitude
        
        # Add timestamp
        lat_data = self.coordinator.data.get(LOCATION_LATITUDE_KEY)
        if isinstance(lat_data, dict) and "timestamp" in lat_data:
            attrs["last_changed"] = lat_data["timestamp"]
        
        return attrs
