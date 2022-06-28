"""Support for interfacing with NAD Cl 16-60 home audio controller."""
import logging
from enum import Enum

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerDeviceClass,
    PLATFORM_SCHEMA
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from . import CONF_CLIENT
from .nad_client import NadClient

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string
})


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NAD Cl 16-60 home audio controller entry."""
    entities = []
    data = hass.data[DOMAIN][config_entry.entry_id]
    client = data[CONF_CLIENT]

    amp = NadAmp(client)

    entities = [amp]
    for output_channel_index in range(1, 16):
        _LOGGER.info("Adding channel %d", output_channel_index)
        entities.append(
            NadChannel(client, amp, output_channel_index)
        )

    async_add_entities(entities, update_before_add=True)


class SoundMode(Enum):
    PresetNone: 0
    Preset1: 1
    Preset2: 2
    Preset3: 3
    Preset4: 4
    Preset5: 5
    Preset6: 6
    Preset7: 7
    Preset8: 8
    Preset9: 9


class InputSource(Enum):
    Global1: (True, 1)
    Global2: (True, 2)
    Source1: (False, 1)
    Source2: (False, 2)
    Source3: (False, 3)
    Source4: (False, 4)
    Source5: (False, 5)
    Source6: (False, 6)
    Source7: (False, 7)
    Source8: (False, 8)
    Source9: (False, 9)
    Source10: (False, 10)
    Source11: (False, 11)
    Source12: (False, 12)
    Source13: (False, 13)
    Source14: (False, 14)
    Source15: (False, 15)
    Source16: (False, 16)


class NadAmp(MediaPlayerEntity):
    _attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(self, client: NadClient):
        self._client = client

        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER
        self._attr_sound_mode_list = [sm.name for sm in SoundMode]

        device_name = client.get_device_name()
        serial_number = client.get_serial_number()
        model = client.get_device_model()
        sw_version = client.get_firmware_version()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            manufacturer="NAD",
            model=model,
            name=device_name,
            sw_version=sw_version,
        )

        self._attr_unique_id = serial_number
        self._attr_name = device_name

        self._state = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._state = self._client.get_power_status()
            self._update_success = True
        except Exception:
            self._update_success = False
            _LOGGER.warning("Could not update")
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    def turn_on(self):
        self._client.power_on()

    def turn_off(self):
        self._client.power_off()

    async def async_toggle(self):
        await self._client.power_toggle()


class NadChannel(MediaPlayerEntity):
    _attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )

    def __init__(self, client: NadClient, amp: NadAmp, output_index: int):
        self._client = client
        self._output_channel = output_index

        self._attr_source_list = [source.name for source in InputSource]
        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER

        self._attr_unique_id = f"{amp.unique_id}_{self._output_channel}"
        self._attr_name = f"{amp.name} channel {self._output_channel}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name,
            manufacturer="NAD",
            via_device=amp.device_info.get('identifiers')[0]
        )

        self._source_index = None
        self._is_global = False
        self._snapshot = None
        self._volume = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._volume = self._client.get_output_gain(self._output_channel)
            self._attr_is_volume_muted = self._client.get_output_mute(self._output_channel)
            self._update_success = True
        except Exception:
            self._update_success = False
            _LOGGER.warning("Could not update output index %d", self._output_channel)
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return (self._volume + 6) / 12

    def set_volume_level(self, volume):
        self._volume = volume * 12 - 6
        self._client.set_output_gain(self._output_channel, self._volume)

    async def async_volume_up(self):
        await self._client.set_output_gain(self._output_channel, self._volume + 0.5)
        self._volume += 0.5

    async def async_volume_down(self):
        await self._client.set_output_gain(self._output_channel, self._volume - 0.5)
        self._volume -= 0.5

    def mute_volume(self, mute):
        self._client.set_output_mute(self._output_channel, mute)

    @property
    def source(self) -> str | None:
        if self._source_index is None:
            return None
        return f"{'Global' if self._is_global else 'Input'}{self._source_index}"

    def select_source(self, source):
        if source not in InputSource:
            return

        (is_global, index) = InputSource[source].value

        if ((not is_global) and self._is_global) or (is_global and (index != self._source_index)):
            self._client.set_global_control(self._source_index, False)

        if is_global:
            self._client.set_global_control(index, True)
        else:
            self._client.set_output_source(self._output_channel, index)

        self._source_index = index
        self._is_global = is_global

    def select_sound_mode(self, sound_mode):
        self._client.set_output_preset(self._output_channel, SoundMode[sound_mode].value)
