"""Support for interfacing with NAD multi-room audio controller."""
import logging
from enum import Enum

from homeassistant import exceptions
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_CLIENT
from .config_flow import DOMAIN
from .nad_client import NadClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NAD Cl multi-room audio controller entry."""
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
    PresetNone = 0
    Preset1 = 1
    Preset2 = 2
    Preset3 = 3
    Preset4 = 4
    Preset5 = 5
    Preset6 = 6
    Preset7 = 7
    Preset8 = 8
    Preset9 = 9


class GlobalSource(Enum):
    Global1 = 0
    Global2 = 1


class InputSource(Enum):
    Source1 = 1
    Source2 = 2
    Source3 = 3
    Source4 = 4
    Source5 = 5
    Source6 = 6
    Source7 = 7
    Source8 = 8
    Source9 = 9
    Source10 = 10
    Source11 = 11
    Source12 = 12
    Source13 = 13
    Source14 = 14
    Source15 = 15
    Source16 = 16


class NadAmp(MediaPlayerEntity):
    _attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(self, client: NadClient):
        self._client = client

        self._attr_device_class = MediaPlayerDeviceClass.RECEIVER

        device_name = client.get_device_name()
        serial_number = client.get_serial_number()
        model = client.get_device_model()
        sw_version = client.get_firmware_version()

        self._attr_source_list = [source.name for source in GlobalSource]
        self._attr_source_list.append("None")
        self._source = None

        self._attr_device_info = DeviceInfo(
            configuration_url=f"http://{client.ip}",
            identifiers={(DOMAIN, serial_number)},
            manufacturer="NAD",
            model=model,
            name=device_name,
            sw_version=sw_version
        )

        self._attr_unique_id = serial_number
        self._attr_name = device_name

        self._state = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._attr_state = self._client.get_power_status().split(':')[1]
            self._update_success = True
        except Exception as e:
            self._update_success = False
            _LOGGER.warning("Could not update: %s", e)
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    async def async_turn_on(self):
        self._client.power_on()
        self._attr_state = "On"

    async def async_turn_off(self):
        self._client.power_off()
        self._attr_state = "Off"

    async def async_toggle(self):
        await self._client.power_toggle()
        self._attr_state = {"On": "Off", "Off": "On"}[self._attr_state]

    @property
    def source(self):
        return self._source.name if self._source is not None else None

    async def async_select_source(self, source):
        if source not in self._attr_source_list:
            raise InvalidSource(f"The global source should be one of {self._attr_source_list}")

        await self.ensure_device_is_on()

        new_source = GlobalSource[source] if source != "None" else None

        if self._source == new_source:
            return

        if self._source is not None:
            self._client.set_global_control(self._source.value, False)

        self._source = new_source

        if self._source is not None:
            self._client.set_global_control(self._source.value, True)

    async def ensure_device_is_on(self):
        if self.state == "Off":
            await self.async_turn_on()
            self.async_schedule_update_ha_state()


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

        self._attr_sound_mode_list = [sm.name for sm in SoundMode]
        self._sound_mode = None

        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER

        self._attr_source_list = [source.name for source in InputSource]
        self._attr_source_list.append("None")
        self._source = None

        self._attr_unique_id = f"{amp.unique_id}_{self._output_channel}"
        self._attr_name = f"{amp.name} channel {self._output_channel}"
        self._attr_device_info = amp.device_info
        self._amp = amp

        self._snapshot = None
        self._volume = None
        self._update_success = True

    def update(self):
        """Retrieve latest state."""
        try:
            self._volume = self._client.get_output_gain(self._output_channel)
            self._attr_is_volume_muted = self._client.get_output_mute(self._output_channel)
            self._update_success = True
        except Exception as e:
            self._update_success = False
            _LOGGER.warning("Could not update output index %d: %s", self._output_channel, e)
            return

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._update_success

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        if self._volume is None:
            return None
        return (float(self._volume) + 6) / 12

    def set_volume_level(self, volume):
        self._amp.ensure_device_is_on()

        self._volume = volume * 12 - 6
        self._client.set_output_gain(self._output_channel, self._volume)

    async def async_volume_up(self):
        await self._amp.ensure_device_is_on()

        self._client.set_output_gain(self._output_channel, self._volume + 0.5)
        self._volume += 0.5

    async def async_volume_down(self):
        await self._amp.ensure_device_is_on()

        self._client.set_output_gain(self._output_channel, self._volume - 0.5)
        self._volume -= 0.5

    def mute_volume(self, mute):
        self._amp.ensure_device_is_on()

        self._client.set_output_mute(self._output_channel, mute)
        self._attr_is_volume_muted = mute

    @property
    def source(self):
        return self._source.name if self._source is not None else None

    @property
    def state(self):
        if self.is_volume_muted:
            return "Muted"
        else:
            return "Playing"

    async def async_select_source(self, source):
        if source not in self._attr_source_list:
            raise InvalidSource(f"The global source should be one of {self._attr_source_list}")

        await self._amp.ensure_device_is_on()

        self._source = InputSource[source]
        self._client.set_output_source(self._output_channel, self._source.value)

    async def async_select_sound_mode(self, sound_mode):
        if sound_mode not in self._attr_sound_mode_list:
            raise InvalidSoundMode(f"The sound mode should be one of {self._attr_sound_mode_list}")

        await self._amp.ensure_device_is_on()

        self._sound_mode = SoundMode[sound_mode]
        self._client.set_output_preset(self._output_channel, SoundMode[sound_mode].value)

    @property
    def sound_mode(self):
        return self._sound_mode.name if self._sound_mode is not None else None

    @property
    def enabled(self) -> bool:
        return self._amp.state == "On"


class InvalidSource(exceptions.IntegrationError):
    def __init__(self, msg: str):
        """Error to indicate we cannot connect."""
        self.msg = msg

    def __str__(self) -> str:
        return self.msg


class InvalidSoundMode(exceptions.IntegrationError):
    def __init__(self, msg: str):
        """Error to indicate we cannot connect."""
        self.msg = msg

    def __str__(self) -> str:
        return self.msg