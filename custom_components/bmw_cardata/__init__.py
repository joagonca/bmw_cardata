"""BMW CarData integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_VIN, DOMAIN, PLATFORMS
from .coordinator import BMWCarDataCoordinator

_LOGGER = logging.getLogger(__name__)

type BMWCarDataConfigEntry = ConfigEntry[BMWCarDataCoordinator]

# Card URL path
CARD_URL = "/bmw_cardata/bmw-cardata-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BMW CarData component."""
    # Register static path for the card
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/bmw_cardata",
            str(Path(__file__).parent / "www"),
            cache_headers=True,
        )
    ])
    
    # Register the card as a Lovelace resource
    await _async_register_card_resource(hass)
    
    return True


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    """Register the card as a Lovelace resource if not already registered."""
    # Get Lovelace resources
    if "lovelace" not in hass.data:
        return
    
    lovelace_data = hass.data["lovelace"]
    if "resources" not in lovelace_data:
        return
    
    resources: ResourceStorageCollection = lovelace_data["resources"]
    
    # Check if already registered
    for resource in resources.async_items():
        if CARD_URL in resource.get("url", ""):
            return
    
    # Register the card
    await resources.async_create_item({
        "url": CARD_URL,
        "type": "module",
    })
    _LOGGER.info("Registered BMW CarData card as Lovelace resource")


async def async_setup_entry(hass: HomeAssistant, entry: BMWCarDataConfigEntry) -> bool:
    """Set up BMW CarData from a config entry."""
    coordinator = BMWCarDataCoordinator(hass, entry)

    # Set up the coordinator
    if not await coordinator.async_setup():
        return False

    # Store coordinator in runtime data
    entry.runtime_data = coordinator

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: BMWCarDataConfigEntry
) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Shutdown coordinator
        coordinator: BMWCarDataCoordinator = entry.runtime_data
        await coordinator.async_shutdown()

    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant, entry: BMWCarDataConfigEntry
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
