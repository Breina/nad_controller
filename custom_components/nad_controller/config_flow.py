"""Config flow for NAD multi-room audio controller integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.ssdp import ATTR_UPNP_FRIENDLY_NAME, SsdpServiceInfo

from .const import CONF_MODEL, CONF_SERIAL_NUMBER, DOMAIN
from .nad_client import DEFAULT_TCP_PORT, NadClient, NadError, NadIdentity

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_IP_ADDRESS): str,
    vol.Optional(CONF_PORT, default=DEFAULT_TCP_PORT): cv.port
})

_LOGGER = logging.getLogger(__name__)


class NetworkFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NAD multi-room audio controller."""

    VERSION = 1

    def __init__(self) -> None:
        self.ip: str | None = None
        self.port: int = DEFAULT_TCP_PORT
        self.identity: NadIdentity | None = None

    async def _async_identify(self) -> NadIdentity:
        client = NadClient(self.ip, async_get_clientsession(self.hass), self.port)
        return await client.get_identity()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            self.ip = user_input[CONF_IP_ADDRESS]
            self.port = user_input.get(CONF_PORT, DEFAULT_TCP_PORT)
            try:
                self.identity = await self._async_identify()
            except NadError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self._async_set_unique_id()
                return self._async_create()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(DATA_SCHEMA, user_input),
            errors=errors,
            last_step=True,
        )

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> ConfigFlowResult:
        """Handle a NAD controller discovered over SSDP."""
        self.ip = str(urlparse(discovery_info.ssdp_location).hostname)
        try:
            self.identity = await self._async_identify()
        except NadError:
            return self.async_abort(reason="cannot_connect")

        await self._async_set_unique_id({CONF_IP_ADDRESS: self.ip})

        self.context["title_placeholders"] = {
            "name": self.identity.name or discovery_info.upnp.get(ATTR_UPNP_FRIENDLY_NAME, self.ip)
        }
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Allow the user to confirm adding the device."""
        if user_input is not None:
            return self._async_create()

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self.identity.name, "ip": self.ip},
            last_step=True,
        )

    async def _async_set_unique_id(self, updates: dict[str, Any] | None = None) -> None:
        if not self.identity.serial_number:
            self._async_abort_entries_match({CONF_IP_ADDRESS: self.ip, CONF_PORT: self.port})
            return
        await self.async_set_unique_id(self.construct_unique_id(self.identity.model, self.identity.serial_number))
        # A known amplifier that got a new address is followed rather than added twice
        self._abort_if_unique_id_configured(updates=updates or {CONF_IP_ADDRESS: self.ip, CONF_PORT: self.port})

    def _async_create(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self.identity.name or self.ip,
            data={
                CONF_IP_ADDRESS: self.ip,
                CONF_PORT: self.port,
                CONF_MODEL: self.identity.model,
                CONF_SERIAL_NUMBER: self.identity.serial_number,
            },
        )

    @staticmethod
    def construct_unique_id(model_name: str, serial_number: str) -> str:
        """Construct the unique id from the ssdp discovery or user_step."""
        return f"{model_name}-{serial_number}"
