"""Tests for the rate_event and delete_event service actions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeromouse.api import ZeroMouseApiError
from custom_components.zeromouse.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .conftest import DEVICE_ID


def _device_id(device_registry: dr.DeviceRegistry, entry: MockConfigEntry) -> str:
    device = device_registry.async_get_device_by_identifier((DOMAIN, DEVICE_ID), entry.entry_id)
    assert device
    return device.id


async def test_rate_and_delete(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    mock_api: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test that the actions reach the API with the cloud device id."""
    device_id = _device_id(device_registry, setup_entry)
    await hass.services.async_call(
        DOMAIN,
        "rate_event",
        {"device_id": device_id, "event_id": "e2", "rating": "incorrect"},
        blocking=True,
    )
    mock_api.async_rate_event.assert_awaited_once_with(DEVICE_ID, "e2", "incorrect")

    await hass.services.async_call(
        DOMAIN,
        "rate_event",
        {"device_id": device_id, "event_id": "e2", "rating": "correct"},
        blocking=True,
    )
    mock_api.async_rate_event.assert_awaited_with(DEVICE_ID, "e2", "correct")

    await hass.services.async_call(
        DOMAIN,
        "rate_event",
        {"device_id": device_id, "event_id": "e2", "rating": "none"},
        blocking=True,
    )
    mock_api.async_rate_event.assert_awaited_with(DEVICE_ID, "e2", None)

    calls = mock_api.async_get_devices.await_count
    await hass.services.async_call(
        DOMAIN, "delete_event", {"device_id": device_id, "event_id": "e2"}, blocking=True
    )
    mock_api.async_delete_event.assert_awaited_once_with(DEVICE_ID, "e2")
    await hass.async_block_till_done()
    assert mock_api.async_get_devices.await_count > calls  # refreshed


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("rate_event", {"rating": "correct"}),
        ("delete_event", {}),
    ],
)
async def test_api_errors_are_translated(
    hass: HomeAssistant,
    setup_entry: MockConfigEntry,
    mock_api: MagicMock,
    device_registry: dr.DeviceRegistry,
    service: str,
    data: dict,
) -> None:
    """Test that cloud errors become translated HomeAssistantErrors."""
    mock_api.async_rate_event.side_effect = ZeroMouseApiError("nope")
    mock_api.async_delete_event.side_effect = ZeroMouseApiError("nope")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            service,
            {"device_id": _device_id(device_registry, setup_entry), "event_id": "e1", **data},
            blocking=True,
        )
    assert err.value.translation_key == "api_error"


async def test_unknown_device(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """Test a device that is not a ZeroMOUSE."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "delete_event", {"device_id": "nope", "event_id": "e1"}, blocking=True
        )
    assert err.value.translation_key == "device_not_found"

    other = MockConfigEntry(domain="other")
    other.add_to_hass(hass)
    foreign = dr.async_get(hass).async_get_or_create(
        config_entry_id=other.entry_id, identifiers={("other", "x")}
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "delete_event", {"device_id": foreign.id, "event_id": "e1"}, blocking=True
        )


async def test_entry_not_loaded(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """Test calling an action while the integration is unloaded."""
    device_id = _device_id(device_registry, setup_entry)
    await hass.config_entries.async_unload(setup_entry.entry_id)
    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "delete_event", {"device_id": device_id, "event_id": "e1"}, blocking=True
        )
    assert err.value.translation_key == "entry_not_loaded"


async def test_invalid_rating(
    hass: HomeAssistant, setup_entry: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """Test schema validation."""
    with pytest.raises(Exception):  # noqa: B017 - vol.Invalid / MultipleInvalid
        await hass.services.async_call(
            DOMAIN,
            "rate_event",
            {
                "device_id": _device_id(device_registry, setup_entry),
                "event_id": "e1",
                "rating": "maybe",
            },
            blocking=True,
        )
