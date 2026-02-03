"""BMW CarData integration."""

from __future__ import annotations

from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import BMWCarDataCoordinator

BMWCarDataConfigEntry: TypeAlias = ConfigEntry[BMWCarDataCoordinator]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BMW CarData component."""
    return True


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
