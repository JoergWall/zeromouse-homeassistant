"""Base entity and helpers for ZeroMOUSE."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ZeroMouseError
from .const import DOMAIN, MANUFACTURER
from .coordinator import ZeroMouseConfigEntry, ZeroMouseCoordinator, ZeroMouseDevice


@callback
def async_setup_device_entities(
    entry: ZeroMouseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[ZeroMouseCoordinator, str], Iterable[Entity]],
) -> None:
    """Add entities for every device, including devices added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new = [device_id for device_id in coordinator.data if device_id not in known]
        if not new:
            return
        known.update(new)
        async_add_entities(
            [entity for device_id in new for entity in factory(coordinator, device_id)]
        )

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


class ZeroMouseEntity(CoordinatorEntity[ZeroMouseCoordinator]):
    """Entity bound to one ZeroMOUSE device."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: ZeroMouseCoordinator, device_id: str, key: str
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.data[device_id]
        model = device.flap.get("model")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            # The API fills "model" with the device id on current firmware
            model=model if model not in (None, device_id) else None,
            name=device.name,
            serial_number=device_id,
            sw_version=device.firmware,
            hw_version=(
                str(device.flap["verHardware"])
                if device.flap.get("verHardware") is not None
                else None
            ),
        )

    @property
    def device(self) -> ZeroMouseDevice:
        """Return the current device data."""
        return self.coordinator.data[self._device_id]

    @property
    def available(self) -> bool:
        """Return if the device is known."""
        return super().available and self._device_id in self.coordinator.data

    async def _async_call(self, call: Awaitable[object]) -> None:
        """Run a write call, then update state."""
        try:
            await call
        except ZeroMouseError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="api_error",
                translation_placeholders={"error": str(err)},
            ) from err
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
