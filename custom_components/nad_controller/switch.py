"""Global inputs and green mode of the NAD amplifier."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import GLOBAL_COUNT, NadClient, NadState

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class NadSwitchDescription(SwitchEntityDescription):
    value_fn: Callable[[NadState], bool | None]
    set_fn: Callable[[NadClient, bool], Awaitable[None]]
    name_fn: Callable[[NadState], str] | None = None


def global_input(global_index: int) -> NadSwitchDescription:
    return NadSwitchDescription(
        key=f"global_{'ab'[global_index]}",
        name_fn=lambda data: data.global_names[global_index],
        value_fn=lambda data: data.global_enabled[global_index] if data.global_enabled else None,
        set_fn=lambda client, on: client.set_global_enabled(global_index, on),
    )


GREEN_MODE = NadSwitchDescription(
    key="green_mode",
    translation_key="green_mode",
    entity_category=EntityCategory.CONFIG,
    value_fn=lambda data: data.green_mode,
    set_fn=lambda client, on: client.set_green_mode(on),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = [global_input(global_index) for global_index in range(GLOBAL_COUNT)]
    descriptions.append(GREEN_MODE)
    async_add_entities(NadSwitch(coordinator, description) for description in descriptions)


class NadSwitch(NadEntity, SwitchEntity):
    entity_description: NadSwitchDescription

    def __init__(self, coordinator: NadCoordinator, description: NadSwitchDescription):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def name(self):
        if self.entity_description.name_fn:
            return self.entity_description.name_fn(self.coordinator.data)
        return super().name

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.entity_description.set_fn(self.coordinator.client, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(self.entity_description.set_fn(self.coordinator.client, False))
