"""Config flow tests covering every path."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zeromouse.api import ZeroMouseApiError, ZeroMouseAuthError
from custom_components.zeromouse.const import DOMAIN
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import OWNER_ID


@pytest.mark.parametrize(
    ("error", "reason"),
    [(ZeroMouseAuthError("x"), "invalid_auth"), (ZeroMouseApiError("x"), "cannot_connect")],
)
async def test_user_error_then_recover(
    hass: HomeAssistant, mock_api: MagicMock, error: Exception, reason: str
) -> None:
    """Test that the form recovers after an error."""
    mock_api.async_login.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "bad"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    mock_api.async_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "good"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_EMAIL: "a@b.c", CONF_PASSWORD: "good"}


async def test_already_configured(
    hass: HomeAssistant, mock_api: MagicMock, setup_entry: MockConfigEntry
) -> None:
    """Test that the same account cannot be added twice."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "other@b.c", CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, mock_api: MagicMock, setup_entry: MockConfigEntry
) -> None:
    """Test reauthentication incl. a wrong password first."""
    result = await setup_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_api.async_login.side_effect = ZeroMouseAuthError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api.async_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert setup_entry.data[CONF_PASSWORD] == "new"


async def test_reauth_other_account(
    hass: HomeAssistant, mock_api: MagicMock, setup_entry: MockConfigEntry
) -> None:
    """Test that reauth refuses a different account."""
    result = await setup_entry.start_reauth_flow(hass)
    mock_api.owner_id = "someone-else"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_reconfigure(
    hass: HomeAssistant, mock_api: MagicMock, setup_entry: MockConfigEntry
) -> None:
    """Test changing email and password."""
    result = await setup_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    mock_api.async_login.side_effect = ZeroMouseApiError("x")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "new@b.c", CONF_PASSWORD: "pw2"}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    mock_api.async_login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "new@b.c", CONF_PASSWORD: "pw2"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert setup_entry.data == {CONF_EMAIL: "new@b.c", CONF_PASSWORD: "pw2"}
    assert setup_entry.title == "new@b.c"
    assert setup_entry.unique_id == OWNER_ID


async def test_reconfigure_other_account(
    hass: HomeAssistant, mock_api: MagicMock, setup_entry: MockConfigEntry
) -> None:
    """Test that reconfigure refuses a different account."""
    result = await setup_entry.start_reconfigure_flow(hass)
    mock_api.owner_id = "someone-else"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: "x@b.c", CONF_PASSWORD: "pw"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
