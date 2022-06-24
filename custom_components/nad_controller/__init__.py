"""The NAD Cl 16-60 home audio intagration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, Platform, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from nad_client import NadClient
from .const import (
    DOMAIN,
    NAD_OBJECT,
    UNDO_UPDATE_LISTENER,
)

PLATFORMS = [Platform.MEDIA_PLAYER]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NAD Cl 16-60 from a config entry."""
    host = entry.data[CONF_HOST]

    try:
        nad = await hass.async_add_executor_job(NadClient, host)
    except Exception as err:
        _LOGGER.error("Error connecting to NAD Cl 16-60 controller at %s", host)
        raise ConfigEntryNotReady from err

    hass.config_entries.async_update_entry(
        entry, data={**entry.data}
    )

    undo_listener = entry.add_update_listener(_update_listener)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        NAD_OBJECT: nad,
        UNDO_UPDATE_LISTENER: undo_listener
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN][entry.entry_id][UNDO_UPDATE_LISTENER]()
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
