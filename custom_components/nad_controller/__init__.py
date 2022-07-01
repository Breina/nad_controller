"""The NAD Cl 16-60 home audio integration."""
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .config_flow import DOMAIN
from .nad_client import NadClient, DEFAULT_TCP_PORT

CONF_CLIENT = "client"
UNDO_UPDATE_LISTENER = "undo_update_listener"
PLATFORMS = [Platform.MEDIA_PLAYER]

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT): int
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NAD Cl 16-60 from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    config = hass.data[DOMAIN].get(Platform.MEDIA_PLAYER, {})
    host = config.get(CONF_HOST)
    port = config.get(CONF_PORT, DEFAULT_TCP_PORT)

    try:
        client = NadClient(host, port)
    except (Exception) as ex:
        raise ConfigEntryNotReady from ex

    undo_listener = entry.add_update_listener(update_listener)

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_CLIENT: client,
        UNDO_UPDATE_LISTENER: undo_listener
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

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
