"""Polls the NAD amplifier for all entities at once."""
from __future__ import annotations

import logging
from collections.abc import Awaitable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, REFRESH_COOLDOWN, SCAN_INTERVAL
from .nad_client import NadClient, NadError, NadIdentity, NadState

_LOGGER = logging.getLogger(__name__)

type NadConfigEntry = ConfigEntry[NadCoordinator]


class NadCoordinator(DataUpdateCoordinator[NadState]):
    config_entry: NadConfigEntry

    def __init__(self, hass: HomeAssistant, entry: NadConfigEntry, client: NadClient, identity: NadIdentity):
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            # Refresh soon after commands, while still collapsing bursts such as a dragged volume slider
            request_refresh_debouncer=Debouncer(hass, _LOGGER, cooldown=REFRESH_COOLDOWN, immediate=False),
        )
        self.client = client
        self.identity = identity
        self.device_id: str | None = None
        self._web_api_down = False

    async def _async_update_data(self) -> NadState:
        try:
            state = await self.client.read_state()
        except NadError as ex:
            if self.data is None:
                raise UpdateFailed(f"Could not read the amplifier's web API: {ex}") from ex
            if not self._web_api_down:
                _LOGGER.warning("Web API of %s unavailable, falling back to IP control: %s", self.client.host, ex)
                self._web_api_down = True
            try:
                return await self.client.read_state_over_tcp(self.data)
            except NadError as tcp_ex:
                raise UpdateFailed(f"Could not reach the amplifier: {tcp_ex}") from tcp_ex

        if self._web_api_down:
            _LOGGER.info("Web API of %s is back", self.client.host)
            self._web_api_down = False
        return state

    async def async_command(self, command: Awaitable) -> None:
        """Run a command, then refresh so every entity reflects the amplifier's own view of the result."""
        try:
            await command
        except NadError as ex:
            raise HomeAssistantError(str(ex)) from ex
        await self.async_request_refresh()
