"""Data update coordinator for ZeroMOUSE."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ZeroMouseApi,
    ZeroMouseApiError,
    ZeroMouseAuthError,
    ZeroMouseError,
    parse_event_time,
)
from .const import (
    DOMAIN,
    EVENT_LIMIT,
    EVENT_ZEROMOUSE,
    STATISTICS_INTERVAL,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type ZeroMouseConfigEntry = ConfigEntry[ZeroMouseCoordinator]


@dataclass
class ZeroMouseDevice:
    """Everything known about one ZeroMOUSE device."""

    flap: dict[str, Any]
    shadow: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    statistics: dict[str, Any] | None = None

    @property
    def device_id(self) -> str:
        """Return the device id."""
        return str(self.flap["deviceID"])

    @property
    def name(self) -> str:
        """Return the user given name."""
        return self.flap.get("name") or f"ZeroMOUSE {self.device_id}"

    @property
    def firmware(self) -> str | None:
        """Return the firmware version."""
        parts = [self.flap.get(k) for k in ("verMajor", "verMinor", "verRevision")]
        if any(p is None for p in parts):
            return None
        return ".".join(str(p) for p in parts)

    def setting(self, section: str, key: str) -> Any:
        """Return a shadow value the way the app does: desired, else reported."""
        state = self.shadow.get("state") or {}
        for part in ("desired", "reported"):
            value = ((state.get(part) or {}).get(section) or {}).get(key)
            if value is not None:
                return value
        return None

    def reported(self, section: str, key: str) -> Any:
        """Return a reported shadow value."""
        state = self.shadow.get("state") or {}
        return ((state.get("reported") or {}).get(section) or {}).get(key)

    def set_desired(self, section: str, values: dict[str, Any]) -> None:
        """Optimistically store desired values until the next refresh."""
        state = self.shadow.setdefault("state", {})
        desired = state.setdefault("desired", {}) or {}
        state["desired"] = desired
        desired.setdefault(section, {}).update(values)

    @property
    def cats(self) -> list[dict[str, Any]]:
        """Return the cat clusters."""
        return [c for c in self.flap.get("catClusters") or [] if c]

    def cat_name(self, cluster_id: str | None) -> str | None:
        """Return the name of a cat cluster."""
        for cat in self.cats:
            if cat.get("id") == cluster_id:
                return cat.get("name")
        return None

    @property
    def last_event(self) -> dict[str, Any] | None:
        """Return the newest event."""
        return self.events[0] if self.events else None

    @property
    def last_prey_event(self) -> dict[str, Any] | None:
        """Return the newest event classified as prey."""
        return next(
            (e for e in self.events if e.get("classification_byNet") == "prey"), None
        )

    def event_cat(self, event: dict[str, Any]) -> str | None:
        """Return the cat name of an event."""
        return self.cat_name(event.get("catClusterId_byUser") or event.get("catClusterId"))

    @property
    def prey_monthly(self) -> list[dict[str, Any]]:
        """Return the monthly prey statistics."""
        stats = self.statistics or {}
        if isinstance(stats.get("data"), dict):
            stats = stats["data"]
        return list((stats.get("stats") or {}).get("prey_monthly") or [])


class ZeroMouseCoordinator(DataUpdateCoordinator[dict[str, ZeroMouseDevice]]):
    """Polls the ZeroMOUSE cloud."""

    config_entry: ZeroMouseConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ZeroMouseConfigEntry, api: ZeroMouseApi
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self._stats_updated: dict[str, datetime] = {}
        self._seen_events: dict[str, set[str]] = {}
        # New events found by the last refresh, consumed by event entities
        self.new_events: dict[str, list[dict[str, Any]]] = {}

    async def _async_update_data(self) -> dict[str, ZeroMouseDevice]:
        try:
            devices = await self._fetch()
        except ZeroMouseAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        except ZeroMouseError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._remove_stale_devices(devices)
        return devices

    def _remove_stale_devices(self, devices: dict[str, ZeroMouseDevice]) -> None:
        """Detach devices that are no longer part of the account."""
        if not devices:
            # Never wipe everything because of one empty answer
            return
        registry = dr.async_get(self.hass)
        for entry in dr.async_entries_for_config_entry(
            registry, self.config_entry.entry_id
        ):
            ids = {ident for domain, ident in entry.identifiers if domain == DOMAIN}
            if ids and not ids & devices.keys():
                _LOGGER.info("Removing ZeroMOUSE device %s, no longer in the account", ids)
                registry.async_remove_device(entry.id)

    async def _fetch(self) -> dict[str, ZeroMouseDevice]:
        old = self.data or {}
        devices: dict[str, ZeroMouseDevice] = {}
        self.new_events = {}
        now = dt_util.utcnow()

        for flap in await self.api.async_get_devices():
            device_id = flap["deviceID"]
            previous = old.get(device_id)
            device = ZeroMouseDevice(flap=flap)

            try:
                device.shadow = await self.api.async_get_shadow(device_id)
            except ZeroMouseApiError as err:
                _LOGGER.debug("Shadow of %s unavailable: %s", device_id, err)
                device.shadow = previous.shadow if previous else {}

            device.events = await self.api.async_get_events(device_id, EVENT_LIMIT)
            self._detect_new_events(device)

            last_stats = self._stats_updated.get(device_id)
            if previous is None or last_stats is None or now - last_stats > STATISTICS_INTERVAL:
                try:
                    device.statistics = await self.api.async_get_statistics(device_id)
                    self._stats_updated[device_id] = now
                except ZeroMouseApiError as err:
                    _LOGGER.debug("Statistics of %s unavailable: %s", device_id, err)
                    device.statistics = previous.statistics if previous else None
            else:
                device.statistics = previous.statistics

            devices[device_id] = device
        return devices

    def _detect_new_events(self, device: ZeroMouseDevice) -> None:
        ids = {e["eventID"] for e in device.events if e.get("eventID")}
        seen = self._seen_events.get(device.device_id)
        self._seen_events[device.device_id] = (
            ids if seen is None or len(seen) > 500 else seen | ids
        )
        if seen is None:
            # First refresh: don't replay history
            return
        new = [e for e in reversed(device.events) if e.get("eventID") not in seen]
        if not new:
            return
        self.new_events[device.device_id] = new
        ha_device = dr.async_get(self.hass).async_get_device_by_identifier(
            (DOMAIN, device.device_id), self.config_entry.entry_id
        )
        for event in new:
            when = parse_event_time(event)
            self.hass.bus.async_fire(
                EVENT_ZEROMOUSE,
                {
                    # Home Assistant device id, usable in the service actions
                    "device_id": ha_device.id if ha_device else None,
                    "zeromouse_device_id": device.device_id,
                    "device_name": device.name,
                    "event_id": event.get("eventID"),
                    "classification": event.get("classification_byNet"),
                    "cat": device.event_cat(event),
                    "time": when.isoformat() if when else None,
                },
            )

    async def async_handle_realtime_event(self, event: dict[str, Any]) -> None:
        """Handle a pushed event: refresh right away."""
        _LOGGER.debug("Realtime event: %s", event)
        await self.async_request_refresh()
