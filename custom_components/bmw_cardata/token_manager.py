"""Shared OAuth token manager for BMW CarData integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_TOKENS,
    DEFAULT_SCOPES,
    DOMAIN,
    TOKEN_ENDPOINT,
    TOKEN_EXPIRES_AT,
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
            await self.async_refresh_tokens()
        return self._tokens

    async def async_refresh_tokens(self, force: bool = False) -> bool:
        """Refresh access tokens with lock to prevent concurrent refreshes.

        Args:
            force: Bypass the expiry check and always refresh. Used before
                   MQTT connect to guarantee a fresh ID token regardless of
                   access token state.
        """
        async with self._refresh_lock:
            # Double-check after acquiring lock (another coroutine may have refreshed)
            if not force and not self._needs_token_refresh():
                return True

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


def get_token_manager(hass: HomeAssistant, client_id: str) -> BMWTokenManager:
    """Get or create a token manager for the given client_id."""
    hass.data.setdefault(DOMAIN, {"token_managers": {}, "mqtt_managers": {}})
    managers = hass.data[DOMAIN].setdefault("token_managers", {})

    if client_id not in managers:
        managers[client_id] = BMWTokenManager(hass, client_id)

    return managers[client_id]


def remove_token_manager(hass: HomeAssistant, client_id: str) -> None:
    """Remove a token manager if it exists."""
    if DOMAIN in hass.data and "token_managers" in hass.data[DOMAIN]:
        hass.data[DOMAIN]["token_managers"].pop(client_id, None)
