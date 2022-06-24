"""Config flow for NAD Cl-16-60 home audio controller integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant import config_entries, core, exceptions
from homeassistant.const import CONF_HOST
from nad_client import NadClient
from const import DOMAIN

DATA_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: core.HomeAssistant, data):
    """Validate the user input allows us to connect.
    Data has the keys from DATA_SCHEMA with values provided by the user.
    """
    try:
        NadClient(data[CONF_HOST]).get_device_name()
    except Exception as err:
        _LOGGER.error("Error connecting to NAD controller")
        raise CannotConnect from err

    # Return info that you want to store in the config entry.
    return {CONF_HOST: data[CONF_HOST]}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NAD Cl-16-60 home audio controller."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                return self.async_create_entry(title=user_input[CONF_HOST], data=info)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )


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
