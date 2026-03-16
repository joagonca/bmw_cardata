"""Diagnostics support for BMW CarData."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_TOKENS,
    CONF_VEHICLE_INFO,
    CONF_VIN,
    TOKEN_EXPIRES_AT,
    TOKEN_REFRESH_EXPIRES_AT,
)
from .coordinator import BMWCarDataCoordinator
from .utils import format_token_expiry

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: BMWCarDataCoordinator = entry.runtime_data
    tokens = coordinator.tokens

    return {
        "vehicle": {
            "vin_suffix": coordinator.vin[-6:],
            **entry.data.get(CONF_VEHICLE_INFO, {}),
        },
        "connection": {
            "mqtt_connected": coordinator.is_mqtt_connected,
            "access_token_expires_in": format_token_expiry(
                tokens.get(TOKEN_EXPIRES_AT, 0)
            ),
            "refresh_token_expires_in": format_token_expiry(
                tokens.get(TOKEN_REFRESH_EXPIRES_AT, 0)
            ),
        },
        "options": dict(entry.options),
        "telemetry_snapshot": {
            key: value for key, value in coordinator.data.items()
        },
        "mqtt_message_buffer": {
            "count": len(coordinator.mqtt_message_buffer),
            "max_size": coordinator.mqtt_message_buffer.maxlen,
            "messages": list(coordinator.mqtt_message_buffer),
        },
    }
