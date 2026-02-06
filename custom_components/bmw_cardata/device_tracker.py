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

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if we have at least latitude and longitude
        return (
            LOCATION_LATITUDE_KEY in self.coordinator.data
            and LOCATION_LONGITUDE_KEY in self.coordinator.data
        )

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        data = self.coordinator.data.get(LOCATION_LATITUDE_KEY)
        if data is None:
            return None
        value = data.get("value") if isinstance(data, dict) else data
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        data = self.coordinator.data.get(LOCATION_LONGITUDE_KEY)
        if data is None:
            return None
        value = data.get("value") if isinstance(data, dict) else data
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        """Return extra state attributes."""
        attrs = {}
        
        # Add altitude if available
        altitude_data = self.coordinator.data.get(LOCATION_ALTITUDE_KEY)
        if altitude_data is not None:
            value = altitude_data.get("value") if isinstance(altitude_data, dict) else altitude_data
            if isinstance(value, (int, float)):
                attrs["altitude"] = float(value)
        
        return attrs
