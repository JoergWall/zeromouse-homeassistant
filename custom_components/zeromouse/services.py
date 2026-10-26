"""Service actions of the ZeroMOUSE integration."""

from __future__ import annotations

from typing import Any, cast

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .api import RATING_CORRECT, RATING_INCORRECT, ZeroMouseError
from .const import DOMAIN
from .coordinator import ZeroMouseCoordinator

SERVICE_RATE_EVENT = "rate_event"
SERVICE_DELETE_EVENT = "delete_event"

ATTR_DEVICE_ID = "device_id"
ATTR_EVENT_ID = "event_id"
ATTR_RATING = "rating"
RATING_NONE = "none"
RATINGS = [RATING_CORRECT, RATING_INCORRECT, RATING_NONE]

EVENT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_EVENT_ID): cv.string,
    }
)
RATE_SCHEMA = EVENT_SCHEMA.extend({vol.Required(ATTR_RATING): vol.In(RATINGS)})


def _resolve(hass: HomeAssistant, device_id: str) -> tuple[ZeroMouseCoordinator, str]:
    """Return coordinator and ZeroMOUSE device id of a Home Assistant device."""
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        cloud_id = next(
            (ident for domain, ident in device.identifiers if domain == DOMAIN), None
        )
        entry = hass.config_entries.async_get_entry(device.config_entry_id)
        if entry is not None and entry.domain == DOMAIN and cloud_id is not None:
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entry_not_loaded",
                    translation_placeholders={"device_id": device_id},
                )
            coordinator: ZeroMouseCoordinator = entry.runtime_data
            return coordinator, cloud_id
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="device_not_found",
        translation_placeholders={"device_id": device_id},
    )


async def _async_rate_event(call: ServiceCall) -> None:
    coordinator, cloud_id = _resolve(call.hass, call.data[ATTR_DEVICE_ID])
    try:
        rating = call.data[ATTR_RATING]
        await coordinator.api.async_rate_event(
            cloud_id, call.data[ATTR_EVENT_ID], None if rating == RATING_NONE else rating
        )
    except ZeroMouseError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="api_error",
            translation_placeholders={"error": str(err)},
        ) from err


async def _async_delete_event(call: ServiceCall) -> None:
    coordinator, cloud_id = _resolve(call.hass, call.data[ATTR_DEVICE_ID])
    try:
        await coordinator.api.async_delete_event(cloud_id, call.data[ATTR_EVENT_ID])
    except ZeroMouseError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="api_error",
            translation_placeholders={"error": str(err)},
        ) from err
    await coordinator.async_request_refresh()


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the service actions."""
    # voluptuous schemas work on every supported version; Home Assistant 2026.10
    # types the parameter with the API compatible probatio.
    hass.services.async_register(
        DOMAIN, SERVICE_RATE_EVENT, _async_rate_event, schema=cast(Any, RATE_SCHEMA)
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE_EVENT, _async_delete_event, schema=cast(Any, EVENT_SCHEMA)
    )
