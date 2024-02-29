"""Support for interfacing with NAD multi-room audio controller."""
import logging
from dataclasses import dataclass
from enum import Enum

from homeassistant import exceptions
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerDeviceClass, MediaPlayerState
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CONF_CLIENT
from .config_flow import DOMAIN
from .nad_client import NadClient

_LOGGER = logging.getLogger(__name__)


@dataclass
class InputChannel:
    name: str
    gain: float
    value: int


@dataclass
class Preset:
    name: str
    value: int


@dataclass
class OutputChannel:
    name: str
    gain: float
    value: int
    source: InputChannel
    dsp_preset: Preset


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the NAD Cl multi-room audio controller entry."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    client: NadClient = data[CONF_CLIENT]

    in_outs = await hass.async_add_executor_job(client.read_in_out)

    inputs = [InputChannel(
        in_outs['input-names'][i]['name'],
        float(in_outs['input-gain'][i]),
        int(in_outs['input-names'][i]['value'])
    ) for i in range(len(in_outs['input-names']))]

    presets = [Preset(dsp_item['name'], int(dsp_item['value'])) for dsp_item in in_outs['dsp-preset-items']]

    outputs = [OutputChannel(
        in_outs['output-names'][i]['name'],
        float(in_outs['output-gain'][i]),
        int(in_outs['output-names'][i]['value']),
        inputs[in_outs['sources'][i]],
        presets[in_outs['dsp-presets'][i]]
    ) for i in range(len(in_outs['output-names']))]

    amp = NadAmp(client)

    entities = [amp]
    for output_channel_index in range(1, 16):
        _LOGGER.info(f"Adding channel {outputs[output_channel_index]}")
        entities.append(
            NadChannel(client, amp, output_channel_index, outputs[output_channel_index], inputs, presets)
        )

    async_add_entities(entities, update_before_add=True)


class GlobalSource(Enum):
    Global1 = 0
    Global2 = 1


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

        self._attr_source_list = [source.name for source in GlobalSource.__members__.values()]
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

        self._attr_unique_id = f"{DOMAIN}_{serial_number}"
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
        self._attr_state = MediaPlayerState.ON

    async def async_turn_off(self):
        self._client.power_off()
        self._attr_state = MediaPlayerState.OFF

    async def async_toggle(self):
        await self._client.power_toggle()
        self._attr_state = {
            MediaPlayerState.ON: MediaPlayerState.OFF,
            MediaPlayerState.OFF: MediaPlayerState.ON
        }[self._attr_state]

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

    def __init__(self, client: NadClient, amp: NadAmp, output_index: int, channel: OutputChannel,
                 inputs: list[InputChannel], dsp_presets: list[Preset]):

        self._client = client
        self._output_channel = output_index

        self._dsp_presets = dsp_presets
        self._attr_sound_mode_list = [preset.name for preset in dsp_presets]
        self._sound_mode = channel.dsp_preset

        self._attr_device_class = MediaPlayerDeviceClass.SPEAKER

        self._sources = inputs
        self._attr_source_list = [source.name for source in inputs]
        self._source = channel.source

        self._attr_unique_id = f"{amp.unique_id}_{self._output_channel}"
        self._attr_name = channel.name
        self._attr_device_info = amp.device_info
        self._amp = amp

        self._snapshot = None
        self._volume = channel.gain
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
        return self._source.name

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

        self._source = [s for s in self._sources if s.name == source][0]
        self._client.set_output_source(self._output_channel, self._source.value + 1)

    async def async_select_sound_mode(self, sound_mode):
        if sound_mode not in self._attr_sound_mode_list:
            raise InvalidSoundMode(f"The sound mode should be one of {self._attr_sound_mode_list}")

        await self._amp.ensure_device_is_on()

        self._sound_mode = [p for p in self._dsp_presets][0]

        self._client.set_output_preset(self._output_channel, self._sound_mode.value + 1)

    @property
    def sound_mode(self):
        return self._sound_mode.name

    @property
    def enabled(self) -> bool:
        return self._amp.state != MediaPlayerState.OFF


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
