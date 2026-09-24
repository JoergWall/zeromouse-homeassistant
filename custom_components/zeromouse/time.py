"""Time entities for the ZeroMOUSE exit time window."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEFAULT_OUT_CLOSE_AT, DEFAULT_OUT_OPEN_AT
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up time entities."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            ExitWindowTime(coordinator, device_id, key)
            for key in ("kkzmOutOpenAt", "kkzmOutCloseAt")
        ],
    )


class ExitWindowTime(ZeroMouseEntity, TimeEntity):
    """Start or end of the time based exit window (minutes after midnight)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: ZeroMouseCoordinator, device_id: str, shadow_key: str
    ) -> None:
        """Initialize."""
        key = "exit_open_at" if shadow_key == "kkzmOutOpenAt" else "exit_close_at"
        super().__init__(coordinator, device_id, key)
        self._attr_translation_key = key
        self._shadow_key = shadow_key

    def _minutes(self, shadow_key: str) -> int:
        value = self.device.setting("system", shadow_key)
        if value is None:
            return (
                DEFAULT_OUT_OPEN_AT
                if shadow_key == "kkzmOutOpenAt"
                else DEFAULT_OUT_CLOSE_AT
            )
        return int(value)

    @property
    def native_value(self) -> time:
        """Return the time."""
        minutes = self._minutes(self._shadow_key) % 1440
        return time(minutes // 60, minutes % 60)

    async def async_set_value(self, value: time) -> None:
        """Change the time window, keeping the current exit mode."""
        minutes = value.hour * 60 + value.minute
        open_at = self._minutes("kkzmOutOpenAt")
        close_at = self._minutes("kkzmOutCloseAt")
        if self._shadow_key == "kkzmOutOpenAt":
            open_at = minutes
        else:
            close_at = minutes
        mode = int(self.device.setting("system", "kkzmBlockModeOut") or 0)
        self.device.set_desired(
            "system", {"kkzmOutOpenAt": open_at, "kkzmOutCloseAt": close_at}
        )
        await self._async_call(
            self.coordinator.api.async_set_exit_mode(
                self._device_id, mode, open_at, close_at
            )
        )
