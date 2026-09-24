"""Event gallery support: websocket API, image proxy and the Lovelace card."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http.server import StaticPathConfig
from homeassistant.components.websocket_api import async_register_command
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.components.websocket_api.decorators import (
    async_response,
    websocket_command,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.util import dt as dt_util

from .api import ZeroMouseError, event_image_index, parse_event_time
from .const import DOMAIN
from .coordinator import ZeroMouseCoordinator

STATIC_URL = "/zeromouse_static"
CARD_FILE = "zeromouse-events-card.js"
CARD_VERSION = "7"
IMAGE_CACHE_SIZE = 400


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register the card, the image view and the websocket command once."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILE}?v={CARD_VERSION}")
    hass.http.register_view(ZeroMouseImageView())
    async_register_command(hass, ws_events)


def _coordinators(hass: HomeAssistant) -> dict[str, ZeroMouseCoordinator]:
    return {
        entry.entry_id: entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    }


def _serialize(
    entry_id: str,
    coordinator: ZeroMouseCoordinator,
    device_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    device = coordinator.data[device_id]
    when = parse_event_time(event)
    images = sorted(
        {int(i["imageIndex"]) for i in event.get("images") or [] if i and i.get("imageIndex") is not None}
    )
    return {
        "entry_id": entry_id,
        "device_id": device_id,
        "device_name": device.name,
        "event_id": event.get("eventID"),
        "classification": event.get("classification_byNet"),
        "time": when.isoformat() if when else None,
        "cat": device.event_cat(event),
        "images": images,
        "title_image": event_image_index(event),
        "is_hidden": bool(event.get("isHidden")),
        "is_favorite": bool(event.get("isFavorite")),
    }


@websocket_command(
    {
        vol.Required("type"): "zeromouse/events",
        vol.Optional("limit", default=10): vol.All(int, vol.Range(min=1, max=1000)),
        vol.Optional("device_id"): str,
        # With "since" all events after that time are returned (up to "limit")
        vol.Optional("since"): cv.datetime,
    }
)
@async_response
async def ws_events(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return the newest events of all (or one) ZeroMOUSE devices."""
    result: list[dict[str, Any]] = []
    try:
        for entry_id, coordinator in _coordinators(hass).items():
            for device_id in coordinator.data:
                if msg.get("device_id") not in (None, device_id):
                    continue
                if "since" in msg:
                    events = await coordinator.api.async_get_events_since(
                        device_id, dt_util.as_utc(msg["since"]), msg["limit"]
                    )
                else:
                    events = await coordinator.api.async_get_events(
                        device_id, min(msg["limit"], 100)
                    )
                result.extend(
                    _serialize(entry_id, coordinator, device_id, e) for e in events
                )
    except ZeroMouseError as err:
        connection.send_error(msg["id"], "zeromouse_error", str(err))
        return
    result.sort(key=lambda e: e["time"] or "", reverse=True)
    connection.send_result(msg["id"], {"events": result[: msg["limit"]]})


class ZeroMouseImageView(HomeAssistantView):
    """Proxy for event images (S3 needs AWS credentials)."""

    url = "/api/zeromouse/image/{entry_id}/{device_id}/{event_id}/{index}"
    name = "api:zeromouse:image"
    requires_auth = True

    def __init__(self) -> None:
        """Initialize."""
        self._cache: OrderedDict[tuple[str, str, int], bytes] = OrderedDict()

    @callback
    def _remember(self, key: tuple[str, str, int], data: bytes) -> None:
        self._cache[key] = data
        while len(self._cache) > IMAGE_CACHE_SIZE:
            self._cache.popitem(last=False)

    async def get(
        self,
        request: web.Request,
        entry_id: str,
        device_id: str,
        event_id: str,
        index: str,
    ) -> web.Response:
        """Return one JPEG."""
        coordinator = _coordinators(request.app[KEY_HASS]).get(entry_id)
        if coordinator is None or device_id not in coordinator.data:
            return web.Response(status=404)
        try:
            key = (device_id, event_id, int(index))
        except ValueError:
            return web.Response(status=400)
        data = self._cache.get(key)
        if data is None:
            try:
                data = await coordinator.api.async_get_event_image(*key)
            except ZeroMouseError:
                return web.Response(status=502)
            if data is None:
                return web.Response(status=404)
            self._remember(key, data)
        else:
            self._cache.move_to_end(key)
        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=604800, immutable"},
        )
