"""Gains and delays of the NAD amplifier, in their native units."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import CHANNEL_COUNT, GAIN_STEP, GLOBAL_COUNT, MAX_GAIN, MIN_GAIN, NadClient, NadState

PARALLEL_UPDATES = 0
DECIBEL = "dB"


@dataclass(frozen=True, kw_only=True)
class NadNumberDescription(NumberEntityDescription):
    value_fn: Callable[[NadState], float | None]
    set_fn: Callable[[NadClient, float], Awaitable[None]]
    name_fn: Callable[[NadState], str] | None = None


def gain_description(key: str, **kwargs) -> dict:
    return dict(
        key=key,
        native_min_value=MIN_GAIN,
        native_max_value=MAX_GAIN,
        native_step=GAIN_STEP,
        native_unit_of_measurement=DECIBEL,
        mode=NumberMode.SLIDER,
        **kwargs,
    )


def output_gain(channel: int) -> NadNumberDescription:
    return NadNumberDescription(
        **gain_description(f"{channel}_gain"),
        name_fn=lambda data: f"{data.output_names[channel - 1]} gain",
        value_fn=lambda data: data.output_gains[channel - 1],
        set_fn=lambda client, value: client.set_output_gain(channel, value),
    )


def input_gain(channel: int) -> NadNumberDescription:
    return NadNumberDescription(
        **gain_description(f"input_{channel}_gain"),
        name_fn=lambda data: f"{data.input_names[channel - 1]} input gain",
        value_fn=lambda data: data.input_gains[channel - 1] if channel <= len(data.input_gains) else None,
        set_fn=lambda client, value: client.set_input_gain(channel, value),
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    )


def global_gain(global_index: int) -> NadNumberDescription:
    return NadNumberDescription(
        **gain_description(f"global_{'ab'[global_index]}_gain"),
        name_fn=lambda data: f"{data.global_names[global_index]} gain",
        value_fn=lambda data: data.global_gains[global_index] if data.global_gains else None,
        set_fn=lambda client, value: client.set_global_gain(global_index, value),
        entity_category=EntityCategory.CONFIG,
    )


POWER_ON_DELAY = NadNumberDescription(
    key="power_on_delay",
    translation_key="power_on_delay",
    native_min_value=0,
    native_max_value=20,
    native_step=2,
    native_unit_of_measurement=UnitOfTime.SECONDS,
    device_class=NumberDeviceClass.DURATION,
    mode=NumberMode.BOX,
    entity_category=EntityCategory.CONFIG,
    value_fn=lambda data: data.power_on_delay,
    set_fn=lambda client, value: client.set_power_on_delay(int(value)),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = [output_gain(channel) for channel in range(1, CHANNEL_COUNT + 1)]
    descriptions += [input_gain(channel) for channel in range(1, CHANNEL_COUNT + 1)]
    descriptions += [global_gain(global_index) for global_index in range(GLOBAL_COUNT)]
    descriptions.append(POWER_ON_DELAY)
    async_add_entities(NadNumber(coordinator, description) for description in descriptions)


class NadNumber(NadEntity, NumberEntity):
    entity_description: NadNumberDescription

    def __init__(self, coordinator: NadCoordinator, description: NadNumberDescription):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def name(self):
        if self.entity_description.name_fn:
            return self.entity_description.name_fn(self.coordinator.data)
        return super().name

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(self.entity_description.set_fn(self.coordinator.client, value))
