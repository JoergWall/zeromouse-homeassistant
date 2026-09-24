"""Diagnostics for ZeroMOUSE."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import ZeroMouseConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD,
    "ownerID",
    "owner",
    "networkName",
    "identityID",
    "identityId",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZeroMouseConfigEntry
) -> dict[str, Any]:
    """Return raw data of all devices."""
    devices = {}
    for device_id, device in entry.runtime_data.data.items():
        flap = copy.deepcopy(device.flap)
        for cat in flap.get("catClusters") or []:
            if cat and cat.get("embedding"):
                cat["embedding"] = f"<{len(cat['embedding'])} values>"
        devices[device_id] = {
            "flap": flap,
            "shadow": device.shadow,
            "events": device.events,
            "statistics": device.statistics,
        }
    return async_redact_data({"entry": dict(entry.data), "devices": devices}, TO_REDACT)
