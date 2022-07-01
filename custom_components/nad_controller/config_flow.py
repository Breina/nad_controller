"""Config flow for NAD Cl-16-60 home audio controller integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import core, exceptions
from homeassistant.components import ssdp
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_MODEL
from homeassistant.data_entry_flow import FlowResult

from .nad_client import NadClient, DEFAULT_TCP_PORT

DOMAIN = "nad_controller"

NAD_OBJECT = "nad_object"
UNDO_UPDATE_LISTENER = "update_update_listener"

DATA_NAD = "nad_data"
DATA_NAD_DISCOVERY_MANAGER = "nad_discovery_manager"
MANUFACTURER = "Lenbrook Industries"
MODEL = "DSP16-60"
UDN_PREFIX = "uuid:NAD_CI 16-60_"

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT): int
})

_LOGGER = logging.getLogger(__name__)

CONF_SERIAL_NUMBER = "serial_number"


async def async_step_init(
        self, user_input: dict[str, Any] | None = None
) -> FlowResult:
    """Manage the options."""
    if user_input is not None:
        return self.async_create_entry(title="", data=user_input)

    return self.async_show_form(step_id="init", data_schema=DATA_SCHEMA)


class NetworkFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NAD Cl-16-60 home audio controller."""

    VERSION = 1

    def __init__(self):
        self.serial_number = None
        self.udn = None
        self.host = None
        self.port = None
        self.model_name = None

    async def async_step_user(self, user_input=None):
        _LOGGER.info("Entering async step user")
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                self.host = user_input.get("host")
                self.port = user_input.get("port", DEFAULT_TCP_PORT)
                # return self.async_create_entry(title=user_input[CONF_HOST], data=info)
                return await self.async_step_connect()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        _LOGGER.info("Going to async_show_form")
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )

    async def async_step_confirm(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        _LOGGER.info("async_step_confirm")
        """Allow the user to confirm adding the device."""
        if user_input is not None:
            return await self.async_step_connect()

        self._set_confirm_only()
        _LOGGER.info("Going to async_show_form")
        return self.async_show_form(step_id="confirm")

    async def async_step_connect(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        _LOGGER.info("Entering async_step_connect")
        """Connect to the controller."""
        try:
            client = NadClient(self.host, self.port)
        except (Exception):
            return self.async_abort(reason="cannot_connect")

        if not self.serial_number:
            self.serial_number = client.get_serial_number()
        if not self.model_name:
            self.model_name = client.get_device_model()

        if self.serial_number is not None:
            unique_id = self.construct_unique_id(self.model_name, self.serial_number)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
        else:
            _LOGGER.error(
                "Could not get serial number of host %s, "
                "unique_id's will not be available",
                self.host,
            )
            self._async_abort_entries_match({CONF_HOST: self.host, CONF_PORT: self.port})

        _LOGGER.info("Going to async_create_entry")
        return self.async_create_entry(
            title=client.get_project_name(),
            data={
                CONF_HOST: self.host,
                CONF_PORT: self.port,
                CONF_MODEL: self.model_name,
                CONF_SERIAL_NUMBER: self.serial_number,
            },
        )

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        _LOGGER.info("Entering async_step_ssdp")
        """Handle a discovered Denon AVR.
        This flow is triggered by the SSDP component. It will check if the
        host is already configured and delegate to the import step if not.
        """
        # Check if required information is present to set the unique_id
        if (
                ssdp.ATTR_UPNP_MODEL_NAME not in discovery_info.upnp
                or ssdp.ATTR_UPNP_UDN not in discovery_info.upnp
        ):
            return self.async_abort(reason="not_nad_missing")

        self.model_name = discovery_info.upnp[ssdp.ATTR_UPNP_MODEL_NAME]
        self.udn = discovery_info.upnp[ssdp.ATTR_UPNP_UDN]
        self.host = urlparse(discovery_info.ssdp_location).hostname

        await self.async_set_unique_id(self.udn)
        self._abort_if_unique_id_configured({CONF_HOST: self.host})

        _LOGGER.info("Going to context.update")
        self.context.update(
            {
                "title_placeholders": {
                    "name": discovery_info.upnp.get(
                        ssdp.ATTR_UPNP_FRIENDLY_NAME, self.host
                    )
                }
            }
        )

        return await self.async_step_confirm()

    @staticmethod
    def construct_unique_id(model_name: str, serial_number: str) -> str:
        """Construct the unique id from the ssdp discovery or user_step."""
        return f"{model_name}-{serial_number}"


@core.callback
def _key_for_source(index, source, previous_sources):
    _LOGGER.info("Entering _key_for_source")
    if str(index) in previous_sources:
        key = vol.Optional(
            source, description={"suggested_value": previous_sources[str(index)]}
        )
    else:
        key = vol.Optional(source)

    return key


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
