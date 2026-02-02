"""Data update coordinator for BMW CarData integration."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
import time
from datetime import datetime
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ALL_KNOWN_KEYS,
    API_BASE_URL,
    CONF_CLIENT_ID,
    CONF_TOKENS,
    CONF_VIN,
    DOMAIN,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_KEEPALIVE,
    MQTT_TOPIC_PATTERN,
    TOKEN_ACCESS,
    TOKEN_ENDPOINT,
    TOKEN_EXPIRES_AT,
    TOKEN_GCID,
    TOKEN_ID,
    TOKEN_REFRESH,
    TOKEN_REFRESH_BUFFER,
    TOKEN_REFRESH_EXPIRES_AT,
)

_LOGGER = logging.getLogger(__name__)


class BMWCarDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for BMW CarData that manages MQTT streaming and REST API calls."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
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

        self._mqtt_client: mqtt.Client | None = None
        self._mqtt_connected = False
        self._mqtt_lock = threading.Lock()

        # Track discovered keys for dynamic entity creation
        self._discovered_keys: set[str] = set()
        self._new_key_callbacks: list[Callable[[str, Any], None]] = []

        # Initialize data store
        self.data: dict[str, Any] = {}

    @property
    def vin(self) -> str:
        """Return the VIN."""
        return self._vin

    @property
    def tokens(self) -> dict[str, Any]:
        """Return current tokens from config entry."""
        return self.config_entry.data.get(CONF_TOKENS, {})

    @property
    def vehicle_info(self) -> dict[str, Any]:
        """Return vehicle info."""
        return self.config_entry.data.get("vehicle_info", {})

    def _needs_token_refresh(self) -> bool:
        """Check if access token needs refresh."""
        expires_at = self.tokens.get(TOKEN_EXPIRES_AT, 0)
        return time.time() >= (expires_at - TOKEN_REFRESH_BUFFER)

    def _is_refresh_token_valid(self) -> bool:
        """Check if refresh token is still valid."""
        refresh_expires_at = self.tokens.get(TOKEN_REFRESH_EXPIRES_AT, 0)
        return time.time() < refresh_expires_at

    async def _async_refresh_tokens(self) -> bool:
        """Refresh access tokens."""
        import asyncio
        import aiohttp

        if not self._is_refresh_token_valid():
            _LOGGER.error("Refresh token expired, re-authentication required")
            return False

        refresh_token = self.tokens.get(TOKEN_REFRESH)
        if not refresh_token:
            _LOGGER.error("No refresh token available")
            return False

        try:
            session = async_get_clientsession(self.hass)

            form_data = aiohttp.FormData()
            form_data.add_field("client_id", self._client_id)
            form_data.add_field("grant_type", "refresh_token")
            form_data.add_field("refresh_token", refresh_token)

            async with asyncio.timeout(30):
                async with session.post(
                    TOKEN_ENDPOINT,
                    data=form_data,
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        _LOGGER.error("Token refresh failed: %s", text)
                        return False

                    token_data = await response.json()

                    # Parse new tokens
                    new_tokens = self._parse_token_response(token_data)

                    # Update config entry with new tokens
                    new_data = {**self.config_entry.data, CONF_TOKENS: new_tokens}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=new_data
                    )

                    _LOGGER.debug("Tokens refreshed successfully")
                    return True

        except Exception as err:
            _LOGGER.exception("Error refreshing tokens: %s", err)
            return False

    def _parse_token_response(self, token_data: dict[str, Any]) -> dict[str, Any]:
        """Parse token response and extract relevant data."""
        # GCID is returned directly in the token response per BMW API spec
        # Fall back to existing GCID if not in refresh response
        gcid = token_data.get("gcid", self.tokens.get(TOKEN_GCID, ""))

        expires_in = token_data.get("expires_in", 3600)
        refresh_expires_in = token_data.get("refresh_expires_in", 1209600)

        return {
            TOKEN_ACCESS: token_data.get("access_token"),
            TOKEN_REFRESH: token_data.get("refresh_token", self.tokens.get(TOKEN_REFRESH)),
            TOKEN_ID: token_data.get("id_token"),
            TOKEN_GCID: gcid,
            TOKEN_EXPIRES_AT: int(time.time()) + expires_in,
            TOKEN_REFRESH_EXPIRES_AT: self.tokens.get(
                TOKEN_REFRESH_EXPIRES_AT, int(time.time()) + refresh_expires_in
            ),
        }

    async def async_get_access_token(self) -> str | None:
        """Get a valid access token, refreshing if necessary."""
        if self._needs_token_refresh():
            await self._async_refresh_tokens()
        return self.tokens.get(TOKEN_ACCESS)

    async def _async_fetch_initial_data(self) -> dict[str, Any]:
        """Fetch initial data via REST API."""
        import asyncio

        access_token = await self.async_get_access_token()
        if not access_token:
            return {}

        data: dict[str, Any] = {}

        try:
            session = async_get_clientsession(self.hass)
            async with asyncio.timeout(30):
                async with session.get(
                    f"{API_BASE_URL}/customers/vehicles/{self._vin}/basicData",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "x-version": "v1",
                    },
                ) as response:
                    if response.status == 200:
                        basic_data = await response.json()
                        data["basic_data"] = basic_data
                        _LOGGER.debug("Fetched basic data for %s", self._vin)

        except Exception as err:
            _LOGGER.warning("Error fetching initial data: %s", err)

        return data

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        # Fetch initial data
        initial_data = await self._async_fetch_initial_data()
        self.data.update(initial_data)

        # Start MQTT connection
        await self._async_start_mqtt()

        return True

    async def async_shutdown(self) -> None:
        """Shut down the coordinator."""
        await self._async_stop_mqtt()

    async def _async_start_mqtt(self) -> None:
        """Start MQTT connection."""
        # Ensure tokens are fresh
        if self._needs_token_refresh():
            await self._async_refresh_tokens()

        gcid = self.tokens.get(TOKEN_GCID)
        id_token = self.tokens.get(TOKEN_ID)

        if not gcid or not id_token:
            _LOGGER.error("Missing GCID or ID token for MQTT connection")
            return

        def _create_and_connect():
            """Create MQTT client and connect (runs in executor)."""
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"ha-bmw-cardata-{gcid[:8]}",
                protocol=mqtt.MQTTv311,
            )

            client.username_pw_set(gcid, id_token)

            client.tls_set(
                ca_certs=None,
                certfile=None,
                keyfile=None,
                cert_reqs=ssl.CERT_REQUIRED,
                tls_version=ssl.PROTOCOL_TLS_CLIENT,
            )

            client.on_connect = self._on_mqtt_connect
            client.on_disconnect = self._on_mqtt_disconnect
            client.on_message = self._on_mqtt_message

            client.connect(
                MQTT_BROKER_HOST,
                MQTT_BROKER_PORT,
                keepalive=MQTT_KEEPALIVE,
            )

            client.loop_start()
            return client

        try:
            self._mqtt_client = await self.hass.async_add_executor_job(
                _create_and_connect
            )
            _LOGGER.debug("MQTT client created for VIN %s", self._vin)
        except Exception as err:
            _LOGGER.error("Failed to create MQTT client: %s", err)

    async def _async_stop_mqtt(self) -> None:
        """Stop MQTT connection."""
        if self._mqtt_client:

            def _stop():
                with self._mqtt_lock:
                    if self._mqtt_client:
                        self._mqtt_client.loop_stop()
                        self._mqtt_client.disconnect()

            await self.hass.async_add_executor_job(_stop)
            self._mqtt_client = None
            self._mqtt_connected = False

    def _on_mqtt_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        """Handle MQTT connection."""
        if reason_code == mqtt.CONNACK_ACCEPTED or reason_code.value == 0:
            self._mqtt_connected = True
            _LOGGER.info("Connected to BMW CarData streaming for VIN %s", self._vin)

            # Subscribe to vehicle topic
            gcid = self.tokens.get(TOKEN_GCID, "")
            topic = MQTT_TOPIC_PATTERN.format(gcid=gcid, vin=self._vin)
            client.subscribe(topic, qos=1)
            _LOGGER.debug("Subscribed to MQTT topic: %s", topic)
        else:
            _LOGGER.error("MQTT connection failed with code: %s", reason_code)
            self._mqtt_connected = False

    def _on_mqtt_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        """Handle MQTT disconnection."""
        self._mqtt_connected = False
        _LOGGER.warning("Disconnected from BMW CarData streaming: %s", reason_code)

        # Schedule reconnection
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_handle_reconnect(),
        )

    async def _async_handle_reconnect(self) -> None:
        """Handle MQTT reconnection with token refresh."""
        await asyncio.sleep(5)  # Brief delay before reconnect

        # Refresh tokens before reconnecting
        if self._needs_token_refresh():
            await self._async_refresh_tokens()

        # Update MQTT credentials and reconnect
        if self._mqtt_client:
            gcid = self.tokens.get(TOKEN_GCID)
            id_token = self.tokens.get(TOKEN_ID)

            if gcid and id_token:

                def _reconnect():
                    with self._mqtt_lock:
                        if self._mqtt_client:
                            self._mqtt_client.username_pw_set(gcid, id_token)
                            try:
                                self._mqtt_client.reconnect()
                            except Exception as err:
                                _LOGGER.error("MQTT reconnect failed: %s", err)

                await self.hass.async_add_executor_job(_reconnect)

    def _on_mqtt_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming MQTT message."""
        try:
            payload_str = message.payload.decode("utf-8")
            payload_data = json.loads(payload_str)

            _LOGGER.debug("Received MQTT message: %s", payload_data)

            # Schedule update on HA event loop
            self.hass.loop.call_soon_threadsafe(
                self.hass.async_create_task,
                self._async_process_mqtt_data(payload_data),
            )

        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            _LOGGER.warning("Failed to parse MQTT message: %s", err)
        except Exception as err:
            _LOGGER.exception("Error processing MQTT message: %s", err)

    async def _async_process_mqtt_data(self, payload: dict[str, Any]) -> None:
        """Process MQTT data and update entities."""
        updated = False

        for key, value in payload.items():
            # Store the value
            self.data[key] = {
                "value": value,
                "timestamp": datetime.utcnow().isoformat(),
            }
            updated = True

            # Check for unknown keys
            if key not in ALL_KNOWN_KEYS and key not in self._discovered_keys:
                self._discovered_keys.add(key)
                _LOGGER.info(
                    "Discovered new telemetry key: %s = %s (consider adding to const.py)",
                    key,
                    value,
                )
                # Notify callbacks about new key
                for cb in self._new_key_callbacks:
                    try:
                        cb(key, value)
                    except Exception as err:
                        _LOGGER.error("Error in new key callback: %s", err)

        if updated:
            self.async_set_updated_data(self.data)

    def register_new_key_callback(
        self, callback: Callable[[str, Any], None]
    ) -> Callable[[], None]:
        """Register a callback for newly discovered keys."""
        self._new_key_callbacks.append(callback)

        def remove():
            self._new_key_callbacks.remove(callback)

        return remove

    @property
    def is_mqtt_connected(self) -> bool:
        """Return whether MQTT is connected."""
        return self._mqtt_connected
