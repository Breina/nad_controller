"""Config flow for NAD multi-room audio controller integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant import core, exceptions, data_entry_flow
from homeassistant.components import ssdp
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, CONF_MODEL
from homeassistant.data_entry_flow import FlowResult, AbortFlow

from .nad_client import NadClient, DEFAULT_TCP_PORT

DOMAIN = "nad_controller"

NAD_OBJECT = "nad_object"
UNDO_UPDATE_LISTENER = "update_update_listener"

DATA_NAD = "nad_data"
DATA_NAD_DISCOVERY_MANAGER = "nad_discovery_manager"
MANUFACTURER = "Lenbrook Industries"
UDN_PREFIX = "uuid:NAD_CI 16-60_"

DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_IP_ADDRESS): str,
    vol.Optional(CONF_PORT, default=DEFAULT_TCP_PORT): cv.port
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
    """Handle a config flow for NAD multi-room audio controller."""

    VERSION = 1

    def __init__(self):
        self.client = None
        self.serial_number = None
        self.udn = None
        self.ip = None
        self.port = None
        self.model_name = None

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                self.ip = user_input.get(CONF_IP_ADDRESS)
                self.port = user_input.get(CONF_PORT, DEFAULT_TCP_PORT)
                return await self.async_step_connect()
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except AbortFlow:
                errors["base"] = "already_in_progress"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors, last_step=True
        )

    async def async_step_confirm(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow the user to confirm adding the device."""
        if user_input is not None:
            return await self.async_step_connect()

        self._set_confirm_only()
        return self.async_show_form(step_id="confirm", last_step=True)

    async def async_step_connect(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Connect to the controller."""
        try:
            if self.client is None:
                self.client = NadClient(self.ip, self.port)
        except Exception as e:
            _LOGGER.exception(e)
            return self.async_abort(reason="cannot_connect")

        if not self.serial_number:
            self.serial_number = self.client.get_serial_number()
        if not self.model_name:
            self.model_name = self.client.get_device_model()

        if self.serial_number is not None:
            unique_id = self.construct_unique_id(self.model_name, self.serial_number)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
        else:
            _LOGGER.error(
                "Could not get serial number of ip %s, "
                "unique_id's will not be available",
                self.ip,
            )
            self._async_abort_entries_match({CONF_IP_ADDRESS: self.ip, CONF_PORT: self.port})

        return self.async_create_entry(
            title=self.client.get_device_name(),
            data={
                CONF_IP_ADDRESS: self.ip,
                CONF_PORT: self.port,
                CONF_MODEL: self.model_name,
                CONF_SERIAL_NUMBER: self.serial_number,
            },
        )

    async def async_step_ssdp(self, discovery_info: ssdp.SsdpServiceInfo) -> FlowResult:
        """Handle a discovered NAD controller.
        This flow is triggered by the SSDP component. It will check if the
        ip address is already configured and delegate to the import step if not.
        """
        # Check if required information is present to set the unique_id
        if (
                ssdp.ATTR_UPNP_MODEL_NAME not in discovery_info.upnp
                or ssdp.ATTR_UPNP_UDN not in discovery_info.upnp
        ):
            return self.async_abort(reason="not_nad_missing")

        self.model_name = discovery_info.upnp[ssdp.ATTR_UPNP_MODEL_NAME]
        self.udn = discovery_info.upnp[ssdp.ATTR_UPNP_UDN]
        self.ip = str(urlparse(discovery_info.ssdp_location).hostname)
        self.port = DEFAULT_TCP_PORT

        try:
            if self.client is None:
                self.client = NadClient(self.ip, self.port)
            self.model_name = self.client.get_device_model()
            self.serial_number = self.client.get_serial_number()
        except (Exception):
            return self.async_abort(reason="cannot_connect")

        await self.async_set_unique_id(self.construct_unique_id(self.model_name, self.serial_number))
        self._abort_if_unique_id_configured({CONF_IP_ADDRESS: self.ip})

        self.context.update(
            {
                "title_placeholders": {
                    "name": discovery_info.upnp.get(
                        ssdp.ATTR_UPNP_FRIENDLY_NAME, self.ip
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
    if str(index) in previous_sources:
        key = vol.Optional(
            source, description={"suggested_value": previous_sources[str(index)]}
        )
    else:
        key = vol.Optional(source)

    return key


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
