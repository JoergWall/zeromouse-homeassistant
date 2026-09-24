"""Sensors for ZeroMOUSE."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import parse_event_time
from .const import CLASSIFICATIONS
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator, ZeroMouseDevice
from .entity import ZeroMouseEntity, async_setup_device_entities

PARALLEL_UPDATES = 0


def _last_event_attr(device: ZeroMouseDevice, key: str) -> Any:
    event = device.last_event
    return event.get(key) if event else None


def _classification(device: ZeroMouseDevice) -> str | None:
    value = _last_event_attr(device, "classification_byNet")
    if value is None:
        return None
    return value if value in CLASSIFICATIONS else "unknown"


def _prey_this_month(device: ZeroMouseDevice) -> int | None:
    if device.statistics is None:
        return None
    period = dt_util.now().strftime("%Y-%m")
    return sum(
        int(p.get("value") or 0)
        for p in device.prey_monthly
        if str(p.get("period", "")).startswith(period)
    )


def _prey_total(device: ZeroMouseDevice) -> int | None:
    if device.statistics is None:
        return None
    return sum(int(p.get("value") or 0) for p in device.prey_monthly)


def _last_event_time(device: ZeroMouseDevice) -> datetime | None:
    event = device.last_event
    return parse_event_time(event) if event else None


def _last_prey_time(device: ZeroMouseDevice) -> datetime | None:
    event = device.last_prey_event
    return parse_event_time(event) if event else None


def _last_cat(device: ZeroMouseDevice) -> str | None:
    event = device.last_event
    return device.event_cat(event) if event else None


@dataclass(frozen=True, kw_only=True)
class ZeroMouseSensorDescription(SensorEntityDescription):
    """Describes a ZeroMOUSE sensor."""

    value_fn: Callable[[ZeroMouseDevice], Any]


SENSORS: tuple[ZeroMouseSensorDescription, ...] = (
    ZeroMouseSensorDescription(
        key="last_event",
        translation_key="last_event",
        device_class=SensorDeviceClass.ENUM,
        options=CLASSIFICATIONS,
        value_fn=_classification,
    ),
    ZeroMouseSensorDescription(
        key="last_event_time",
        translation_key="last_event_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_event_time,
    ),
    ZeroMouseSensorDescription(
        key="last_prey_time",
        translation_key="last_prey_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_prey_time,
    ),
    ZeroMouseSensorDescription(
        key="last_cat",
        translation_key="last_cat",
        value_fn=_last_cat,
    ),
    ZeroMouseSensorDescription(
        key="prey_this_month",
        translation_key="prey_this_month",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_prey_this_month,
    ),
    ZeroMouseSensorDescription(
        key="prey_total",
        translation_key="prey_total",
        value_fn=_prey_total,
    ),
    ZeroMouseSensorDescription(
        key="event_count",
        translation_key="event_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.flap.get("eventCount"),
    ),
    ZeroMouseSensorDescription(
        key="ai_score",
        translation_key="ai_score",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.flap.get("ai_score"),
    ),
    ZeroMouseSensorDescription(
        key="feedback_score",
        translation_key="feedback_score",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.flap.get("userFeedback_score"),
    ),
    ZeroMouseSensorDescription(
        key="wifi_rssi",
        translation_key="wifi_rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Firmware 0.17 reports 0 and never updates it
        value_fn=lambda d: d.reported("system", "metricWifiRSSI") or None,
    ),
    ZeroMouseSensorDescription(
        key="boot_count",
        translation_key="boot_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.flap.get("bootCount"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    async_setup_device_entities(
        entry,
        async_add_entities,
        lambda coordinator, device_id: [
            ZeroMouseSensor(coordinator, device_id, description)
            for description in SENSORS
        ],
    )


class ZeroMouseSensor(ZeroMouseEntity, SensorEntity):
    """ZeroMOUSE sensor."""

    entity_description: ZeroMouseSensorDescription

    def __init__(
        self,
        coordinator: ZeroMouseCoordinator,
        device_id: str,
        description: ZeroMouseSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.device)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose details of the last event on the event sensor."""
        if self.entity_description.key == "last_event" and (
            event := self.device.last_event
        ):
            return {
                "event_id": event.get("eventID"),
                "cat": self.device.event_cat(event),
                "image_count": len(event.get("images") or []),
                "is_favorite": event.get("isFavorite"),
            }
        if self.entity_description.key == "prey_total":
            return {"monthly": self.device.prey_monthly}
        return None
