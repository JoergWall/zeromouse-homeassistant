"""Config flow for ZeroMOUSE."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ZeroMouseApi, ZeroMouseAuthError, ZeroMouseError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

EMAIL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
)
PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)
# voluptuous works on every supported version; Home Assistant 2026.10 types the
# schema parameters with the API compatible probatio, hence ``Any``.
USER_SCHEMA: Any = vol.Schema(
    {
        vol.Required(CONF_EMAIL): EMAIL_SELECTOR,
        vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR,
    }
)
PASSWORD_SCHEMA: Any = vol.Schema({vol.Required(CONF_PASSWORD): PASSWORD_SELECTOR})


class ZeroMouseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZeroMOUSE."""

    VERSION = 1

    async def _async_validate(
        self, email: str, password: str
    ) -> tuple[str | None, dict[str, str]]:
        """Log in and read the device list; return (owner id, errors)."""
        api = ZeroMouseApi(
            async_get_clientsession(self.hass),
            email,
            password,
            executor=self.hass.async_add_executor_job,
        )
        try:
            await api.async_login()
            await api.async_get_devices()
        except ZeroMouseAuthError:
            return None, {"base": "invalid_auth"}
        except ZeroMouseError:
            _LOGGER.exception("Cannot connect to ZeroMOUSE")
            return None, {"base": "cannot_connect"}
        return api.owner_id, {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the app credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            owner_id, errors = await self._async_validate(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if owner_id:
                await self.async_set_unique_id(owner_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL], data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            owner_id, errors = await self._async_validate(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if owner_id:
                await self.async_set_unique_id(owner_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=PASSWORD_SCHEMA,
            description_placeholders={"email": entry.data[CONF_EMAIL]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change email or password of the same account."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            owner_id, errors = await self._async_validate(
                user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if owner_id:
                await self.async_set_unique_id(owner_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry, title=user_input[CONF_EMAIL], data_updates=user_input
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or {CONF_EMAIL: entry.data[CONF_EMAIL]}
            ),
            errors=errors,
        )
