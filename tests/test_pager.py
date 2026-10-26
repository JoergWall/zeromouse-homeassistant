"""Tests for filtered paging through events (gallery "load more")."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeromouse import pager as pager_mod
from custom_components.zeromouse.const import classification_group
from custom_components.zeromouse.pager import (
    DeviceStream,
    EventFilter,
    EventPager,
    PagerStore,
)
from homeassistant.core import HomeAssistant

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def make_events(prefix: str, count: int, start: datetime, step: int = 60, **extra: Any) -> list[dict]:
    """Events newest first, one every `step` seconds."""
    return [
        {
            "eventID": f"{prefix}{i}",
            "eventTime": int((start - timedelta(seconds=i * step)).timestamp()),
            "classification_byNet": "clean",
            **extra,
        }
        for i in range(count)
    ]


def paged_api(events: list[dict], page: int = 3) -> MagicMock:
    """API mock that serves `events` in pages."""
    api = MagicMock()

    async def get_page(device_id, token=None, limit=100, favorites=False):
        start = int(token or 0)
        items = [e for e in events if not favorites or e.get("isFavorite")]
        chunk = items[start : start + page]
        nxt = str(start + page) if start + page < len(items) else None
        return copy.deepcopy(chunk), nxt

    api.async_get_events_page = AsyncMock(side_effect=get_page)
    return api


def test_event_filter() -> None:
    """Test the app's filter semantics."""
    clean = {"classification_byNet": "clean"}
    hidden_out = {"classification_byNet": "out", "isHidden": 1}
    deleted = {"classification_byNet": "prey", "isDeleted": 1}
    favorite = {"classification_byNet": "undecidable", "isHidden": 1, "isFavorite": 1}

    default = EventFilter()
    assert default.matches(clean)
    assert not default.matches(hidden_out)
    assert not default.matches(deleted)
    assert EventFilter(include_hidden=True).matches(hidden_out)

    only_out = EventFilter(groups=frozenset({"out"}))
    assert only_out.matches(hidden_out) and not only_out.matches(clean)
    assert not only_out.matches(deleted | {"classification_byNet": "out"})

    favorites = EventFilter(groups=frozenset({"prey"}), favorites_only=True)
    assert favorites.matches(favorite)
    assert not favorites.matches(clean)


def ev(classification: str, **extra: Any) -> dict[str, Any]:
    """An event with a classification."""
    return {"classification_byNet": classification, **extra}


@pytest.mark.parametrize(
    ("classification", "hidden", "shown"),
    [
        # The app shows these hidden events in its unfiltered list
        ("early", 1, True),
        ("late", 1, True),
        ("undecidable", 1, True),
        ("clean", 0, True),
        ("prey", 0, True),
        ("test", 0, True),
        ("clean", 1, False),
        ("out", 1, False),
        ("free", 0, False),
    ],
)
def test_default_list_like_app(classification: str, hidden: int, shown: bool) -> None:
    """Test the list without filter: the app's buildFilter default."""
    assert EventFilter().matches(ev(classification, isHidden=hidden)) is shown


@pytest.mark.parametrize(
    ("group", "members"),
    [
        ("clean", {"clean", "early"}),
        ("prey", {"prey"}),
        ("undecidable", {"undecidable", "late", "unknown"}),
        ("hand", {"test", "hand"}),
        ("out", {"out"}),
    ],
)
def test_filter_groups_like_app(group: str, members: set[str]) -> None:
    """Test that each check box covers the app's classifications, hidden or not."""
    flt = EventFilter(groups=frozenset({group}))
    for classification in members:
        assert flt.matches(ev(classification, isHidden=1))
        assert classification_group(classification) == group
    others = {"clean", "early", "prey", "undecidable", "late", "unknown", "test", "out", "free"}
    for classification in others - members:
        assert not flt.matches(ev(classification))


def test_classification_group_none() -> None:
    """Test that values the app lists in no filter have no group."""
    assert classification_group("free") is None
    assert classification_group(None) is None


async def test_pager_single_device() -> None:
    """Test that pages continue exactly where the last one ended."""
    events = make_events("e", 8, T0)
    events[2]["isDeleted"] = 1
    stream = DeviceStream("entry", "dev", paged_api(events), EventFilter())
    pager = EventPager([stream], "user")

    first = await pager.async_next(4)
    assert [e["eventID"] for _, e in first] == ["e0", "e1", "e3", "e4"]
    assert pager.has_more
    second = await pager.async_next(4)
    assert [e["eventID"] for _, e in second] == ["e5", "e6", "e7"]
    assert not pager.has_more


async def test_pager_merges_devices_in_order() -> None:
    """Test the time ordered merge of several devices."""
    a = make_events("a", 5, T0, step=100)  # a0 .. a4 every 100 s
    b = make_events("b", 5, T0 - timedelta(seconds=50), step=100)  # in between
    pager = EventPager(
        [
            DeviceStream("entry", "A", paged_api(a, page=2), EventFilter()),
            DeviceStream("entry", "B", paged_api(b, page=2), EventFilter()),
        ],
        None,
    )
    ids: list[str] = []
    while pager.has_more:
        ids += [e["eventID"] for _, e in await pager.async_next(3)]
    assert ids == ["a0", "b0", "a1", "b1", "a2", "b2", "a3", "b3", "a4", "b4"]


async def test_pager_since_and_favorites() -> None:
    """Test the time limit and the favourites index."""
    events = make_events("e", 6, T0, step=3600)
    events[1]["isFavorite"] = 1
    events[4]["isFavorite"] = 1
    since = EventFilter(since=T0 - timedelta(hours=2, minutes=30))
    pager = EventPager([DeviceStream("x", "d", paged_api(events), since)], None)
    assert [e["eventID"] for _, e in await pager.async_next(100)] == ["e0", "e1", "e2"]
    assert not pager.has_more

    favorites = EventFilter(favorites_only=True)
    api = paged_api(events)
    pager = EventPager([DeviceStream("x", "d", api, favorites)], None)
    assert [e["eventID"] for _, e in await pager.async_next(100)] == ["e1", "e4"]
    assert api.async_get_events_page.await_args.kwargs["favorites"] is True


async def test_pager_request_cap() -> None:
    """Test that a rare filter stops after the request cap and can continue."""
    events = make_events("e", 40, T0)
    events[-1]["classification_byNet"] = "prey"
    stream = DeviceStream("x", "d", paged_api(events, page=1), EventFilter(groups=frozenset({"prey"})))
    pager = EventPager([stream], None)
    with patch.object(pager_mod, "MAX_REQUESTS_PER_CALL", 10):
        assert await pager.async_next(5) == []
        assert pager.has_more
        found: list = []
        while pager.has_more:
            found += await pager.async_next(5)
    assert [e["eventID"] for _, e in found] == ["e39"]


def test_pager_store() -> None:
    """Test cursors, user binding and expiry."""
    store = PagerStore()
    pager = EventPager([], "alice")
    cursor = store.add(pager)
    assert store.get(cursor, "alice") is pager
    assert store.get(cursor, "bob") is None
    assert store.get("nope", "alice") is None
    store.remove(cursor)
    assert store.get(cursor, "alice") is None

    with patch.object(pager_mod, "MAX_PAGERS", 2):
        cursors = [store.add(EventPager([], None)) for _ in range(3)]
        assert store.get(cursors[0], None) is None
        assert store.get(cursors[2], None) is not None

    old = EventPager([], None)
    cursor = store.add(old)
    old.touched -= pager_mod.PAGER_TTL + 1
    assert store.get(cursor, None) is None


async def test_ws_load_more_and_filters(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_ws_client
) -> None:
    """Test cursor based loading and the classification filter via websocket."""
    events = make_events("e", 7, T0)
    events[3]["classification_byNet"] = "prey"
    events[5]["classification_byNet"] = "out"
    events[5]["isHidden"] = 1
    api = paged_api(events, page=2)
    mock_api.async_get_events_page.side_effect = api.async_get_events_page.side_effect

    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", "limit": 3})
    msg = await ws.receive_json()
    assert [e["event_id"] for e in msg["result"]["events"]] == ["e0", "e1", "e2"]
    cursor = msg["result"]["cursor"]
    assert cursor

    await ws.send_json({"id": 2, "type": "zeromouse/events", "limit": 3, "cursor": cursor})
    msg = await ws.receive_json()
    # e5 is hidden ("leaving detected") and not in the default view
    assert [e["event_id"] for e in msg["result"]["events"]] == ["e3", "e4", "e6"]
    assert msg["result"]["cursor"] is None

    await ws.send_json({"id": 3, "type": "zeromouse/events", "limit": 3, "cursor": cursor})
    msg = await ws.receive_json()
    assert msg["error"]["code"] == "invalid_cursor"

    await ws.send_json(
        {"id": 4, "type": "zeromouse/events", "classifications": ["prey", "out"]}
    )
    msg = await ws.receive_json()
    assert [e["event_id"] for e in msg["result"]["events"]] == ["e3", "e5"]


async def test_ws_correlation(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    hass_ws_client,
    hass_admin_user,
) -> None:
    """Test that the websocket command matches events and checks permissions."""
    ws = await hass_ws_client(hass)
    with patch(
        "custom_components.zeromouse.frontend.async_correlate",
        AsyncMock(return_value=({"e2": {"method": "flap", "name": "Tiger"}}, "recorder_not_available")),
    ) as correlate:
        await ws.send_json(
            {
                "id": 1,
                "type": "zeromouse/events",
                "correlate": [{"entity": "binary_sensor.tiger", "name": "Tiger", "color": "#123"}],
            }
        )
        msg = await ws.receive_json()
    result = msg["result"]
    assert result["correlation_error"] == "recorder_not_available"
    assert result["events"][0]["match"] == {"method": "flap", "name": "Tiger"}
    assert result["events"][1]["match"] is None
    sent_events = correlate.await_args.args[1]
    assert isinstance(sent_events[0]["time"], datetime)

    # Users without read access to the flap entity are refused
    with patch.object(
        hass_admin_user.permissions, "check_entity", return_value=False
    ):
        await ws.send_json(
            {
                "id": 2,
                "type": "zeromouse/events",
                "correlate": [{"entity": "binary_sensor.secret"}],
            }
        )
        msg = await ws.receive_json()
    assert msg["error"]["code"] == "unauthorized"


@pytest.mark.parametrize(
    "bad",
    [
        {"classifications": ["nonsense"]},
        {"correlate": [{"entity": "not an entity"}]},
        {"correlate": [{"entity": "sensor.x", "preset": "magic"}]},
        {"window_after": 99999},
    ],
)
async def test_ws_rejects_invalid_input(
    hass: HomeAssistant, setup_entry: MockConfigEntry, hass_ws_client, bad: dict
) -> None:
    """Test schema validation of the websocket command."""
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", **bad})
    msg = await ws.receive_json()
    assert msg["error"]["code"] == "invalid_format"


async def test_pager_is_transactional() -> None:
    """Test that a failing fetch loses no events (review finding)."""
    a = make_events("a", 6, T0, step=100)
    b = make_events("b", 6, T0 - timedelta(seconds=50), step=100)
    api_b = paged_api(b, page=1)
    calls = 0
    original = api_b.async_get_events_page.side_effect

    async def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("cloud hiccup")
        return await original(*args, **kwargs)

    api_b.async_get_events_page.side_effect = flaky
    pager = EventPager(
        [
            DeviceStream("x", "A", paged_api(a, page=1), EventFilter()),
            DeviceStream("x", "B", api_b, EventFilter()),
        ],
        None,
    )
    first = await pager.async_next(2)
    with pytest.raises(RuntimeError):
        await pager.async_next(6)
    rest: list = []
    while pager.has_more:
        rest += await pager.async_next(4)
    ids = [e["eventID"] for _, e in first + rest]
    assert ids == ["a0", "b0", "a1", "b1", "a2", "b2", "a3", "b3", "a4", "b4", "a5", "b5"]


async def test_pager_give_back() -> None:
    """Test that a page can be returned when it could not be delivered."""
    events = make_events("e", 4, T0)
    pager = EventPager([DeviceStream("x", "d", paged_api(events), EventFilter())], None)
    page = await pager.async_next(2)
    pager.give_back(page)
    again = await pager.async_next(4)
    assert [e["eventID"] for _, e in again] == ["e0", "e1", "e2", "e3"]


def test_pager_store_per_user_limit() -> None:
    """Test that one user cannot push out the lists of another user."""
    store = PagerStore()
    bob = store.add(EventPager([], "bob"))
    alice = [store.add(EventPager([], "alice")) for _ in range(pager_mod.MAX_PAGERS_PER_USER + 3)]
    assert store.get(bob, "bob") is not None
    assert store.get(alice[0], "alice") is None
    assert store.get(alice[-1], "alice") is not None


async def test_ws_keep_cursor_false(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_ws_client
) -> None:
    """Test that a refresh without paging stores no cursor."""
    events = make_events("e", 7, T0)
    mock_api.async_get_events_page.side_effect = paged_api(events, page=2).async_get_events_page.side_effect
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", "limit": 3, "keep_cursor": False})
    msg = await ws.receive_json()
    assert [e["event_id"] for e in msg["result"]["events"]] == ["e0", "e1", "e2"]
    assert msg["result"]["cursor"] is None
    # The card still learns that it may have missed events
    assert msg["result"]["has_more"] is True


async def test_ws_release_previous_list(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_ws_client
) -> None:
    """Test that a new list can release the caller's previous one."""
    events = make_events("e", 7, T0)
    mock_api.async_get_events_page.side_effect = paged_api(events, page=2).async_get_events_page.side_effect
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", "limit": 2})
    first = (await ws.receive_json())["result"]["cursor"]
    await ws.send_json({"id": 2, "type": "zeromouse/events", "limit": 2, "release": first})
    second = (await ws.receive_json())["result"]["cursor"]
    assert second
    await ws.send_json({"id": 3, "type": "zeromouse/events", "cursor": first})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_cursor"
    # Several lists at once, unknown ones are ignored
    await ws.send_json(
        {"id": 4, "type": "zeromouse/events", "limit": 2, "release": [second, "gone"]}
    )
    assert (await ws.receive_json())["success"]
    await ws.send_json({"id": 5, "type": "zeromouse/events", "cursor": second})
    assert (await ws.receive_json())["error"]["code"] == "invalid_cursor"


def test_pager_store_release_only_own() -> None:
    """Test that a user cannot release the list of another user."""
    store = PagerStore()
    cursor = store.add(EventPager([], "alice"))
    store.release(cursor, "bob")
    assert store.get(cursor, "alice") is not None
    store.release(cursor, "alice")
    assert store.get(cursor, "alice") is None


async def test_ws_correlation_failure_still_returns_events(
    hass: HomeAssistant, setup_entry: MockConfigEntry, hass_ws_client
) -> None:
    """Test that a failing match only drops the cats, not the events."""
    ws = await hass_ws_client(hass)
    with patch(
        "custom_components.zeromouse.frontend.async_correlate",
        AsyncMock(side_effect=RuntimeError("db locked")),
    ):
        await ws.send_json({"id": 1, "type": "zeromouse/events"})
        msg = await ws.receive_json()
    assert msg["success"]
    assert msg["result"]["correlation_error"] == "correlation_failed"
    assert len(msg["result"]["events"]) == 2


async def test_ws_serialization_failure_gives_page_back(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_ws_client
) -> None:
    """Test that the page is returned to the pager if it cannot be serialized."""
    events = make_events("e", 4, T0)
    mock_api.async_get_events_page.side_effect = paged_api(events, page=4).async_get_events_page.side_effect
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", "limit": 2})
    cursor = (await ws.receive_json())["result"]["cursor"]
    with patch(
        "custom_components.zeromouse.frontend._serialize", side_effect=RuntimeError("bad data")
    ):
        await ws.send_json({"id": 2, "type": "zeromouse/events", "limit": 2, "cursor": cursor})
        msg = await ws.receive_json()
    assert not msg["success"]
    await ws.send_json({"id": 3, "type": "zeromouse/events", "limit": 2, "cursor": cursor})
    msg = await ws.receive_json()
    assert [e["event_id"] for e in msg["result"]["events"]] == ["e2", "e3"]
