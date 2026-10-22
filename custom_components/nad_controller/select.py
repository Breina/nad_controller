"""Power and input settings of the NAD amplifier."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import CHANNEL_COUNT, STANDBY_TIMES, NadClient, NadState, PowerMethod

PARALLEL_UPDATES = 0

POWER_METHODS = {
    PowerMethod.POWER_BUTTON: "power_button",
    PowerMethod.ALWAYS_ON: "always_on",
    PowerMethod.V12_TRIGGER: "trigger",
    PowerMethod.SIGNAL_SENSE: "signal_sense",
}
STANDBY_OPTIONS = {standby_time: standby_time.lower() for standby_time in STANDBY_TIMES}
INPUT_MODES = ["stereo", "mono"]


@dataclass(frozen=True, kw_only=True)
class NadSelectDescription(SelectEntityDescription):
    value_fn: Callable[[NadState], str | None]
    set_fn: Callable[[NadClient, str], Awaitable[None]]
    name_fn: Callable[[NadState], str] | None = None


def input_mode(pair: int) -> NadSelectDescription:
    """Stereo or summed-to-mono, per pair of inputs."""
    left = pair * 2 - 1
    return NadSelectDescription(
        key=f"input_{left}_{left + 1}_mode",
        translation_key="input_mode",
        options=INPUT_MODES,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        name_fn=lambda data: f"{data.input_names[left - 1]} / {data.input_names[left]} mode",
        value_fn=lambda data: data.stereo_mono[pair - 1] if pair <= len(data.stereo_mono) else None,
        set_fn=lambda client, option: client.set_stereo_mono(pair, option == "mono"),
    )


POWER_ON_METHOD = NadSelectDescription(
    key="power_on_method",
    translation_key="power_on_method",
    options=list(POWER_METHODS.values()),
    entity_category=EntityCategory.CONFIG,
    value_fn=lambda data: next((o for m, o in POWER_METHODS.items() if m.value == data.power_on_method), None),
    set_fn=lambda client, option: client.set_power_method(
        next(m for m, o in POWER_METHODS.items() if o == option)
    ),
)

STANDBY_TIME = NadSelectDescription(
    key="standby_time",
    translation_key="standby_time",
    options=list(STANDBY_OPTIONS.values()),
    entity_category=EntityCategory.CONFIG,
    value_fn=lambda data: STANDBY_OPTIONS.get(data.standby_time),
    set_fn=lambda client, option: client.set_standby_time(
        next(t for t, o in STANDBY_OPTIONS.items() if o == option)
    ),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = [POWER_ON_METHOD, STANDBY_TIME]
    descriptions += [input_mode(pair) for pair in range(1, CHANNEL_COUNT // 2 + 1)]
    async_add_entities(NadSelect(coordinator, description) for description in descriptions)


class NadSelect(NadEntity, SelectEntity):
    entity_description: NadSelectDescription

    def __init__(self, coordinator: NadCoordinator, description: NadSelectDescription):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def name(self):
        if self.entity_description.name_fn:
            return self.entity_description.name_fn(self.coordinator.data)
        return super().name

    @property
    def current_option(self) -> str | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(self.entity_description.set_fn(self.coordinator.client, option))
