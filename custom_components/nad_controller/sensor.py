"""Temperatures, fans and status of the NAD amplifier."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import NadState, Temperature

PARALLEL_UPDATES = 0
UNITS = {"C": UnitOfTemperature.CELSIUS, "F": UnitOfTemperature.FAHRENHEIT}
SIDES = ["left", "right"]


@dataclass(frozen=True, kw_only=True)
class NadSensorDescription(SensorEntityDescription):
    value_fn: Callable[[NadState], str | float | None]
    temperature_fn: Callable[[NadState], Temperature | None] | None = None


def nth(values: list, index: int):
    return values[index] if index < len(values) else None


def heatsink_temperature(index: int) -> NadSensorDescription:
    return NadSensorDescription(
        key=f"temperature_{SIDES[index]}",
        translation_key=f"temperature_{SIDES[index]}",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        temperature_fn=lambda data: nth(data.temperatures, index),
        value_fn=lambda data: None,
    )


def fan_speed(index: int) -> NadSensorDescription:
    return NadSensorDescription(
        key=f"fan_{SIDES[index]}",
        translation_key=f"fan_{SIDES[index]}",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: nth(data.fan_speeds, index),
    )


SENSORS = [
    heatsink_temperature(0),
    heatsink_temperature(1),
    NadSensorDescription(
        key="temperature_internal",
        translation_key="temperature_internal",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        temperature_fn=lambda data: data.inner_temperature,
        value_fn=lambda data: None,
    ),
    fan_speed(0),
    fan_speed(1),
    NadSensorDescription(
        key="fan_speed_method",
        translation_key="fan_speed_method",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.fan_speed_method,
    ),
    NadSensorDescription(
        key="amp_status",
        translation_key="amp_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.amp_status,
    ),
]


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(NadSensor(coordinator, description) for description in SENSORS)


class NadSensor(NadEntity, SensorEntity):
    entity_description: NadSensorDescription

    def __init__(self, coordinator: NadCoordinator, description: NadSensorDescription):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def _temperature(self) -> Temperature | None:
        temperature_fn = self.entity_description.temperature_fn
        # In standby the heatsinks read 0 degrees and the internal sensor 'NC'
        if not temperature_fn or not self.coordinator.data.power:
            return None
        return temperature_fn(self.coordinator.data)

    @property
    def native_value(self) -> str | float | None:
        if self.entity_description.temperature_fn:
            temperature = self._temperature
            return temperature.value if temperature else None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.temperature_fn:
            # The amplifier reports in whichever unit its web UI is set to
            temperature = self._temperature
            return UNITS[temperature.unit] if temperature else UnitOfTemperature.CELSIUS
        return None
