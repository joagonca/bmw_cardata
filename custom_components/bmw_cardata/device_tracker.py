"""Device tracker platform for BMW CarData integration."""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
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

    async def async_added_to_hass(self) -> None:
        """Restore state when entity is added to hass."""
        await super().async_added_to_hass()

        # Try to restore previous state (for device_tracker, state is the zone name)
        if (last_state := await self.async_get_last_state()) is not None:
            # Restore coordinates from attributes
            if last_state.attributes:
                if "latitude" in last_state.attributes:
                    self._last_latitude = last_state.attributes.get("latitude")
                if "longitude" in last_state.attributes:
                    self._last_longitude = last_state.attributes.get("longitude")
                if "altitude" in last_state.attributes:
                    self._last_altitude = last_state.attributes.get("altitude")
                self._last_timestamp = last_state.attributes.get("last_changed")

                if self._last_latitude is not None and self._last_longitude is not None:
                    self._has_received_data = True

    def _process_coordinator_data(self) -> None:
        """Extract location values from coordinator data."""
        def _extract(key: str) -> float | None:
            data = self.coordinator.data.get(key)
            if data is None:
                return None
            value = data.get("value") if isinstance(data, dict) else data
            return float(value) if isinstance(value, (int, float)) else None

        lat = _extract(LOCATION_LATITUDE_KEY)
        lon = _extract(LOCATION_LONGITUDE_KEY)
        alt = _extract(LOCATION_ALTITUDE_KEY)

        if lat is not None:
            self._last_latitude = lat
        if lon is not None:
            self._last_longitude = lon
        if alt is not None:
            self._last_altitude = alt

        if self._last_latitude is not None and self._last_longitude is not None:
            self._has_received_data = True

        # Update timestamp from latitude key
        lat_data = self.coordinator.data.get(LOCATION_LATITUDE_KEY)
        if isinstance(lat_data, dict) and "timestamp" in lat_data:
            self._last_timestamp = lat_data["timestamp"]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # Available if MQTT is connected or we have restored/cached data
        return self.coordinator.is_mqtt_connected or self._has_received_data

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        return self._last_latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        return self._last_longitude

    @property
    def extra_state_attributes(self) -> dict[str, float | str | None]:
        """Return extra state attributes."""
        attrs: dict[str, float | str | None] = {}
        if self._last_altitude is not None:
            attrs["altitude"] = self._last_altitude
        if self._last_timestamp:
            attrs["last_changed"] = self._last_timestamp
        return attrs
