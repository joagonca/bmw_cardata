"""Data update coordinator for BMW CarData integration."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_MQTT_DEBUG,
    CONF_MQTT_BUFFER_SIZE,
    CONF_CLIENT_ID,
    CONF_VIN,
    DIAG_MAX_MESSAGES,
    DOMAIN,
    DRIVETRAIN_BEV,
    DRIVETRAIN_CONV,
    EVENT_MQTT_DEBUG,
    TOKEN_ACCESS,
)
from .mqtt_manager import BMWMqttManager
from .token_manager import BMWTokenManager
from .utils import async_bmw_api_get, extract_telemetry_value

_LOGGER = logging.getLogger(__name__)


class BMWCarDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for BMW CarData that manages MQTT streaming and REST API calls."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        token_manager: BMWTokenManager,
        mqtt_manager: BMWMqttManager,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # No polling, we use MQTT push
        )
        self.config_entry = config_entry
        self._vin: str = config_entry.data[CONF_VIN]
        self._client_id: str = config_entry.data[CONF_CLIENT_ID]
        self._token_manager = token_manager
        self._mqtt_manager = mqtt_manager

        # Initialize data store
        self.data: dict[str, Any] = {}

        # Ring buffer for diagnostics (last N MQTT messages)
        buffer_size = config_entry.options.get(CONF_MQTT_BUFFER_SIZE, DIAG_MAX_MESSAGES)
        self.mqtt_message_buffer: deque[dict[str, Any]] = deque(
            maxlen=buffer_size
        )

    @property
    def vin(self) -> str:
        """Return the VIN."""
        return self._vin

    @property
    def tokens(self) -> dict[str, Any]:
        """Return current tokens from token manager."""
        return self._token_manager.tokens

    @property
    def vehicle_info(self) -> dict[str, Any]:
        """Return vehicle info."""
        return self.config_entry.data.get("vehicle_info", {})

    @property
    def is_electric(self) -> bool:
        """Return True if vehicle is electric (PHEV or BEV)."""
        return self.vehicle_info.get("drive_train") != DRIVETRAIN_CONV

    @property
    def is_bev(self) -> bool:
        """Return True if vehicle is a battery electric vehicle."""
        return self.vehicle_info.get("drive_train") == DRIVETRAIN_BEV

    async def async_get_access_token(self) -> str | None:
        """Get a valid access token, refreshing if necessary."""
        tokens = await self._token_manager.async_get_tokens()
        return tokens.get(TOKEN_ACCESS)

    async def _async_fetch_initial_data(self) -> dict[str, Any]:
        """Fetch initial data via REST API."""
        access_token = await self.async_get_access_token()
        if not access_token:
            _LOGGER.warning("[%s] No access token for initial data fetch", self._vin[-6:])
            return {}

        data: dict[str, Any] = {}

        try:
            basic_data = await async_bmw_api_get(
                self.hass, access_token,
                f"/customers/vehicles/{self._vin}/basicData",
            )
            data["basic_data"] = basic_data
            _LOGGER.debug("[%s] Fetched basic vehicle data", self._vin[-6:])

        except asyncio.TimeoutError:
            _LOGGER.warning("[%s] Timeout fetching initial data", self._vin[-6:])
        except Exception as err:
            _LOGGER.warning("[%s] Error fetching initial data: %s", self._vin[-6:], err)

        return data

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        # Fetch initial data
        initial_data = await self._async_fetch_initial_data()
        self.data.update(initial_data)

        # Register with shared MQTT manager
        self._mqtt_manager.register_vin(self._vin, self._handle_mqtt_message)
        
        # Start MQTT if not already running
        await self._mqtt_manager.async_start()

        return True

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        # Unregister from MQTT manager (manager handles connection lifecycle)
        self._mqtt_manager.unregister_vin(self._vin)

    def _handle_mqtt_message(self, payload: dict[str, Any]) -> None:
        """Handle MQTT message routed from the shared manager."""
        # Log summary
        data_keys = list(payload.get("data", {}).keys())
        _LOGGER.debug(
            "[%s] MQTT message: %d telemetry keys",
            self._vin[-6:],
            len(data_keys),
        )
        
        # Schedule processing on event loop (we might be called from callback)
        self.hass.async_create_task(self._async_process_mqtt_data(payload))

    async def _async_process_mqtt_data(self, payload: dict[str, Any]) -> None:
        """Process MQTT data and update entities."""
        updated = False

        # Fire debug event if enabled in options
        if self.config_entry.options.get(CONF_MQTT_DEBUG, False):
            self.hass.bus.async_fire(EVENT_MQTT_DEBUG, {
                "vin": self._vin,
                "topic": payload.get("topic", ""),
                "timestamp": payload.get("timestamp", ""),
                "payload": payload,
            })

        # Store in ring buffer for diagnostics
        self.mqtt_message_buffer.append({
            "timestamp": payload.get("timestamp", ""),
            "keys": list(payload.get("data", {}).keys()),
            "payload": payload,
        })

        # Data is nested inside 'data' key
        data_payload = payload.get("data", {})
        
        for key, value_obj in data_payload.items():
            actual_value, timestamp = extract_telemetry_value(value_obj)
            if timestamp is None:
                timestamp = datetime.now(tz=timezone.utc).isoformat()
            
            # Store the value in normalised format
            self.data[key] = {
                "value": actual_value,
                "timestamp": timestamp,
            }
            updated = True

        if updated:
            self.async_set_updated_data(self.data)

    @property
    def is_mqtt_connected(self) -> bool:
        """Return whether MQTT is connected."""
        return self._mqtt_manager.is_connected
