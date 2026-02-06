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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_BASE_URL,
    DEFAULT_SCOPES,
    KNOWN_BINARY_SENSORS,
    KNOWN_SENSORS,
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
from .utils import format_token_expiry, parse_token_response

_LOGGER = logging.getLogger(__name__)


class BMWTokenManager:
    """Shared token manager for all BMW CarData coordinators using the same client_id.
    
    Prevents concurrent token refresh issues when multiple vehicles share the same account.
    """

    def __init__(self, hass: HomeAssistant, client_id: str) -> None:
        """Initialize the token manager."""
        self.hass = hass
        self.client_id = client_id
        self._tokens: dict[str, Any] = {}
        self._refresh_lock = asyncio.Lock()
        self._config_entries: set[str] = set()  # Track entry IDs using this manager

    @property
    def tokens(self) -> dict[str, Any]:
        """Return current tokens."""
        return self._tokens

    def register_entry(self, entry: ConfigEntry) -> None:
        """Register a config entry with this token manager."""
        self._config_entries.add(entry.entry_id)
        entry_tokens = entry.data.get(CONF_TOKENS, {})
        
        # Use tokens with the latest expiry time (most recently refreshed)
        if not self._tokens:
            self._tokens = dict(entry_tokens)
        elif entry_tokens.get(TOKEN_EXPIRES_AT, 0) > self._tokens.get(TOKEN_EXPIRES_AT, 0):
            self._tokens = dict(entry_tokens)
            _LOGGER.debug(
                "[%s] Using fresher tokens from entry %s",
                self.client_id[:8],
                entry.entry_id[:8],
            )

    def unregister_entry(self, entry_id: str) -> bool:
        """Unregister a config entry. Returns True if manager is now empty."""
        self._config_entries.discard(entry_id)
        return len(self._config_entries) == 0

    def _needs_token_refresh(self) -> bool:
        """Check if access token needs refresh."""
        expires_at = self._tokens.get(TOKEN_EXPIRES_AT, 0)
        return time.time() >= (expires_at - TOKEN_REFRESH_BUFFER)

    def _is_refresh_token_valid(self) -> bool:
        """Check if refresh token is still valid."""
        refresh_expires_at = self._tokens.get(TOKEN_REFRESH_EXPIRES_AT, 0)
        return time.time() < refresh_expires_at

    async def async_get_tokens(self) -> dict[str, Any]:
        """Get valid tokens, refreshing if necessary."""
        if self._needs_token_refresh():
            await self._async_refresh_tokens()
        return self._tokens

    async def _async_refresh_tokens(self) -> bool:
        """Refresh access tokens with lock to prevent concurrent refreshes."""
        async with self._refresh_lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            if not self._needs_token_refresh():
                return True

            import aiohttp

            if not self._is_refresh_token_valid():
                _LOGGER.error(
                    "[%s] Refresh token expired, re-authentication required",
                    self.client_id[:8],
                )
                return False

            refresh_token = self._tokens.get(TOKEN_REFRESH)
            if not refresh_token:
                _LOGGER.error("[%s] No refresh token available", self.client_id[:8])
                return False

            try:
                session = async_get_clientsession(self.hass)

                form_data = aiohttp.FormData()
                form_data.add_field("client_id", self.client_id)
                form_data.add_field("grant_type", "refresh_token")
                form_data.add_field("refresh_token", refresh_token)
                form_data.add_field("scope", DEFAULT_SCOPES)

                async with asyncio.timeout(30):
                    async with session.post(
                        TOKEN_ENDPOINT,
                        data=form_data,
                    ) as response:
                        if response.status != 200:
                            text = await response.text()
                            _LOGGER.error(
                                "[%s] Token refresh failed (HTTP %d): %s",
                                self.client_id[:8],
                                response.status,
                                text[:200],
                            )
                            return False

                        token_data = await response.json()

                        # Parse new tokens using shared utility
                        new_tokens = parse_token_response(token_data, self._tokens)
                        self._tokens = new_tokens

                        # Update all config entries using this manager
                        await self._async_update_all_entries(new_tokens)

                        _LOGGER.info(
                            "[%s] Tokens refreshed, expires in %s",
                            self.client_id[:8],
                            format_token_expiry(new_tokens[TOKEN_EXPIRES_AT]),
                        )
                        return True

            except asyncio.TimeoutError:
                _LOGGER.error("[%s] Token refresh timed out", self.client_id[:8])
                return False
            except Exception as err:
                _LOGGER.error("[%s] Token refresh error: %s", self.client_id[:8], err)
                return False

    async def _async_update_all_entries(self, new_tokens: dict[str, Any]) -> None:
        """Update tokens in all config entries using this manager."""
        for entry_id in list(self._config_entries):
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry:
                new_data = {**entry.data, CONF_TOKENS: new_tokens}
                self.hass.config_entries.async_update_entry(entry, data=new_data)


class BMWMqttManager:
    """Shared MQTT connection manager for all vehicles using the same GCID.
    
    BMW's MQTT broker only allows one connection per customer (GCID).
    This manager maintains a single connection and routes messages to the
    appropriate coordinator based on VIN.
    """

    def __init__(
        self, hass: HomeAssistant, token_manager: BMWTokenManager, gcid: str
    ) -> None:
        """Initialize the MQTT manager."""
        self.hass = hass
        self._token_manager = token_manager
        self._gcid = gcid
        self._mqtt_client: mqtt.Client | None = None
        self._mqtt_connected = False
        self._mqtt_connecting = False  # Track if connection attempt is in progress
        self._mqtt_lock = threading.Lock()
        self._start_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        # Map VIN -> callback function for message routing
        self._vin_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}
        # Track subscribed topics
        self._subscribed_vins: set[str] = set()

    @property
    def is_connected(self) -> bool:
        """Return True if MQTT is connected."""
        return self._mqtt_connected

    def register_vin(
        self, vin: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a VIN with its message callback."""
        self._vin_callbacks[vin] = callback
        
        # If already connected, subscribe to this VIN's topic
        if self._mqtt_connected and self._mqtt_client and vin not in self._subscribed_vins:
            topic = MQTT_TOPIC_PATTERN.format(gcid=self._gcid, vin=vin)
            self._mqtt_client.subscribe(topic, qos=1)
            self._subscribed_vins.add(vin)
            _LOGGER.info("[%s] Subscribed to topic for VIN %s", self._gcid[:8], vin[-6:])

    def unregister_vin(self, vin: str) -> bool:
        """Unregister a VIN. Returns True if no more VINs registered."""
        self._vin_callbacks.pop(vin, None)
        
        # Unsubscribe from topic if connected
        if self._mqtt_connected and self._mqtt_client and vin in self._subscribed_vins:
            topic = MQTT_TOPIC_PATTERN.format(gcid=self._gcid, vin=vin)
            self._mqtt_client.unsubscribe(topic)
            self._subscribed_vins.discard(vin)
            _LOGGER.info("[%s] Unsubscribed from topic for VIN %s", self._gcid[:8], vin[-6:])
        
        return len(self._vin_callbacks) == 0

    async def async_start(self) -> None:
        """Start the MQTT connection."""
        async with self._start_lock:
            # Already connected or connection in progress
            if self._mqtt_connected or self._mqtt_connecting:
                return
            
            # If we have a dead client, clean it up first
            if self._mqtt_client and not self._mqtt_connected and not self._mqtt_connecting:
                _LOGGER.info("[%s] Cleaning up disconnected MQTT client", self._gcid[:8])
                await self._async_stop_client()
            
            self._mqtt_connecting = True
            
            # Force token refresh to ensure we have valid credentials
            _LOGGER.debug("[%s] Refreshing tokens before MQTT connect", self._gcid[:8])
            await self._token_manager._async_refresh_tokens()
            
            tokens = self._token_manager.tokens
            id_token = tokens.get(TOKEN_ID)

            if not id_token:
                _LOGGER.error("[%s] Missing ID token for MQTT", self._gcid[:8])
                return

            def _create_and_connect():
                """Create MQTT client and connect (runs in executor)."""
                client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                    client_id=f"ha-bmw-cardata-{self._gcid[:8]}",
                    protocol=mqtt.MQTTv311,
                )

                client.username_pw_set(self._gcid, id_token)

                # Use modern SSL context approach for better compatibility
                ssl_context = ssl.create_default_context()
                client.tls_set_context(ssl_context)

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
                _LOGGER.info(
                    "[%s] MQTT client connecting to %s:%d",
                    self._gcid[:8],
                    MQTT_BROKER_HOST,
                    MQTT_BROKER_PORT,
                )
            except Exception as err:
                self._mqtt_connecting = False
                _LOGGER.error("[%s] Failed to create MQTT client: %s", self._gcid[:8], err)

    async def _async_stop_client(self) -> None:
        """Stop the MQTT client without affecting connecting state."""
        if self._mqtt_client:
            def _stop():
                with self._mqtt_lock:
                    if self._mqtt_client:
                        self._mqtt_client.loop_stop()
                        self._mqtt_client.disconnect()

            await self.hass.async_add_executor_job(_stop)
            self._mqtt_client = None
            self._mqtt_connected = False
            self._subscribed_vins.clear()

    async def async_stop(self) -> None:
        """Stop the MQTT connection."""
        self._mqtt_connecting = False
        await self._async_stop_client()

    def _on_mqtt_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None = None,
    ) -> None:
        """Handle MQTT connection."""
        self._mqtt_connecting = False
        
        if reason_code == mqtt.CONNACK_ACCEPTED or reason_code.value == 0:
            self._mqtt_connected = True
            self._subscribed_vins.clear()

            # Subscribe to all registered VINs
            for vin in self._vin_callbacks:
                topic = MQTT_TOPIC_PATTERN.format(gcid=self._gcid, vin=vin)
                client.subscribe(topic, qos=1)
                self._subscribed_vins.add(vin)
            
            _LOGGER.info(
                "[%s] MQTT connected, subscribed to %d vehicle(s)",
                self._gcid[:8],
                len(self._vin_callbacks),
            )
        else:
            _LOGGER.error(
                "[%s] MQTT connection failed: %s",
                self._gcid[:8],
                reason_code,
            )
            self._mqtt_connected = False
            
            # Schedule reconnection attempt on auth failure
            self.hass.loop.call_soon_threadsafe(
                self.hass.async_create_task,
                self._async_handle_reconnect(),
            )

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
        self._subscribed_vins.clear()
        _LOGGER.warning("[%s] MQTT disconnected: %s", self._gcid[:8], reason_code)

        # Schedule reconnection
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_handle_reconnect(),
        )

    async def _async_handle_reconnect(self) -> None:
        """Handle MQTT reconnection with token refresh."""
        async with self._reconnect_lock:
            await asyncio.sleep(5)  # Brief delay before reconnect

            # Always refresh tokens before reconnecting to ensure fresh ID token
            _LOGGER.info("[%s] Refreshing tokens before MQTT reconnect", self._gcid[:8])
            if not await self._token_manager._async_refresh_tokens():
                _LOGGER.error("[%s] Token refresh failed, cannot reconnect", self._gcid[:8])
                return

            # Update MQTT credentials and reconnect
            if self._mqtt_client:
                tokens = self._token_manager.tokens
                id_token = tokens.get(TOKEN_ID)

                if id_token:
                    def _reconnect():
                        with self._mqtt_lock:
                            if self._mqtt_client:
                                self._mqtt_client.username_pw_set(self._gcid, id_token)
                                try:
                                    self._mqtt_client.reconnect()
                                    _LOGGER.info("[%s] MQTT reconnection initiated", self._gcid[:8])
                                except Exception as err:
                                    _LOGGER.error("[%s] MQTT reconnect failed: %s", self._gcid[:8], err)

                    await self.hass.async_add_executor_job(_reconnect)
                else:
                    _LOGGER.error("[%s] Cannot reconnect: missing ID token", self._gcid[:8])

    def _on_mqtt_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming MQTT message and route to appropriate coordinator."""
        try:
            payload_str = message.payload.decode("utf-8")
            payload_data = json.loads(payload_str)

            # Extract VIN from payload or topic
            vin = payload_data.get("vin")
            if not vin:
                # Try to extract from topic: {gcid}/{vin}
                topic_parts = message.topic.split("/")
                if len(topic_parts) >= 2:
                    vin = topic_parts[1]

            if vin and vin in self._vin_callbacks:
                # Route to the appropriate coordinator's callback
                callback = self._vin_callbacks[vin]
                # Schedule callback on HA event loop
                self.hass.loop.call_soon_threadsafe(
                    self.hass.async_create_task,
                    self._async_invoke_callback(callback, payload_data),
                )
            else:
                _LOGGER.debug(
                    "[%s] Received message for unknown VIN: %s",
                    self._gcid[:8],
                    vin[-6:] if vin else "none",
                )

        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            _LOGGER.warning("[%s] Failed to parse MQTT message: %s", self._gcid[:8], err)
        except Exception as err:
            _LOGGER.error("[%s] Error processing MQTT message: %s", self._gcid[:8], err)

    async def _async_invoke_callback(
        self, callback: Callable[[dict[str, Any]], None], payload: dict[str, Any]
    ) -> None:
        """Invoke callback (possibly async) with payload."""
        result = callback(payload)
        if asyncio.iscoroutine(result):
            await result


def get_token_manager(hass: HomeAssistant, client_id: str) -> BMWTokenManager:
    """Get or create a token manager for the given client_id."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {"token_managers": {}, "mqtt_managers": {}}
    
    managers = hass.data[DOMAIN].setdefault("token_managers", {})
    
    if client_id not in managers:
        managers[client_id] = BMWTokenManager(hass, client_id)
    
    return managers[client_id]


def get_mqtt_manager(
    hass: HomeAssistant, token_manager: BMWTokenManager, gcid: str
) -> BMWMqttManager:
    """Get or create an MQTT manager for the given GCID."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {"token_managers": {}, "mqtt_managers": {}}
    
    managers = hass.data[DOMAIN].setdefault("mqtt_managers", {})
    
    if gcid not in managers:
        managers[gcid] = BMWMqttManager(hass, token_manager, gcid)
    
    return managers[gcid]


def remove_token_manager(hass: HomeAssistant, client_id: str) -> None:
    """Remove a token manager if it exists."""
    if DOMAIN in hass.data and "token_managers" in hass.data[DOMAIN]:
        hass.data[DOMAIN]["token_managers"].pop(client_id, None)


async def remove_mqtt_manager(hass: HomeAssistant, gcid: str) -> None:
    """Remove and stop an MQTT manager if it exists."""
    if DOMAIN in hass.data and "mqtt_managers" in hass.data[DOMAIN]:
        manager = hass.data[DOMAIN]["mqtt_managers"].pop(gcid, None)
        if manager:
            await manager.async_stop()


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
        """Return current tokens from token manager."""
        return self._token_manager.tokens

    @property
    def vehicle_info(self) -> dict[str, Any]:
        """Return vehicle info."""
        return self.config_entry.data.get("vehicle_info", {})

    def _needs_token_refresh(self) -> bool:
        """Check if access token needs refresh."""
        return self._token_manager._needs_token_refresh()

    async def _async_refresh_tokens(self) -> bool:
        """Refresh access tokens via shared token manager."""
        return await self._token_manager._async_refresh_tokens()

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
                        _LOGGER.debug("[%s] Fetched basic vehicle data", self._vin[-6:])
                    else:
                        _LOGGER.warning(
                            "[%s] Failed to fetch basic data (HTTP %d)",
                            self._vin[-6:],
                            response.status,
                        )

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

        # Data is nested inside 'data' key
        data_payload = payload.get("data", {})
        
        for key, value_obj in data_payload.items():
            # value_obj has structure: {'timestamp': '...', 'value': ...}
            if isinstance(value_obj, dict) and "value" in value_obj:
                actual_value = value_obj.get("value")
                timestamp = value_obj.get("timestamp", datetime.utcnow().isoformat())
            else:
                actual_value = value_obj
                timestamp = datetime.utcnow().isoformat()
            
            # Store the value
            self.data[key] = {
                "value": actual_value,
                "timestamp": timestamp,
            }
            updated = True

            # Check for unknown keys
            if key not in KNOWN_SENSORS and key not in KNOWN_BINARY_SENSORS and key not in self._discovered_keys:
                self._discovered_keys.add(key)
                _LOGGER.info(
                    "[%s] New telemetry key: %s (type=%s, add to const.py for custom config)",
                    self._vin[-6:],
                    key,
                    type(actual_value).__name__,
                )
                # Notify callbacks about new key
                for cb in self._new_key_callbacks:
                    try:
                        cb(key, actual_value)
                    except Exception as err:
                        _LOGGER.error("[%s] New key callback error: %s", self._vin[-6:], err)

        if updated:
            self.async_set_updated_data(self.data)

    def register_new_key_callback(
        self, cb: Callable[[str, Any], None]
    ) -> Callable[[], None]:
        """Register a callback for newly discovered keys."""
        self._new_key_callbacks.append(cb)

        def remove():
            self._new_key_callbacks.remove(cb)

        return remove

    @property
    def is_mqtt_connected(self) -> bool:
        """Return whether MQTT is connected."""
        return self._mqtt_manager.is_connected
