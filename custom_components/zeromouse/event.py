"""Event entity firing for every new ZeroMOUSE detection."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import parse_event_time
from .const import CLASSIFICATIONS
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up event entities."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [ZeroMouseDetectionEvent(coordinator, device_id)],
    )


class ZeroMouseDetectionEvent(ZeroMouseEntity, EventEntity):
    """Fires with the classification of each new event."""

    _attr_translation_key = "detection"
    _attr_event_types = CLASSIFICATIONS

    def __init__(self, coordinator: ZeroMouseCoordinator, device_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, "detection")

    @callback
    def _handle_coordinator_update(self) -> None:
        device = self.coordinator.data.get(self._device_id)
        for event in self.coordinator.new_events.get(self._device_id, []):
            classification = event.get("classification_byNet")
            if classification not in CLASSIFICATIONS:
                classification = "unknown"
            when = parse_event_time(event)
            self._trigger_event(
                classification,
                {
                    "event_id": event.get("eventID"),
                    "cat": device.event_cat(event) if device else None,
                    "time": when.isoformat() if when else None,
                },
            )
        super()._handle_coordinator_update()
