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
    # Device and cat names, serial (= device id) and cat cluster ids
    "deviceID",
    "name",
    "id",
    "catClusterId",
    "catClusterId_byUser",
}

# Shadow values the integration uses; other keys are listed by name only, the
# device may report network or hardware details there
SHADOW_KEYS: dict[str, set[str]] = {
    "system": {
        "kkzmBlockModeIn",
        "kkzmBlockModeOut",
        "kkzmOutOpenAt",
        "kkzmOutCloseAt",
        "undecidableMode",
        "metricWifiRSSI",
    },
    "proximity": {"irPreyEventTime"},
    "rfid": {"blockEnabled"},
}


def _shadow(shadow: dict[str, Any]) -> dict[str, Any]:
    """Return the used shadow values and the names of all others."""
    state = shadow.get("state") or {}
    result: dict[str, Any] = {}
    other: list[str] = []
    for part in ("reported", "desired"):
        sections = state.get(part) or {}
        result[part] = {}
        for section, values in sections.items():
            if not isinstance(values, dict):
                other.append(f"{part}.{section}")
                continue
            keys = SHADOW_KEYS.get(section, set())
            used = {k: v for k, v in values.items() if k in keys}
            if used:
                result[part][section] = used
            other.extend(f"{part}.{section}.{k}" for k in values if k not in keys)
    result["connected"] = (shadow.get("connectivity") or {}).get("connected")
    other.extend(k for k in shadow if k not in ("state", "connectivity"))
    result["other_keys"] = sorted(other)
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ZeroMouseConfigEntry
) -> dict[str, Any]:
    """Return the data of all devices, without personal or identifying values."""
    devices = {}
    for number, device in enumerate(entry.runtime_data.data.values(), 1):
        flap = copy.deepcopy(device.flap)
        for cat in flap.get("catClusters") or []:
            if cat and cat.get("embedding"):
                cat["embedding"] = f"<{len(cat['embedding'])} values>"
        devices[f"device_{number}"] = {
            "flap": flap,
            "shadow": _shadow(device.shadow),
            "events": device.events,
            "statistics": device.statistics,
        }
    return async_redact_data({"entry": dict(entry.data), "devices": devices}, TO_REDACT)
