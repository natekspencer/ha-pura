"""Support for Pura binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .coordinator import PuraDataUpdateCoordinator
from .entity import PuraEntity
from .helpers import get_device_id


@dataclass(frozen=True, kw_only=True)
class PuraBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Pura binary sensor entity description."""

    on_fn: Callable[[dict], Any]


SENSORS: dict[tuple[str, ...], tuple[PuraBinarySensorEntityDescription, ...]] = {
    ("car", "mini"): (  # single fragrance
        PuraBinarySensorEntityDescription(
            key="low_fragrance",
            name="Low fragrance",
            device_class=BinarySensorDeviceClass.PROBLEM,
            on_fn=lambda data: (data.get("bay1") or {}).get("lowFragrance", False),
        ),
    ),
    ("wall", "plus", "mini"): (
        PuraBinarySensorEntityDescription(
            key="connected",
            name="Connected",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            on_fn=lambda data: data["connected"],
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura binary sensors using config entry."""
    coordinator: PuraDataUpdateCoordinator = entry.runtime_data

    entities = [
        PuraBinarySensorEntity(
            coordinator=coordinator,
            description=description,
            device_type=device_type,
            device_id=get_device_id(device),
        )
        for device_types, descriptions in SENSORS.items()
        for device_type, devices in coordinator.devices.items()
        if device_type in device_types
        for device in devices
        for description in descriptions
    ]

    if not entities:
        return

    async_add_entities(entities)


class PuraBinarySensorEntity(PuraEntity, BinarySensorEntity):
    """Pura binary sensor entity."""

    entity_description: PuraBinarySensorEntityDescription
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return self.entity_description.on_fn(self.get_device())
