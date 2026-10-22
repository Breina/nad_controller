"""Identify and restart the NAD amplifier."""
from __future__ import annotations

import asyncio

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import NadConfigEntry, NadCoordinator
from .entity import NadEntity
from .nad_client import NadError

PARALLEL_UPDATES = 0
IDENTIFY_SECONDS = 10

IDENTIFY = ButtonEntityDescription(
    key="identify",
    device_class=ButtonDeviceClass.IDENTIFY,
    entity_category=EntityCategory.DIAGNOSTIC,
)
RESTART = ButtonEntityDescription(
    key="restart",
    device_class=ButtonDeviceClass.RESTART,
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: NadConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([NadButton(coordinator, IDENTIFY), NadButton(coordinator, RESTART)])


class NadButton(NadEntity, ButtonEntity):

    def __init__(self, coordinator: NadCoordinator, description: ButtonEntityDescription):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        client = self.coordinator.client
        try:
            if self.entity_description.key == RESTART.key:
                await client.reboot()
                return
            await client.led_flash(True)
        except NadError as ex:
            raise HomeAssistantError(str(ex)) from ex

        # Stop flashing the front LED after a while, without holding up the service call
        self.coordinator.config_entry.async_create_background_task(
            self.hass, self._stop_flashing(), "nad_controller_identify"
        )

    async def _stop_flashing(self) -> None:
        await asyncio.sleep(IDENTIFY_SECONDS)
        try:
            await self.coordinator.client.led_flash(False)
        except NadError:
            pass
