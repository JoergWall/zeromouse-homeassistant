"""Fixtures for ZeroMOUSE tests."""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeromouse.const import DOMAIN

OWNER_ID = "11111111-2222-3333-4444-555555555555"
DEVICE_ID = "ZM-TEST-0001"

FLAP = {
    "deviceID": DEVICE_ID,
    "name": "Katzenklappe",
    "model": "ZM1",
    "networkName": "wifi",
    "ownerID": OWNER_ID,
    "verHardware": 2,
    "verMajor": 1,
    "verMinor": 4,
    "verRevision": 7,
    "bootCount": 12,
    "eventCount": 345,
    "ai_score": 80,
    "userFeedback_score": 55,
    "catClusters": [
        {"id": "c1", "name": "Minka", "allowEntry": True, "embedding": [0.1], "threshold": 0.5},
        {"id": "c2", "name": "Nachbarkater", "allowEntry": False, "embedding": [0.2], "threshold": 0.5},
    ],
    "blockUnknownCats": False,
}

SHADOW = {
    "state": {
        "reported": {
            "system": {
                "kkzmBlockModeIn": 1,
                "kkzmBlockModeOut": 2,
                "kkzmOutOpenAt": 480,
                "kkzmOutCloseAt": 1200,
                "undecidableMode": 0,
                "metricWifiRSSI": -61,
            },
            "proximity": {"irPreyEventTime": 120},
            "rfid": {"blockEnabled": True},
        },
        "desired": {"system": {"undecidableMode": 2}},
    },
    "connectivity": {"connected": True, "timestamp": 1790153958550},
}

EVENTS = [
    {
        "eventID": "e2",
        "eventTime": "2026-09-23T10:00:00.000Z",
        "classification_byNet": "prey",
        "catClusterId": "c1",
        "titleImageIndex": 2,
        "images": [{"imageIndex": 1}, {"imageIndex": 2}],
    },
    {
        "eventID": "e1",
        "eventTime": 1790000000,
        "classification_byNet": "clean",
        "catClusterId": "c2",
        "images": [],
    },
]

STATS = {"stats": {"prey_monthly": [{"period": "2026-08", "value": 3}, {"period": "2026-09", "value": 2}]}}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations."""


@pytest.fixture
def mock_api() -> MagicMock:
    """Return a mocked ZeroMouseApi."""
    api = MagicMock()
    api.owner_id = OWNER_ID
    api.async_login = AsyncMock()
    api.async_get_tokens = AsyncMock(return_value=("id", "access"))
    api.async_get_devices = AsyncMock(side_effect=lambda: [copy.deepcopy(FLAP)])
    api.async_get_shadow = AsyncMock(side_effect=lambda _id: copy.deepcopy(SHADOW))
    api.async_get_events = AsyncMock(side_effect=lambda _id, _n: copy.deepcopy(EVENTS))
    api.async_get_events_since = AsyncMock(side_effect=lambda _id, _since, _n: copy.deepcopy(EVENTS))
    api.async_get_statistics = AsyncMock(return_value=STATS)
    api.async_update_shadow = AsyncMock()
    api.async_set_entry_mode = AsyncMock()
    api.async_set_exit_mode = AsyncMock()
    api.async_update_device = AsyncMock()
    api.async_get_event_image = AsyncMock(return_value=b"\xff\xd8jpeg")
    with (
        patch("custom_components.zeromouse.ZeroMouseApi", return_value=api),
        patch("custom_components.zeromouse.config_flow.ZeroMouseApi", return_value=api),
        patch("custom_components.zeromouse.ZeroMouseRealtime") as realtime,
    ):
        realtime.return_value.run = AsyncMock()
        yield api


@pytest.fixture
async def setup_entry(hass: HomeAssistant, mock_api: MagicMock) -> MockConfigEntry:
    """Set up a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=OWNER_ID,
        data={CONF_EMAIL: "a@b.c", CONF_PASSWORD: "pw"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
