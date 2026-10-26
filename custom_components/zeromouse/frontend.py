"""Event gallery support: websocket API, image proxy and the Lovelace card."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import logging
from pathlib import Path
import re
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.auth.permissions.const import POLICY_READ
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
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.util import dt as dt_util

from .api import ZeroMouseError, event_image_index, event_rating, parse_event_time
from .const import DOMAIN, classification_group
from .coordinator import ZeroMouseCoordinator
from .correlation import (
    DEFAULT_WINDOW_AFTER,
    DEFAULT_WINDOW_BEFORE,
    PRESET_NAMES,
    SOURCE_ATTRIBUTE,
    SOURCE_EVENT,
    SOURCE_STATE,
    async_correlate,
)
from .pager import FILTER_GROUPS, DeviceStream, EventFilter, EventPager, PagerStore

_LOGGER = logging.getLogger(__name__)

STATIC_URL = "/zeromouse_static"
CARD_FILE = "zeromouse-events-card.js"
IMAGE_CACHE_SIZE = 400
# Event ids are UUIDs; anything else never reaches the S3 key
_EVENT_ID = re.compile(r"[0-9A-Za-z-]{1,64}")
DATA_PAGERS = f"{DOMAIN}_pagers"


def _file_version(path: Path) -> str:
    """Short content hash: browsers fetch the card again whenever it changes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Register the card, the image view and the websocket command once."""
    www = Path(__file__).parent / "www"
    version = await hass.async_add_executor_job(_file_version, www / CARD_FILE)
    # The URL carries the content hash, so the file may be cached for long
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(www), True)]
    )
    add_extra_js_url(hass, f"{STATIC_URL}/{CARD_FILE}?v={version}")
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
    ha_device_id: str | None,
) -> dict[str, Any]:
    device = coordinator.data.get(device_id)
    when = parse_event_time(event)
    images = sorted(
        {
            int(i["imageIndex"])
            for i in event.get("images") or []
            if i and i.get("imageIndex") is not None
        }
    )
    return {
        "entry_id": entry_id,
        "device_id": device_id,
        "ha_device_id": ha_device_id,
        "device_name": device.name if device else device_id,
        "event_id": event.get("eventID"),
        "classification": event.get("classification_byNet"),
        "group": classification_group(event.get("classification_byNet")),
        "time": when.isoformat() if when else None,
        "cat": device.event_cat(event) if device else None,
        "images": images,
        "title_image": event_image_index(event),
        "is_hidden": bool(event.get("isHidden")),
        "is_favorite": bool(event.get("isFavorite")),
        "rating": event_rating(event),
    }


CORRELATE_SCHEMA = vol.Schema(
    {
        # Without entity the entry only names a cat that ZeroMOUSE recognises
        vol.Optional("entity"): cv.entity_id,
        vol.Optional("name"): cv.string,
        vol.Optional("preset", default="auto"): vol.In(PRESET_NAMES),
        vol.Optional("source"): vol.In([SOURCE_ATTRIBUTE, SOURCE_STATE, SOURCE_EVENT]),
        vol.Optional("time_attribute"): vol.Any(None, cv.string),
        vol.Optional("direction_attribute"): vol.Any(None, cv.string),
        vol.Optional("in"): [vol.Any(cv.string, int, float, bool)],
        vol.Optional("out"): [vol.Any(cv.string, int, float, bool)],
        # Only states whose attributes have these values, e.g. {rfidCode: "900..."}
        vol.Optional("filter"): {
            cv.string: vol.Any(
                cv.string, int, float, bool, [vol.Any(cv.string, int, float, bool)]
            )
        },
    },
    # Cards pass their display options (icon, color) along
    extra=vol.ALLOW_EXTRA,
)


# voluptuous works on every supported version (see services.py for the cast)
WS_EVENTS_SCHEMA: dict[Any, Any] = (
    {
        vol.Required("type"): "zeromouse/events",
        vol.Optional("limit", default=10): vol.All(int, vol.Range(min=1, max=1000)),
        # Continue a previous list ("load more")
        vol.Optional("cursor"): cv.string,
        # False: the caller will not load more (e.g. a refresh), keep no cursor
        vol.Optional("keep_cursor", default=True): cv.boolean,
        # The caller's previous lists, no longer needed
        vol.Optional("release"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("device_id"): cv.string,
        # Only events after this time; the list ends there
        vol.Optional("since"): cv.datetime,
        # App filters: clean, prey, undecidable, hand, out (empty = default view)
        vol.Optional("classifications", default=[]): [vol.In(list(FILTER_GROUPS))],
        vol.Optional("favorites_only", default=False): cv.boolean,
        vol.Optional("include_hidden", default=False): cv.boolean,
        vol.Optional("correlate", default=[]): [CORRELATE_SCHEMA],
        vol.Optional("window_before", default=DEFAULT_WINDOW_BEFORE): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=3600)
        ),
        vol.Optional("window_after", default=DEFAULT_WINDOW_AFTER): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=3600)
        ),
    }
)


@websocket_command(WS_EVENTS_SCHEMA)
@async_response
async def ws_events(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return events of all (or one) ZeroMOUSE devices, filtered and paged."""
    user_id = connection.user.id if connection.user else None
    for config in msg["correlate"]:
        if "entity" in config and not connection.user.permissions.check_entity(
            config["entity"], POLICY_READ
        ):
            connection.send_error(msg["id"], "unauthorized", config["entity"])
            return

    store: PagerStore = hass.data.setdefault(DATA_PAGERS, PagerStore())
    for old in msg.get("release", []):
        store.release(old, user_id)
    cursor: str | None = msg.get("cursor")
    if cursor:
        pager = store.get(cursor, user_id)
        if pager is None:
            connection.send_error(msg["id"], "invalid_cursor", "List expired, reload")
            return
    else:
        event_filter = EventFilter(
            groups=frozenset(msg["classifications"]),
            favorites_only=msg["favorites_only"],
            include_hidden=msg["include_hidden"],
            since=dt_util.as_utc(msg["since"]) if "since" in msg else None,
        )
        streams = [
            DeviceStream(entry_id, device_id, coordinator.api, event_filter)
            for entry_id, coordinator in _coordinators(hass).items()
            for device_id in coordinator.data
            if msg.get("device_id") in (None, device_id)
        ]
        pager = EventPager(streams, user_id)
        cursor = None

    try:
        page = await pager.async_next(msg["limit"])
    except ZeroMouseError as err:
        connection.send_error(msg["id"], "zeromouse_error", str(err))
        return

    try:
        events = _serialize_page(hass, page)
    except Exception:
        # Keep the list consistent: the next call delivers this page again
        pager.give_back(page)
        raise

    # has_more also without cursor: a refresh can see that it missed events
    result: dict[str, Any] = {"events": events, "cursor": None, "has_more": pager.has_more}
    if pager.has_more and (cursor or msg["keep_cursor"]):
        result["cursor"] = cursor or store.add(pager)
    elif cursor:
        store.remove(cursor)

    # Always match: cats recognised by ZeroMOUSE need no flap configuration
    to_match = [
        {**e, "time": dt_util.parse_datetime(e["time"]) if e["time"] else None}
        for e in events
    ]
    try:
        matches, error = await async_correlate(
            hass,
            to_match,
            [config for config in msg["correlate"] if "entity" in config],
            msg["window_before"],
            msg["window_after"],
        )
    except Exception:
        _LOGGER.exception("Matching ZeroMOUSE events with cat flap passages failed")
        matches, error = {}, "correlation_failed"
    for event in events:
        event["match"] = matches.get(str(event["event_id"]))
    if error:
        result["correlation_error"] = error
    connection.send_result(msg["id"], result)


def _serialize_page(
    hass: HomeAssistant, page: list[tuple[DeviceStream, dict[str, Any]]]
) -> list[dict[str, Any]]:
    registry = dr.async_get(hass)
    coordinators = _coordinators(hass)
    events = []
    for stream, event in page:
        coordinator = coordinators.get(stream.entry_id)
        if coordinator is None:
            continue
        device = registry.async_get_device_by_identifier(
            (DOMAIN, stream.device_id), stream.entry_id
        )
        events.append(
            _serialize(
                stream.entry_id,
                coordinator,
                stream.device_id,
                event,
                device.id if device else None,
            )
        )
    return events


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
        if not _EVENT_ID.fullmatch(event_id):
            return web.Response(status=400)
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
