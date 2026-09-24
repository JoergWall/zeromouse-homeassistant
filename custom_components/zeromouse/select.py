"""Selects for ZeroMOUSE modes."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    DEFAULT_OUT_CLOSE_AT,
    DEFAULT_OUT_OPEN_AT,
    ENTRY_MODES,
    EXIT_MODES,
    PREY_BLOCK_TIMES,
    UNDECIDABLE_MODES,
)
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

# Writes go to the cloud one at a time
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up selects."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            EntryModeSelect(coordinator, device_id),
            ExitModeSelect(coordinator, device_id),
            UndecidableModeSelect(coordinator, device_id),
            PreyBlockTimeSelect(coordinator, device_id),
        ],
    )


def _option(mapping: dict[int, str], value: Any) -> str | None:
    try:
        return mapping.get(int(value))
    except (TypeError, ValueError):
        return None


def _key(mapping: dict[int, str], option: str) -> int:
    return next(k for k, v in mapping.items() if v == option)


class EntryModeSelect(ZeroMouseEntity, SelectEntity):
    """Entry mode (free / block prey / face detection / locked)."""

    _attr_translation_key = "entry_mode"
    _attr_options = list(ENTRY_MODES.values())

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "entry_mode")

    @property
    def current_option(self) -> str | None:
        """Return the mode."""
        return _option(ENTRY_MODES, self.device.setting("system", "kkzmBlockModeIn"))

    async def async_select_option(self, option: str) -> None:
        """Set the mode."""
        mode = _key(ENTRY_MODES, option)
        self.device.set_desired("system", {"kkzmBlockModeIn": mode})
        await self._async_call(
            self.coordinator.api.async_set_entry_mode(self._device_id, mode)
        )


class ExitModeSelect(ZeroMouseEntity, SelectEntity):
    """Exit mode (open / locked / time based)."""

    _attr_translation_key = "exit_mode"
    _attr_options = list(EXIT_MODES.values())

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "exit_mode")

    @property
    def current_option(self) -> str | None:
        """Return the mode."""
        return _option(EXIT_MODES, self.device.setting("system", "kkzmBlockModeOut"))

    async def async_select_option(self, option: str) -> None:
        """Set the mode, keeping the configured time window."""
        mode = _key(EXIT_MODES, option)
        open_at = self.device.setting("system", "kkzmOutOpenAt")
        close_at = self.device.setting("system", "kkzmOutCloseAt")
        open_at = DEFAULT_OUT_OPEN_AT if open_at is None else int(open_at)
        close_at = DEFAULT_OUT_CLOSE_AT if close_at is None else int(close_at)
        self.device.set_desired(
            "system",
            {
                "kkzmBlockModeOut": mode,
                "kkzmOutOpenAt": open_at,
                "kkzmOutCloseAt": close_at,
            },
        )
        await self._async_call(
            self.coordinator.api.async_set_exit_mode(
                self._device_id, mode, open_at, close_at
            )
        )


class UndecidableModeSelect(ZeroMouseEntity, SelectEntity):
    """Behaviour for inconclusive events."""

    _attr_translation_key = "undecidable_mode"
    _attr_options = list(UNDECIDABLE_MODES.values())
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "undecidable_mode")

    @property
    def current_option(self) -> str | None:
        """Return the mode."""
        value = self.device.setting("system", "undecidableMode")
        return _option(UNDECIDABLE_MODES, 0 if value is None else value)

    async def async_select_option(self, option: str) -> None:
        """Set the mode."""
        values = {"undecidableMode": _key(UNDECIDABLE_MODES, option)}
        self.device.set_desired("system", values)
        await self._async_call(
            self.coordinator.api.async_update_shadow(self._device_id, {"system": values})
        )


class PreyBlockTimeSelect(ZeroMouseEntity, SelectEntity):
    """Minimum time the flap stays blocked after prey was detected."""

    _attr_translation_key = "prey_block_time"
    _attr_options = [str(s) for s in PREY_BLOCK_TIMES]
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "prey_block_time")

    @property
    def current_option(self) -> str | None:
        """Return the duration in seconds."""
        value = self.device.setting("proximity", "irPreyEventTime")
        return None if value is None else str(int(value))

    async def async_select_option(self, option: str) -> None:
        """Set the duration."""
        values = {"irPreyEventTime": int(option)}
        self.device.set_desired("proximity", values)
        await self._async_call(
            self.coordinator.api.async_update_shadow(
                self._device_id, {"proximity": values}
            )
        )
