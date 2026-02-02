"""Shared utilities for BMW CarData integration."""

from __future__ import annotations

import time
from typing import Any

from .const import (
    TOKEN_ACCESS,
    TOKEN_EXPIRES_AT,
    TOKEN_GCID,
    TOKEN_ID,
    TOKEN_REFRESH,
    TOKEN_REFRESH_EXPIRES_AT,
)


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
        TOKEN_ID: token_data.get("id_token"),
        TOKEN_GCID: gcid,
        TOKEN_EXPIRES_AT: int(time.time()) + expires_in,
        # Preserve existing refresh expiry if present (refresh doesn't reset it)
        TOKEN_REFRESH_EXPIRES_AT: existing.get(
            TOKEN_REFRESH_EXPIRES_AT, int(time.time()) + refresh_expires_in
        ),
    }


def generate_entity_name_from_key(key: str) -> str:
    """Generate a human-readable entity name from a telemetry key.
    
    Example: "vehicle.body.door.row1.driver.isOpen" -> "Driver Isopen"
    """
    name_parts = key.split(".")
    return " ".join(name_parts[-2:]).replace("_", " ").title()


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
