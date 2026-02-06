"""BMW CarData integration."""

from __future__ import annotations

from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_TOKENS, PLATFORMS
from .coordinator import (
    BMWCarDataCoordinator,
    get_mqtt_manager,
    get_token_manager,
    remove_mqtt_manager,
    remove_token_manager,
)

BMWCarDataConfigEntry: TypeAlias = ConfigEntry[BMWCarDataCoordinator]

# Token key for GCID
TOKEN_GCID = "gcid"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the BMW CarData component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BMWCarDataConfigEntry) -> bool:
    """Set up BMW CarData from a config entry."""
    client_id = entry.data[CONF_CLIENT_ID]
    tokens = entry.data.get(CONF_TOKENS, {})
    gcid = tokens.get(TOKEN_GCID)
    
    if not gcid:
        return False
    
    # Get or create shared token manager for this client_id
    token_manager = get_token_manager(hass, client_id)
    token_manager.register_entry(entry)
    
    # Get or create shared MQTT manager for this GCID
    mqtt_manager = get_mqtt_manager(hass, token_manager, gcid)
    
    coordinator = BMWCarDataCoordinator(hass, entry, token_manager, mqtt_manager)

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
        # Shutdown coordinator (unregisters VIN from MQTT manager)
        coordinator: BMWCarDataCoordinator = entry.runtime_data
        await coordinator.async_shutdown()
        
        # Get GCID for MQTT manager cleanup
        tokens = entry.data.get(CONF_TOKENS, {})
        gcid = tokens.get(TOKEN_GCID)
        
        # Unregister from token manager and clean up if last entry
        client_id = entry.data[CONF_CLIENT_ID]
        token_manager = get_token_manager(hass, client_id)
        if token_manager.unregister_entry(entry.entry_id):
            remove_token_manager(hass, client_id)
            # Also remove MQTT manager if this was the last entry
            if gcid:
                await remove_mqtt_manager(hass, gcid)

    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant, entry: BMWCarDataConfigEntry
) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
