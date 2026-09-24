"""Binary sensors for ZeroMOUSE."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import parse_event_time
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            ZeroMousePreyBlockSensor(coordinator, device_id),
            ZeroMouseOnlineSensor(coordinator, device_id),
        ],
    )


class ZeroMouseOnlineSensor(ZeroMouseEntity, BinarySensorEntity):
    """Cloud connection of the device (shadow ``connectivity.connected``)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "online")

    @property
    def is_on(self) -> bool | None:
        """Return if the device is connected to the cloud."""
        connected = (self.device.shadow.get("connectivity") or {}).get("connected")
        return None if connected is None else bool(connected)


class ZeroMousePreyBlockSensor(ZeroMouseEntity, BinarySensorEntity):
    """On while the flap is (probably) blocked because of recently detected prey.

    Derived from the last prey event and the configured minimum block duration,
    the cloud does not report the actual lock state.
    """

    _attr_translation_key = "prey_blocked"

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "prey_blocked")

    @property
    def is_on(self) -> bool | None:
        """Return if prey was detected within the block duration."""
        event = self.device.last_prey_event
        if event is None:
            return False
        when = parse_event_time(event)
        if when is None:
            return None
        block_time = self.device.setting("proximity", "irPreyEventTime") or 60
        return dt_util.utcnow() - when < timedelta(seconds=int(block_time))
