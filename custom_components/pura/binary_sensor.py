"""Support for Pura binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pypura.utils import has_fragrance

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .entity import PuraEntity


def is_low_fragrance(device: dict[str, Any], bay: int) -> bool | None:
    """Return whether the fragrance in a bay is running low."""
    bay_data = device.get(f"bay{bay}") or {}
    if (low_fragrance := bay_data.get("lowFragrance")) is None:
        low_fragrance = (bay_data.get("remaining") or {}).get("lowFragrance")
    return low_fragrance


@dataclass(frozen=True, kw_only=True)
class PuraBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Pura binary sensor entity description."""

    available_fn: Callable[[dict], bool] | None = None
    on_fn: Callable[[dict], Any]


SENSORS: dict[tuple[str, ...], tuple[PuraBinarySensorEntityDescription, ...]] = {
    ("car", "mini"): (  # single fragrance
        PuraBinarySensorEntityDescription(
            key="low_fragrance",
            translation_key="low_fragrance",
            device_class=BinarySensorDeviceClass.PROBLEM,
            available_fn=lambda data: has_fragrance(data, 1),
            on_fn=lambda data: is_low_fragrance(data, 1),
        ),
    ),
    ("wall", "plus"): (  # dual fragrance
        PuraBinarySensorEntityDescription(
            key="bay_1_low_fragrance",
            translation_key="bay_low_fragrance",
            translation_placeholders={"bay": "1"},
            device_class=BinarySensorDeviceClass.PROBLEM,
            available_fn=lambda data: has_fragrance(data, 1),
            on_fn=lambda data: is_low_fragrance(data, 1),
        ),
        PuraBinarySensorEntityDescription(
            key="bay_2_low_fragrance",
            translation_key="bay_low_fragrance",
            translation_placeholders={"bay": "2"},
            device_class=BinarySensorDeviceClass.PROBLEM,
            available_fn=lambda data: has_fragrance(data, 2),
            on_fn=lambda data: is_low_fragrance(data, 2),
        ),
    ),
    ("wall", "plus", "mini"): (
        PuraBinarySensorEntityDescription(
            key="connected",
            translation_key="connected",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_fn=lambda data: data["connected"],
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura binary sensors using config entry."""
    coordinator = entry.runtime_data.coordinator
    added_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        nonlocal added_devices
        current_devices = coordinator.current_devices_with_type
        if new_devices := current_devices - added_devices:
            async_add_entities(
                PuraBinarySensorEntity(
                    coordinator=coordinator,
                    description=description,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_types, descriptions in SENSORS.items()
                for device_id, device_type in new_devices
                if device_type in device_types
                for description in descriptions
            )
        added_devices = current_devices

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


class PuraBinarySensorEntity(PuraEntity, BinarySensorEntity):
    """Pura binary sensor entity."""

    entity_description: PuraBinarySensorEntityDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
        if available_fn := self.entity_description.available_fn:
            return available_fn(self.get_device())
        return True

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.on_fn(self.get_device())
