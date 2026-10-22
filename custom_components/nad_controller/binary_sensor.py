"""Signal and protection status per output channel of the NAD amplifier."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import CHANNEL_COUNT, NadState

PARALLEL_UPDATES = 0
STATUS_OK = "OK"


@dataclass(frozen=True, kw_only=True)
class NadBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[NadState], bool | None]
    name_fn: Callable[[NadState], str] | None = None


def signal(channel: int) -> NadBinarySensorDescription:
    return NadBinarySensorDescription(
        key=f"{channel}_signal",
        device_class=BinarySensorDeviceClass.SOUND,
        entity_registry_enabled_default=False,
        name_fn=lambda data: f"{data.output_names[channel - 1]} signal",
        value_fn=lambda data: data.signals[channel - 1] if channel <= len(data.signals) else None,
    )


def protection(channel: int) -> NadBinarySensorDescription:
    return NadBinarySensorDescription(
        key=f"{channel}_protection",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        name_fn=lambda data: f"{data.output_names[channel - 1]} protection",
        value_fn=lambda data: data.protection[channel - 1] != STATUS_OK if channel <= len(data.protection) else None,
    )


AMP_PROBLEM = NadBinarySensorDescription(
    key="amp_problem",
    translation_key="amp_problem",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: data.amp_status != STATUS_OK if data.amp_status else None,
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    descriptions = [AMP_PROBLEM]
    descriptions += [signal(channel) for channel in range(1, CHANNEL_COUNT + 1)]
    descriptions += [protection(channel) for channel in range(1, CHANNEL_COUNT + 1)]
    async_add_entities(NadBinarySensor(coordinator, description) for description in descriptions)


class NadBinarySensor(NadEntity, BinarySensorEntity):
    entity_description: NadBinarySensorDescription

    def __init__(self, coordinator: NadCoordinator, description: NadBinarySensorDescription):
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
