"""The NAD Cl multi-room audio controller integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .config_flow import DOMAIN
from .nad_client import NadClient, DEFAULT_TCP_PORT

CONF_CLIENT = "client"
UNDO_UPDATE_LISTENER = "undo_update_listener"
PLATFORMS = [Platform.MEDIA_PLAYER]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NAD multi-room audio controller from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    ip = entry.data.get(CONF_IP_ADDRESS)
    port = entry.data.get(CONF_PORT, DEFAULT_TCP_PORT)

    try:
        client = NadClient(ip, port)
    except Exception as ex:
        raise ConfigEntryNotReady from ex

    undo_listener = entry.add_update_listener(update_listener)

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_CLIENT: client,
        UNDO_UPDATE_LISTENER: undo_listener,
    }

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
