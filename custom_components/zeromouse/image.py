"""Image entity showing the picture of the last ZeroMOUSE event."""

from __future__ import annotations

import logging

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import ZeroMouseError, event_image_index, parse_event_time
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator
from .entity import ZeroMouseEntity, async_setup_device_entities

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up image entities."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            ZeroMouseLastEventImage(hass, coordinator, device_id)
        ],
    )


class ZeroMouseLastEventImage(ZeroMouseEntity, ImageEntity):
    """Preview image of the newest event."""

    _attr_translation_key = "last_event_image"
    _attr_content_type = "image/jpeg"

    def __init__(
        self, hass: HomeAssistant, coordinator: ZeroMouseCoordinator, device_id: str
    ) -> None:
        """Initialize."""
        ZeroMouseEntity.__init__(self, coordinator, device_id, "last_event_image")
        ImageEntity.__init__(self, hass)
        self._event_id: str | None = None
        self._image: bytes | None = None
        self._update_event()

    def _update_event(self) -> None:
        event = self.device.last_event
        event_id = event.get("eventID") if event else None
        if event_id != self._event_id:
            self._event_id = event_id
            self._image = None
            self._attr_image_last_updated = (
                (parse_event_time(event) or dt_util.utcnow()) if event else None
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        if self._device_id in self.coordinator.data:
            self._update_event()
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Return the event the image belongs to."""
        return {"event_id": self._event_id}

    async def async_image(self) -> bytes | None:
        """Return the JPEG of the newest event."""
        if self._image is not None:
            return self._image
        event = self.device.last_event
        if not event or (index := event_image_index(event)) is None:
            return None
        try:
            self._image = await self.coordinator.api.async_get_event_image(
                self._device_id, event["eventID"], index
            )
        except ZeroMouseError as err:
            _LOGGER.warning("Could not load ZeroMOUSE image: %s", err)
            return None
        return self._image
