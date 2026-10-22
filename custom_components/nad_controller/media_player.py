"""Media players for the amplifier, each output channel and each zone."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity, NadZoneEntity
from .nad_client import CHANNEL_COUNT, GAIN_STEP, GLOBAL_COUNT, MAX_GAIN, MIN_GAIN, NadState

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0
NO_GLOBAL_SOURCE = "None"
GAIN_RANGE = MAX_GAIN - MIN_GAIN


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the NAD Cl multi-room audio controller entry."""
    coordinator = entry.runtime_data
    entities: list[MediaPlayerEntity] = [NadAmp(coordinator)]
    entities += [NadChannel(coordinator, channel) for channel in range(1, CHANNEL_COUNT + 1)]
    entities += [NadZone(coordinator, zone) for zone in coordinator.data.zones]
    async_add_entities(entities)


def gain_to_volume(gain: float) -> float:
    return (gain - MIN_GAIN) / GAIN_RANGE


def volume_to_gain(volume: float) -> float:
    return clamp_gain(volume * GAIN_RANGE + MIN_GAIN)


def clamp_gain(gain: float) -> float:
    return min(MAX_GAIN, max(MIN_GAIN, round(gain / GAIN_STEP) * GAIN_STEP))


def channel_state(data: NadState, channels: list[int]) -> MediaPlayerState:
    if not data.power:
        return MediaPlayerState.OFF
    if any(data.signals[channel - 1] for channel in channels if channel <= len(data.signals)):
        return MediaPlayerState.PLAYING
    return MediaPlayerState.IDLE


def validate_option(option: str, options: list[str], translation_key: str) -> int:
    if option not in options:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=translation_key,
            translation_placeholders={"option": option, "options": ", ".join(options)},
        )
    return options.index(option)


class NadAmp(NadEntity, MediaPlayerEntity):
    """The amplifier: power and the global inputs that override every output's source."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_supported_features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.ON if self.coordinator.data.power else MediaPlayerState.OFF

    @property
    def source_list(self) -> list[str]:
        return [NO_GLOBAL_SOURCE, *self.coordinator.data.global_names]

    @property
    def source(self) -> str:
        data = self.coordinator.data
        enabled = [name for name, on in zip(data.global_names, data.global_enabled) if on]
        return enabled[0] if enabled else NO_GLOBAL_SOURCE

    async def async_turn_on(self) -> None:
        await self.coordinator.async_command(self.coordinator.client.power_on())

    async def async_turn_off(self) -> None:
        await self.coordinator.async_command(self.coordinator.client.power_off())

    async def async_select_source(self, source: str) -> None:
        selected = validate_option(source, self.source_list, "invalid_source") - 1

        async def select() -> None:
            # Switch the other global off first, so outputs never briefly follow both
            for global_index in sorted(range(GLOBAL_COUNT), key=lambda g: g == selected):
                await self.coordinator.client.set_global_enabled(global_index, global_index == selected)

        await self.coordinator.async_command(select())


class NadChannelGroup(MediaPlayerEntity):
    """Volume, mute, source and preset over a set of output channels."""

    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
            MediaPlayerEntityFeature.VOLUME_MUTE
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.SELECT_SOURCE
            | MediaPlayerEntityFeature.SELECT_SOUND_MODE
    )
    _attr_volume_step = GAIN_STEP / GAIN_RANGE
    coordinator: NadCoordinator

    @property
    def channels(self) -> list[int]:
        raise NotImplementedError

    def _common(self, values: list[Any]) -> Any:
        picked = {values[channel - 1] for channel in self.channels}
        return picked.pop() if len(picked) == 1 else None

    @property
    def gains(self) -> list[float]:
        return [self.coordinator.data.output_gains[channel - 1] for channel in self.channels]

    @property
    def state(self) -> MediaPlayerState:
        return channel_state(self.coordinator.data, self.channels)

    @property
    def volume_level(self) -> float | None:
        gains = self.gains
        return gain_to_volume(sum(gains) / len(gains)) if gains else None

    @property
    def is_volume_muted(self) -> bool:
        return all(self.coordinator.data.output_mutes[channel - 1] for channel in self.channels)

    @property
    def source_list(self) -> list[str]:
        return self.coordinator.data.input_names

    @property
    def source(self) -> str | None:
        source = self._common(self.coordinator.data.sources)
        return self.source_list[source] if source is not None and source < len(self.source_list) else None

    @property
    def sound_mode_list(self) -> list[str]:
        return [name for _, name in sorted(self.coordinator.data.preset_names.items())]

    @property
    def sound_mode(self) -> str | None:
        preset = self._common(self.coordinator.data.presets)
        return self.coordinator.data.preset_names.get(preset) if preset is not None else None

    async def _shift_gain(self, delta: float) -> None:
        """Move every channel by the same amount, which keeps the balance between them."""
        client = self.coordinator.client

        async def shift() -> None:
            for channel, gain in zip(self.channels, self.gains):
                new_gain = clamp_gain(gain + delta)
                if new_gain != gain:
                    await client.set_output_gain(channel, new_gain)

        await self.coordinator.async_command(shift())

    async def async_set_volume_level(self, volume: float) -> None:
        gains = self.gains
        await self._shift_gain(volume_to_gain(volume) - sum(gains) / len(gains))

    async def async_volume_up(self) -> None:
        await self._shift_gain(GAIN_STEP)

    async def async_volume_down(self) -> None:
        await self._shift_gain(-GAIN_STEP)

    async def _for_each_channel(self, command) -> None:
        async def run() -> None:
            for channel in self.channels:
                await command(channel)

        await self.coordinator.async_command(run())

    async def async_mute_volume(self, mute: bool) -> None:
        client = self.coordinator.client
        await self._for_each_channel(lambda channel: client.set_output_mute(channel, mute))

    async def async_select_source(self, source: str) -> None:
        input_index = validate_option(source, self.source_list, "invalid_source")
        client = self.coordinator.client
        await self._for_each_channel(lambda channel: client.set_output_source(channel, input_index))

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        validate_option(sound_mode, self.sound_mode_list, "invalid_sound_mode")
        preset = next(value for value, name in self.coordinator.data.preset_names.items() if name == sound_mode)
        client = self.coordinator.client
        await self._for_each_channel(lambda channel: client.set_output_preset(channel, preset))


class NadChannel(NadEntity, NadChannelGroup):
    """One output channel. The amplifier mutes channels per stereo pair."""

    def __init__(self, coordinator: NadCoordinator, channel: int):
        super().__init__(coordinator, str(channel))
        self._channel = channel

    @property
    def channels(self) -> list[int]:
        return [self._channel]

    @property
    def name(self) -> str:
        return self.coordinator.data.output_names[self._channel - 1]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attributes: dict[str, Any] = {"channel": self._channel, "gain_db": data.output_gains[self._channel - 1]}
        if self._channel <= len(data.protection):
            attributes["protection"] = data.protection[self._channel - 1]
        zones = [zone.name for zone in data.zones if self._channel in zone.channels]
        if zones:
            attributes["zones"] = zones
        return attributes


class NadZone(NadZoneEntity, NadChannelGroup):
    """A zone as configured in the web UI, controlling all of its channels together."""

    _attr_name = None

    @property
    def channels(self) -> list[int]:
        zone = self.zone
        return zone.channels if zone else []

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "channels": [data.output_names[channel - 1] for channel in self.channels],
            "gains_db": self.gains,
        }
