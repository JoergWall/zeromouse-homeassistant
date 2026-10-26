"""Tests for setup, entities, devices and the gallery backend."""

from __future__ import annotations

import copy
from datetime import timedelta
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.zeromouse.api import ZeroMouseApiError, ZeroMouseAuthError
from custom_components.zeromouse.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .conftest import DEVICE_ID, EVENTS, FLAP, OWNER_ID, SHADOW


async def refresh(hass: HomeAssistant, freezer: FrozenDateTimeFactory | None = None) -> None:
    """Trigger a coordinator update."""
    if freezer:
        freezer.tick(timedelta(seconds=61))
        async_fire_time_changed(hass)
    else:
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (ZeroMouseAuthError("x"), ConfigEntryState.SETUP_ERROR),
        (ZeroMouseApiError("x"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception, state: ConfigEntryState
) -> None:
    """Test login failures during setup."""
    mock_api.async_login.side_effect = error
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=OWNER_ID, data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is state


async def test_unload(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test unloading."""
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    assert setup_entry.state is ConfigEntryState.NOT_LOADED


async def test_update_failed_marks_unavailable(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that entities become unavailable and recover."""
    mock_api.async_get_devices.side_effect = ZeroMouseApiError("down")
    await refresh(hass)
    assert hass.states.get("sensor.katzenklappe_last_event").state == "unavailable"
    mock_api.async_get_devices.side_effect = lambda: [copy.deepcopy(FLAP)]
    await refresh(hass)
    assert hass.states.get("sensor.katzenklappe_last_event").state == "prey"


async def test_partial_failures_keep_old_data(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that shadow/statistics errors keep the previous values."""
    mock_api.async_get_shadow.side_effect = ZeroMouseApiError("x")
    mock_api.async_get_statistics.side_effect = ZeroMouseApiError("x")
    coordinator = setup_entry.runtime_data
    coordinator._stats_updated.clear()
    await refresh(hass)
    assert hass.states.get("select.katzenklappe_entry_mode").state == "blocking_prey"
    assert hass.states.get("sensor.katzenklappe_prey_total").state == "5"


async def test_statistics_cached(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that statistics are only fetched every 30 minutes."""
    calls = mock_api.async_get_statistics.await_count
    await refresh(hass)
    assert mock_api.async_get_statistics.await_count == calls


async def test_dynamic_and_stale_devices(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    mock_api: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that new devices appear and removed ones disappear."""
    second = copy.deepcopy(FLAP) | {"deviceID": "ZM-2", "name": "Keller", "catClusters": None}
    mock_api.async_get_devices.side_effect = lambda: [copy.deepcopy(FLAP), copy.deepcopy(second)]
    await refresh(hass)
    assert hass.states.get("sensor.keller_last_event") is not None
    assert device_registry.async_get_device_by_identifier((DOMAIN, "ZM-2"), setup_entry.entry_id)

    mock_api.async_get_devices.side_effect = lambda: [copy.deepcopy(second)]
    await refresh(hass)
    assert device_registry.async_get_device_by_identifier((DOMAIN, DEVICE_ID), setup_entry.entry_id) is None

    # An empty answer never removes everything
    mock_api.async_get_devices.side_effect = list
    await refresh(hass)
    assert device_registry.async_get_device_by_identifier((DOMAIN, "ZM-2"), setup_entry.entry_id)


async def test_new_cat_adds_switch(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that a cat added in the app gets a switch."""
    flap = copy.deepcopy(FLAP)
    flap["catClusters"].append({"id": "c3", "name": "Findus", "allowEntry": True})
    mock_api.async_get_devices.side_effect = lambda: [copy.deepcopy(flap)]
    await refresh(hass)
    assert hass.states.get("switch.katzenklappe_findus_allow_entry").state == "on"

    flap["catClusters"].pop()
    await refresh(hass)
    assert hass.states.get("switch.katzenklappe_findus_allow_entry").state == "unavailable"


async def test_remove_config_entry_device(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that only devices no longer in the account can be removed."""
    from custom_components.zeromouse import async_remove_config_entry_device

    device = device_registry.async_get_device_by_identifier((DOMAIN, DEVICE_ID), setup_entry.entry_id)
    assert not await async_remove_config_entry_device(hass, setup_entry, device)
    old = device_registry.async_get_or_create(
        config_entry_id=setup_entry.entry_id, identifiers={(DOMAIN, "gone")}
    )
    assert await async_remove_config_entry_device(hass, setup_entry, old)


async def test_action_error_is_translated(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that failing writes raise a translated HomeAssistantError."""
    mock_api.async_set_entry_mode.side_effect = ZeroMouseApiError("rejected")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": "select.katzenklappe_entry_mode", "option": "locked"},
            blocking=True,
        )
    assert err.value.translation_key == "api_error"
    assert err.value.translation_placeholders == {"error": "rejected"}


async def test_more_controls(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test the remaining write paths."""
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.katzenklappe_inconclusive_event_handling", "option": "always_allow"},
        blocking=True,
    )
    mock_api.async_update_shadow.assert_awaited_with(DEVICE_ID, {"system": {"undecidableMode": 1}})

    await hass.services.async_call(
        "time",
        "set_value",
        {"entity_id": "time.katzenklappe_exit_open_until", "time": "21:15"},
        blocking=True,
    )
    mock_api.async_set_exit_mode.assert_awaited_with(DEVICE_ID, 2, 480, 1275)

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.katzenklappe_block_prey"}, blocking=True
    )
    mock_api.async_update_shadow.assert_awaited_with(DEVICE_ID, {"rfid": {"blockEnabled": True}})

    for service, value in (("turn_on", True), ("turn_off", False)):
        await hass.services.async_call(
            "switch",
            service,
            {"entity_id": "switch.katzenklappe_block_unknown_cats"},
            blocking=True,
        )
        mock_api.async_update_device.assert_awaited_with(DEVICE_ID, blockUnknownCats=value)

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.katzenklappe_minka_allow_entry"},
        blocking=True,
    )
    clusters = mock_api.async_update_device.await_args.kwargs["catClusters"]
    assert [c["allowEntry"] for c in clusters] == [False, False]


async def test_defaults_without_shadow(
    hass: HomeAssistant, mock_api: MagicMock
) -> None:
    """Test fallbacks when the shadow is empty."""
    mock_api.async_get_shadow.side_effect = lambda _id: {}
    mock_api.async_get_events.side_effect = lambda _id, _n: []
    mock_api.async_get_statistics.return_value = {"data": {"stats": {"prey_monthly": []}}}
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=OWNER_ID, data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    states = {s.entity_id: s.state for s in hass.states.async_all()}
    assert states["time.katzenklappe_exit_open_from"] == "09:00:00"
    assert states["time.katzenklappe_exit_open_until"] == "18:00:00"
    assert states["select.katzenklappe_inconclusive_event_handling"] == "smart"
    assert states["select.katzenklappe_prey_block_duration"] == "unknown"
    assert states["switch.katzenklappe_block_prey"] == "unknown"
    assert states["sensor.katzenklappe_last_event"] == "unknown"
    assert states["sensor.katzenklappe_prey_total"] == "0"
    assert states["binary_sensor.katzenklappe_prey_block_active"] == "off"
    assert states["binary_sensor.katzenklappe_connectivity"] == "unknown"

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.katzenklappe_exit_mode", "option": "time_based"},
        blocking=True,
    )
    mock_api.async_set_exit_mode.assert_awaited_with(DEVICE_ID, 2, 540, 1080)

    client_image = hass.states.get("image.katzenklappe_last_event_image")
    assert client_image.state == "unknown"


async def test_sensor_values(
    hass: HomeAssistant, mock_api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Test derived sensor values at a fixed time."""
    freezer.move_to("2026-09-23T10:01:00+00:00")
    events = copy.deepcopy(EVENTS)
    events[0]["classification_byNet"] = "something-new"
    events.insert(0, {"eventID": "e9", "classification_byNet": "prey", "eventTime": "garbage"})
    mock_api.async_get_events.side_effect = lambda _id, _n: copy.deepcopy(events)
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=OWNER_ID, data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.katzenklappe_prey_this_month").state == "2"
    last = hass.states.get("sensor.katzenklappe_last_event")
    assert last.state == "prey"
    assert last.attributes["event_id"] == "e9"
    assert hass.states.get("sensor.katzenklappe_prey_total").attributes["monthly"][0]["value"] == 3
    # prey event without a usable time
    assert hass.states.get("binary_sensor.katzenklappe_prey_block_active").state == "unknown"

    events.pop(0)
    await refresh(hass, freezer)
    # "something-new" is reported as unknown; prey at 10:00 < 120 s ago -> blocked
    assert hass.states.get("sensor.katzenklappe_last_event").state == "unknown"


async def test_prey_block_active(
    hass: HomeAssistant, mock_api: MagicMock, freezer: FrozenDateTimeFactory
) -> None:
    """Test the derived prey block sensor."""
    freezer.move_to("2026-09-23T10:01:00+00:00")
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=OWNER_ID, data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.katzenklappe_prey_block_active").state == "on"
    await refresh(hass, freezer)
    await refresh(hass, freezer)
    assert hass.states.get("binary_sensor.katzenklappe_prey_block_active").state == "off"


async def test_diagnostics(
    hass: HomeAssistant, setup_entry: MockConfigEntry, hass_client
) -> None:
    """Test that diagnostics redact personal data."""
    diag = await get_diagnostics_for_config_entry(hass, hass_client, setup_entry)
    assert diag["entry"] == {CONF_EMAIL: "**REDACTED**", CONF_PASSWORD: "**REDACTED**"}
    assert DEVICE_ID not in str(diag)
    device = diag["devices"]["device_1"]
    assert device["flap"]["ownerID"] == "**REDACTED**"
    assert device["flap"]["name"] == "**REDACTED**"
    assert device["flap"]["catClusters"][0]["embedding"] == "<1 values>"
    assert device["flap"]["catClusters"][0]["name"] == "**REDACTED**"
    shadow = device["shadow"]
    assert shadow["reported"]["system"]["metricWifiRSSI"] == -61
    assert shadow["desired"] == {"system": {"undecidableMode": 2}}
    assert shadow["connected"] is True
    assert shadow["other_keys"] == []


def test_diagnostics_shadow_allowlist() -> None:
    """Test that unknown shadow values are listed by name only."""
    from custom_components.zeromouse.diagnostics import _shadow

    result = _shadow(
        {
            "state": {
                "reported": {
                    "system": {"kkzmBlockModeIn": 1, "wifiSSID": "Home"},
                    "network": {"ip": "192.168.1.2"},
                    "flag": True,
                },
            },
            "metadata": {"x": 1},
        }
    )
    assert result["reported"] == {"system": {"kkzmBlockModeIn": 1}}
    assert result["desired"] == {}
    assert result["other_keys"] == [
        "metadata",
        "reported.flag",
        "reported.network.ip",
        "reported.system.wifiSSID",
    ]
    assert "Home" not in str(result) and "192.168" not in str(result)


async def test_realtime_event_triggers_refresh(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that a pushed event refreshes the data."""
    calls = mock_api.async_get_devices.await_count
    await setup_entry.runtime_data.async_handle_realtime_event({"eventID": "x"})
    await hass.async_block_till_done()
    assert mock_api.async_get_devices.await_count > calls


async def test_ws_events_variants(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_ws_client
) -> None:
    """Test the websocket command with since, device filter and errors."""
    ws = await hass_ws_client(hass)
    await ws.send_json(
        {"id": 1, "type": "zeromouse/events", "since": "2026-09-13T00:00:00Z", "limit": 500}
    )
    msg = await ws.receive_json()
    assert msg["success"]
    # e1 (epoch 1790000000 = 2026-09-21) is newer than since, e2 too
    assert len(msg["result"]["events"]) == 2
    assert msg["result"]["cursor"] is None
    event = msg["result"]["events"][0]
    assert event["ha_device_id"]
    assert event["rating"] is None
    assert event["group"] == event["classification"]  # clean / prey: own group

    await ws.send_json({"id": 2, "type": "zeromouse/events", "device_id": "other"})
    msg = await ws.receive_json()
    assert msg["result"]["events"] == []

    mock_api.async_get_events_page.side_effect = ZeroMouseApiError("down")
    await ws.send_json({"id": 3, "type": "zeromouse/events"})
    msg = await ws.receive_json()
    assert not msg["success"]
    assert msg["error"]["code"] == "zeromouse_error"


async def test_image_view_errors(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_client
) -> None:
    """Test the image proxy error paths."""
    client = await hass_client()
    base = f"/api/zeromouse/image/{setup_entry.entry_id}/{DEVICE_ID}"
    assert (await client.get(f"{base}/e1/x")).status == 400
    # Only event ids reach the S3 key
    assert (await client.get(f"{base}/e1%2F..%2Fx/1")).status in (400, 404)
    assert (await client.get(f"{base}/e1.jpg/1")).status == 400
    mock_api.async_get_event_image.assert_not_awaited()
    mock_api.async_get_event_image.return_value = None
    assert (await client.get(f"{base}/e1/9")).status == 404
    mock_api.async_get_event_image.side_effect = ZeroMouseApiError("x")
    assert (await client.get(f"{base}/e1/8")).status == 502


async def test_image_view_cache_eviction(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_client
) -> None:
    """Test that the image cache is bounded."""
    client = await hass_client()
    base = f"/api/zeromouse/image/{setup_entry.entry_id}/{DEVICE_ID}/e1"
    with patch("custom_components.zeromouse.frontend.IMAGE_CACHE_SIZE", 2):
        for index in range(3):
            assert (await client.get(f"{base}/{index}")).status == 200
        assert (await client.get(f"{base}/0")).status == 200
    assert mock_api.async_get_event_image.await_count == 4


async def test_image_entity_error(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock, hass_client
) -> None:
    """Test the image entity when the download fails."""
    mock_api.async_get_event_image.side_effect = ZeroMouseApiError("x")
    client = await hass_client()
    state = hass.states.get("image.katzenklappe_last_event_image")
    resp = await client.get(state.attributes["entity_picture"])
    assert resp.status == 500


async def test_image_entity_updates_on_new_event(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that a new event changes the image."""
    before = hass.states.get("image.katzenklappe_last_event_image")
    new = {"eventID": "e3", "eventTime": "2026-09-23T11:00:00Z", "classification_byNet": "clean"}
    mock_api.async_get_events.side_effect = lambda _id, _n: [new, *copy.deepcopy(EVENTS)]
    await refresh(hass)
    after = hass.states.get("image.katzenklappe_last_event_image")
    assert after.attributes["event_id"] == "e3"
    assert after.state != before.state


async def test_event_entity_unknown_classification(
    hass: HomeAssistant, setup_entry: MockConfigEntry, mock_api: MagicMock
) -> None:
    """Test that unknown classifications are mapped."""
    new = {"eventID": "e4", "classification_byNet": "brand-new"}
    mock_api.async_get_events.side_effect = lambda _id, _n: [new, *copy.deepcopy(EVENTS)]
    await refresh(hass)
    state = hass.states.get("event.katzenklappe_detection")
    assert state.attributes["event_type"] == "unknown"
    assert state.attributes["time"] is None


async def test_seen_events_bounded(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Test that the memory of seen events does not grow forever."""
    coordinator = setup_entry.runtime_data
    coordinator._seen_events[DEVICE_ID] = {str(i) for i in range(600)}
    await refresh(hass)
    assert coordinator._seen_events[DEVICE_ID] == {"e1", "e2"}


def test_device_helpers() -> None:
    """Test ZeroMouseDevice helpers."""
    from custom_components.zeromouse.coordinator import ZeroMouseDevice

    device = ZeroMouseDevice(flap={"deviceID": "x"})
    assert device.name == "ZeroMOUSE x"
    assert device.firmware is None
    assert device.cat_name("nope") is None
    device.set_desired("system", {"a": 1})
    assert device.setting("system", "a") == 1
    assert SHADOW  # fixture data sanity
