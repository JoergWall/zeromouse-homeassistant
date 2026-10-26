"""Tests for the ZeroMOUSE integration."""

from __future__ import annotations

import copy
from datetime import timedelta
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.zeromouse.api import (
    ZeroMouseAuthError,
    event_image_index,
    parse_event_time,
)
from custom_components.zeromouse.const import DOMAIN
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util

from .conftest import DEVICE_ID, EVENTS, OWNER_ID


async def test_config_flow(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test the user step."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == OWNER_ID


async def test_config_flow_invalid_auth(hass: HomeAssistant, mock_api: MagicMock) -> None:
    """Test wrong credentials."""
    mock_api.async_login.side_effect = ZeroMouseAuthError("NotAuthorizedException")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test entity states."""
    assert setup_entry.state is ConfigEntryState.LOADED
    states = {s.entity_id: s.state for s in hass.states.async_all()}

    assert states["sensor.katzenklappe_last_event"] == "prey"
    assert states["sensor.katzenklappe_last_cat"] == "Minka"
    assert states["sensor.katzenklappe_prey_total"] == "5"
    assert states["binary_sensor.katzenklappe_connectivity"] == "on"
    assert states["sensor.katzenklappe_last_event_time"] == "2026-09-23T10:00:00+00:00"
    assert states["select.katzenklappe_entry_mode"] == "blocking_prey"
    assert states["select.katzenklappe_exit_mode"] == "time_based"
    # desired wins over reported, like in the app
    assert states["select.katzenklappe_inconclusive_event_handling"] == "always_block"
    assert states["select.katzenklappe_prey_block_duration"] == "120"
    assert states["time.katzenklappe_exit_open_from"] == "08:00:00"
    assert states["time.katzenklappe_exit_open_until"] == "20:00:00"
    assert states["switch.katzenklappe_block_prey"] == "on"
    assert states["switch.katzenklappe_block_unknown_cats"] == "off"
    assert states["switch.katzenklappe_minka_allow_entry"] == "on"
    assert states["switch.katzenklappe_nachbarkater_allow_entry"] == "off"
    assert "image.katzenklappe_last_event_image" in states
    assert "event.katzenklappe_detection" in states
    assert "binary_sensor.katzenklappe_prey_block_active" in states


async def test_controls(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test writing settings."""
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.katzenklappe_entry_mode", "option": "locked"},
        blocking=True,
    )
    mock_api.async_set_entry_mode.assert_awaited_with(DEVICE_ID, 3)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.katzenklappe_exit_mode", "option": "locked"},
        blocking=True,
    )
    mock_api.async_set_exit_mode.assert_awaited_with(DEVICE_ID, 1, 480, 1200)

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": "time.katzenklappe_exit_open_from", "time": "07:30"},
        blocking=True,
    )
    mock_api.async_set_exit_mode.assert_awaited_with(DEVICE_ID, 1, 450, 1200)

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.katzenklappe_prey_block_duration", "option": "600"},
        blocking=True,
    )
    mock_api.async_update_shadow.assert_awaited_with(
        DEVICE_ID, {"proximity": {"irPreyEventTime": 600}}
    )

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.katzenklappe_block_prey"},
        blocking=True,
    )
    mock_api.async_update_shadow.assert_awaited_with(
        DEVICE_ID, {"rfid": {"blockEnabled": False}}
    )

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.katzenklappe_nachbarkater_allow_entry"},
        blocking=True,
    )
    clusters = mock_api.async_update_device.await_args.kwargs["catClusters"]
    assert [c["allowEntry"] for c in clusters] == [True, True]
    assert clusters[0]["embedding"] == [0.1]


async def test_new_event(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that a new event fires the event entity and bus event."""
    fired = []
    hass.bus.async_listen("zeromouse_event", fired.append)
    new = {"eventID": "e3", "eventTime": "2026-09-23T11:00:00Z", "classification_byNet": "clean", "catClusterId": "c2"}
    mock_api.async_get_events.side_effect = lambda _id, _n: [new, *copy.deepcopy(EVENTS)]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    state = hass.states.get("event.katzenklappe_detection")
    assert state.attributes["event_type"] == "clean"
    assert state.attributes["cat"] == "Nachbarkater"
    assert len(fired) == 1
    assert fired[0].data["event_id"] == "e3"
    assert hass.states.get("sensor.katzenklappe_last_event").state == "clean"


async def test_image(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_client
) -> None:
    """Test the event image."""
    client = await hass_client()
    state = hass.states.get("image.katzenklappe_last_event_image")
    resp = await client.get(state.attributes["entity_picture"])
    assert resp.status == 200
    assert await resp.read() == b"\xff\xd8jpeg"
    mock_api.async_get_event_image.assert_awaited_with(DEVICE_ID, "e2", 2)


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that an auth error during polling starts reauth."""
    mock_api.async_get_devices.side_effect = ZeroMouseAuthError("expired")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


def test_helpers() -> None:
    """Test parsing helpers."""
    assert parse_event_time({"eventTime": 1790000000000}).year == 2026
    assert parse_event_time({"eventTime": "1790000000"}).year == 2026
    assert parse_event_time({"createdAt": "2026-01-02T03:04:05.000Z"}).month == 1
    assert parse_event_time({}) is None
    assert event_image_index({"images": [{"imageIndex": 3}, {"imageIndex": 1}]}) == 1
    assert event_image_index({"titleImageIndex": 0}) == 0


async def test_ws_events_and_image_view(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    mock_api: MagicMock,
    hass_ws_client,
    hass_client,
) -> None:
    """Test the gallery backend."""
    ws = await hass_ws_client(hass)
    await ws.send_json({"id": 1, "type": "zeromouse/events", "limit": 5})
    msg = await ws.receive_json()
    assert msg["success"], msg
    events = msg["result"]["events"]
    assert [e["event_id"] for e in events] == ["e2", "e1"]
    assert events[0]["images"] == [1, 2]
    assert events[0]["title_image"] == 2
    assert events[0]["device_name"] == "Katzenklappe"
    assert events[0]["cat"] == "Minka"

    client = await hass_client()
    url = f"/api/zeromouse/image/{setup_entry.entry_id}/{DEVICE_ID}/e2/1"
    resp = await client.get(url)
    assert resp.status == 200
    assert resp.content_type == "image/jpeg"
    await client.get(url)
    assert mock_api.async_get_event_image.await_count == 1  # cached

    resp = await client.get(f"/api/zeromouse/image/unknown/{DEVICE_ID}/e2/1")
    assert resp.status == 404

    resp = await client.get("/zeromouse_static/zeromouse-events-card.js")
    assert resp.status == 200

