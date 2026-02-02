"""BMW CarData integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_VIN, DOMAIN, PLATFORMS
from .coordinator import BMWCarDataCoordinator

_LOGGER = logging.getLogger(__name__)

type BMWCarDataConfigEntry = ConfigEntry[BMWCarDataCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BMW CarData component."""
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register frontend resources."""
    from homeassistant.components.http import StaticPathConfig
    
    await hass.http.async_register_static_paths([
        StaticPathConfig(
            "/bmw_cardata",
            str(Path(__file__).parent / "www"),
            cache_headers=False,
        )
    ])
    _LOGGER.info("Registered BMW CarData static path at /bmw_cardata")


async def async_setup_entry(hass: HomeAssistant, entry: BMWCarDataConfigEntry) -> bool:
    """Set up BMW CarData from a config entry."""
    # Register frontend resources (only once)
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {"frontend_registered": False}
    
    if not hass.data[DOMAIN].get("frontend_registered"):
        await _async_register_frontend(hass)
        hass.data[DOMAIN]["frontend_registered"] = True

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
