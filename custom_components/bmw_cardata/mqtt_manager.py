"""Shared MQTT connection manager for BMW CarData integration."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_KEEPALIVE,
    MQTT_TOPIC_PATTERN,
    TOKEN_ID,
)
from .token_manager import BMWTokenManager

_LOGGER = logging.getLogger(__name__)


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
        self._stopped = False  # Set on async_stop(); causes reconnect loop to exit cleanly
        self._mqtt_lock = threading.Lock()
        self._start_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        # Map VIN -> callback function for message routing.
        # Protected by _vin_lock (accessed from both HA loop and paho thread).
        self._vin_callbacks: dict[str, Callable[[dict[str, Any]], None]] = {}
        self._subscribed_vins: set[str] = set()
        self._vin_lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        """Return True if MQTT is connected."""
        return self._mqtt_connected

    def register_vin(
        self, vin: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Register a VIN with its message callback."""
        with self._vin_lock:
            self._vin_callbacks[vin] = callback
        
            # If already connected, subscribe to this VIN's topic
            if self._mqtt_connected and self._mqtt_client and vin not in self._subscribed_vins:
                topic = MQTT_TOPIC_PATTERN.format(gcid=self._gcid, vin=vin)
                self._mqtt_client.subscribe(topic, qos=1)
                self._subscribed_vins.add(vin)
                _LOGGER.info("[%s] Subscribed to topic for VIN %s", self._gcid[:8], vin[-6:])

    def unregister_vin(self, vin: str) -> bool:
        """Unregister a VIN. Returns True if no more VINs registered."""
        with self._vin_lock:
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

            # Force a token refresh before every MQTT connect.  BMW's MQTT broker
            # authenticates with the ID token, which can be stale even when the
            # access token is still valid (e.g. right after a re-auth device-code
            # grant).  A failed refresh is not fatal — we fall back to the
            # existing id_token from a previous successful auth.
            _LOGGER.debug("[%s] Forcing token refresh before MQTT connect", self._gcid[:8])
            await self._token_manager.async_refresh_tokens(force=True)

            tokens = self._token_manager.tokens
            id_token = tokens.get(TOKEN_ID)

            if not id_token:
                _LOGGER.error("[%s] Missing ID token for MQTT — re-authentication required", self._gcid[:8])
                self._mqtt_connecting = False
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
                        # disconnect() before loop_stop(): the network thread
                        # must be running to transmit the DISCONNECT packet.
                        self._mqtt_client.disconnect()
                        self._mqtt_client.loop_stop()

            await self.hass.async_add_executor_job(_stop)
            self._mqtt_client = None
            self._mqtt_connected = False
            with self._vin_lock:
                self._subscribed_vins.clear()

    async def async_stop(self) -> None:
        """Stop the MQTT connection."""
        self._stopped = True
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

            # Snapshot VINs under lock, then subscribe outside lock
            # (paho subscribe is thread-safe and should not be called under our lock)
            with self._vin_lock:
                self._subscribed_vins.clear()
                vins_to_subscribe = list(self._vin_callbacks.keys())

            for vin in vins_to_subscribe:
                topic = MQTT_TOPIC_PATTERN.format(gcid=self._gcid, vin=vin)
                client.subscribe(topic, qos=1)
                with self._vin_lock:
                    self._subscribed_vins.add(vin)
            
            _LOGGER.info(
                "[%s] MQTT connected, subscribed to %d vehicle(s)",
                self._gcid[:8],
                len(vins_to_subscribe),
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
        with self._vin_lock:
            self._subscribed_vins.clear()
        _LOGGER.warning("[%s] MQTT disconnected: %s", self._gcid[:8], reason_code)

        # Schedule reconnection
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_handle_reconnect(),
        )

    async def _async_handle_reconnect(self) -> None:
        """Handle MQTT reconnection by tearing down the client and starting fresh.

        Using async_start() rather than paho's reconnect() avoids a race between
        paho's internal auto-reconnect loop (which reuses stale credentials) and our
        manual credential update.  A fresh client is always created with up-to-date
        tokens, and a retry loop with increasing delays handles transient failures.
        """
        async with self._reconnect_lock:
            delays = [5, 15, 30, 60, 120]
            for attempt, delay in enumerate(delays):
                await asyncio.sleep(delay)

                # Manager was stopped (entry unloaded/reloaded during our sleep).
                # Exit without triggering re-auth — the new manager handles things.
                if self._stopped:
                    return

                _LOGGER.info(
                    "[%s] MQTT reconnect attempt %d/%d",
                    self._gcid[:8],
                    attempt + 1,
                    len(delays),
                )

                # Tear down existing client (stops paho loop thread, clears state)
                await self._async_stop_client()

                # Fresh start: refreshes tokens and creates a new paho client
                await self.async_start()

                # If a client was created, the connection is in progress.
                # _on_mqtt_connect will handle the outcome; if it fails it will
                # schedule another _async_handle_reconnect.
                if self._mqtt_client is not None:
                    return

                _LOGGER.warning(
                    "[%s] MQTT reconnect attempt %d failed, retrying in %ds",
                    self._gcid[:8],
                    attempt + 1,
                    delays[attempt + 1] if attempt + 1 < len(delays) else 0,
                )

            _LOGGER.error(
                "[%s] MQTT reconnect exhausted all %d attempts",
                self._gcid[:8],
                len(delays),
            )

            # Surface a re-authentication notification in the HA UI so the user
            # can renew their session without removing the integration.
            for entry_id in list(self._token_manager._config_entries):
                entry = self.hass.config_entries.async_get_entry(entry_id)
                if entry:
                    entry.async_start_reauth(self.hass)
                    _LOGGER.warning(
                        "[%s] Re-authentication required — check Home Assistant notifications",
                        self._gcid[:8],
                    )
                    break

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

            if vin:
                # Snapshot callback under lock (called from paho thread)
                with self._vin_lock:
                    callback = self._vin_callbacks.get(vin)
                if callback is not None:
                    # Schedule callback on HA event loop
                    self.hass.loop.call_soon_threadsafe(
                        self.hass.async_create_task,
                        self._async_invoke_callback(callback, payload_data),
                    )
                else:
                    _LOGGER.debug(
                        "[%s] Received message for unknown VIN: %s",
                        self._gcid[:8],
                        vin[-6:],
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


def get_mqtt_manager(
    hass: HomeAssistant, token_manager: BMWTokenManager, gcid: str
) -> BMWMqttManager:
    """Get or create an MQTT manager for the given GCID."""
    hass.data.setdefault(DOMAIN, {"token_managers": {}, "mqtt_managers": {}})
    managers = hass.data[DOMAIN].setdefault("mqtt_managers", {})

    if gcid not in managers:
        managers[gcid] = BMWMqttManager(hass, token_manager, gcid)

    return managers[gcid]


async def remove_mqtt_manager(hass: HomeAssistant, gcid: str) -> None:
    """Remove and stop an MQTT manager if it exists."""
    if DOMAIN in hass.data and "mqtt_managers" in hass.data[DOMAIN]:
        manager = hass.data[DOMAIN]["mqtt_managers"].pop(gcid, None)
        if manager:
            await manager.async_stop()
