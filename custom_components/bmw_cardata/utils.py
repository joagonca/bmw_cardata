"""Shared utilities for BMW CarData integration."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    TOKEN_ACCESS,
    TOKEN_EXPIRES_AT,
    TOKEN_GCID,
    TOKEN_ID,
    TOKEN_REFRESH,
    TOKEN_REFRESH_EXPIRES_AT,
    TOKEN_UPDATED_AT,
)

_LOGGER = logging.getLogger(__name__)


def parse_token_response(
    token_data: dict[str, Any],
    existing_tokens: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse token response and extract relevant data.
    
    Args:
        token_data: Raw token response from BMW API.
        existing_tokens: Existing tokens to fall back to for missing fields (e.g., during refresh).
    
    Returns:
        Normalized token dictionary with all required fields.
    """
    existing = existing_tokens or {}
    
    # GCID is returned directly in the token response per BMW API spec
    # Fall back to existing GCID if not in refresh response
    gcid = token_data.get("gcid") or existing.get(TOKEN_GCID, "")

    expires_in = token_data.get("expires_in", 3600)
    refresh_expires_in = token_data.get("refresh_expires_in", 1209600)  # 2 weeks default

    return {
        TOKEN_ACCESS: token_data.get("access_token"),
        TOKEN_REFRESH: token_data.get("refresh_token") or existing.get(TOKEN_REFRESH),
        TOKEN_ID: token_data.get("id_token") or existing.get(TOKEN_ID),
        TOKEN_GCID: gcid,
        TOKEN_EXPIRES_AT: int(time.time()) + expires_in,
        # Preserve existing refresh expiry if present (refresh doesn't reset it)
        TOKEN_REFRESH_EXPIRES_AT: existing.get(
            TOKEN_REFRESH_EXPIRES_AT, int(time.time()) + refresh_expires_in
        ),
        TOKEN_UPDATED_AT: int(time.time()),
    }


def format_token_expiry(expires_at: int) -> str:
    """Format token expiry timestamp for logging.
    
    Returns human-readable time until expiry.
    """
    remaining = expires_at - int(time.time())
    if remaining <= 0:
        return "expired"
    if remaining < 60:
        return f"{remaining}s"
    if remaining < 3600:
        return f"{remaining // 60}m"
    return f"{remaining // 3600}h {(remaining % 3600) // 60}m"


async def async_bmw_api_get(
    hass: HomeAssistant, access_token: str, path: str
) -> dict[str, Any]:
    """Make an authenticated GET request to the BMW CarData REST API.

    Args:
        hass: Home Assistant instance (used for shared aiohttp session).
        access_token: Bearer token for authorization.
        path: API path relative to API_BASE_URL (e.g., "/customers/vehicles/mappings").

    Returns:
        Parsed JSON response.

    Raises:
        aiohttp.ClientResponseError: On non-2xx status via raise_for_status().
    """
    session = async_get_clientsession(hass)
    async with asyncio.timeout(30):
        async with session.get(
            f"{API_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "x-version": "v1",
            },
        ) as response:
            response.raise_for_status()
            return await response.json()


def extract_telemetry_value(data: Any) -> tuple[Any, str | None]:
    """Extract value and timestamp from a coordinator data entry.

    BMW telemetry data is stored as ``{"value": ..., "timestamp": ...}`` dicts.
    This helper normalises the extraction so callers don't repeat the isinstance check.

    Returns:
        (value, timestamp) tuple.  timestamp is None when data is not a dict.
    """
    if isinstance(data, dict) and "value" in data:
        return data["value"], data.get("timestamp")
    return data, None
