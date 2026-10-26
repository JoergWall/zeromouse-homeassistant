"""The ZeroMOUSE integration."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ZeroMouseApi, ZeroMouseAuthError, ZeroMouseError
from .const import DOMAIN
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .frontend import async_setup_frontend
from .realtime import ZeroMouseRealtime
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the service actions, the dashboard cards and their backend."""
    async_setup_services(hass)
    await async_setup_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZeroMouseConfigEntry) -> bool:
    """Set up ZeroMOUSE from a config entry."""
    session = async_get_clientsession(hass)
    api = ZeroMouseApi(
        session,
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        executor=hass.async_add_executor_job,
    )
    try:
        await api.async_login()
    except ZeroMouseAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="auth_failed",
            translation_placeholders={"error": str(err)},
        ) from err
    except ZeroMouseError as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"error": str(err)},
        ) from err

    coordinator = ZeroMouseCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    realtime = ZeroMouseRealtime(session, api, coordinator.async_handle_realtime_event)
    entry.async_create_background_task(
        hass, realtime.run(), f"zeromouse_realtime_{entry.entry_id}"
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZeroMouseConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ZeroMouseConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow removing a device only if it is no longer part of the account."""
    return not any(
        domain == DOMAIN and ident in entry.runtime_data.data
        for domain, ident in device_entry.identifiers
    )
