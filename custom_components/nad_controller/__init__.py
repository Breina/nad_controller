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
    _LOGGER.info("Entering async_setup_entry")
    """Set up NAD multi-room audio controller from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    ip = entry.data.get(CONF_IP_ADDRESS)
    port = entry.data.get(CONF_PORT, DEFAULT_TCP_PORT)

    try:
        _LOGGER.info(f"FULL DATA: {entry}")
        _LOGGER.info(f"ip: {ip} port: {port}")
        client = NadClient(ip, port)
    except (Exception) as ex:
        raise ConfigEntryNotReady from ex

    undo_listener = entry.add_update_listener(update_listener)
    _LOGGER.info("5")

    hass.data[DOMAIN][entry.entry_id] = {
        CONF_CLIENT: client,
        UNDO_UPDATE_LISTENER: undo_listener
    }

    _LOGGER.info("Going to async_setup_platforms")
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    _LOGGER.info("Entering async_unload_entry")
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    hass.data[DOMAIN][config_entry.entry_id][UNDO_UPDATE_LISTENER]()

    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    _LOGGER.info("Entering update_listener")
    """Handle options update."""
    await hass.config_entries.async_reload(config_entry.entry_id)
