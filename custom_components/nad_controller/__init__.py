"""The NAD Cl multi-room audio controller integration."""

import logging

from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import amp_device_info
from .nad_client import DEFAULT_TCP_PORT, NadClient, NadError

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: NadConfigEntry) -> bool:
    """Set up NAD multi-room audio controller from a config entry."""
    client = NadClient(
        entry.data[CONF_IP_ADDRESS],
        async_get_clientsession(hass),
        entry.data.get(CONF_PORT, DEFAULT_TCP_PORT),
    )

    try:
        identity = await client.get_identity()
    except NadError as ex:
        raise ConfigEntryNotReady(str(ex)) from ex

    coordinator = NadCoordinator(hass, entry, client, identity)
    await coordinator.async_config_entry_first_refresh()
    # Registered up front, so the zones can refer to it as their parent
    coordinator.device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **amp_device_info(coordinator)
    ).id
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NadConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
