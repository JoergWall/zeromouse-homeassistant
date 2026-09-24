"""Switches for ZeroMOUSE."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            BlockPreySwitch(coordinator, device_id),
            BlockUnknownCatsSwitch(coordinator, device_id),
        ],
    )

    # Cats can be added in the app at any time
    coordinator = entry.runtime_data
    known_cats: set[tuple[str, str]] = set()

    @callback
    def _add_new_cats() -> None:
        new = [
            (device_id, cat["id"])
            for device_id, device in coordinator.data.items()
            for cat in device.cats
            if cat.get("id") and (device_id, cat["id"]) not in known_cats
        ]
        if new:
            known_cats.update(new)
            async_add_entities(
                CatAllowEntrySwitch(coordinator, device_id, cat_id)
                for device_id, cat_id in new
            )

    _add_new_cats()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_cats))


class BlockPreySwitch(ZeroMouseEntity, SwitchEntity):
    """Actively block prey; if off the device only records events."""

    _attr_translation_key = "block_prey"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "block_prey")

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        value = self.device.setting("rfid", "blockEnabled")
        return None if value is None else bool(value)

    async def _async_set(self, enabled: bool) -> None:
        values = {"blockEnabled": enabled}
        self.device.set_desired("rfid", values)
        await self._async_call(
            self.coordinator.api.async_update_shadow(self._device_id, {"rfid": values})
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._async_set(False)


class BlockUnknownCatsSwitch(ZeroMouseEntity, SwitchEntity):
    """Block cats that are not in the cat list (face detection mode)."""

    _attr_translation_key = "block_unknown_cats"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "block_unknown_cats")

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        value = self.device.flap.get("blockUnknownCats")
        return None if value is None else bool(value)

    async def _async_set(self, enabled: bool) -> None:
        self.device.flap["blockUnknownCats"] = enabled
        await self._async_call(
            self.coordinator.api.async_update_device(
                self._device_id, blockUnknownCats=enabled
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self._async_set(False)


class CatAllowEntrySwitch(ZeroMouseEntity, SwitchEntity):
    """Allow entry for one known cat (face detection mode)."""

    _attr_translation_key = "cat_allow_entry"

    def __init__(
        self, coordinator: ZeroMouseCoordinator, device_id: str, cat_id: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, f"cat_{cat_id}_allow_entry")
        self._cat_id = cat_id
        self._attr_translation_placeholders = {
            "cat": self.device.cat_name(cat_id) or cat_id
        }

    @property
    def _cat(self) -> dict[str, Any] | None:
        return next((c for c in self.device.cats if c.get("id") == self._cat_id), None)

    @property
    def available(self) -> bool:
        """Return if the cat still exists."""
        return super().available and self._cat is not None

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        cat = self._cat
        return None if cat is None else bool(cat.get("allowEntry"))

    async def _async_set(self, allow: bool) -> None:
        # The API only accepts the full list, exactly like the app sends it.
        clusters = copy.deepcopy(self.device.cats)
        for cat in clusters:
            if cat.get("id") == self._cat_id:
                cat["allowEntry"] = allow
        self.device.flap["catClusters"] = clusters
        await self._async_call(
            self.coordinator.api.async_update_device(
                self._device_id, catClusters=clusters
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Allow entry."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Deny entry."""
        await self._async_set(False)
