"""Support for Pura sensors."""

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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import UTC, utc_from_timestamp

from . import PuraConfigEntry
from .coordinator import PuraDataUpdateCoordinator
from .entity import PuraEntity
from .helpers import (
    fragrance_name,
    fragrance_remaining,
    fragrance_runtime,
    get_device_id,
    has_fragrance,
)


@dataclass(frozen=True, kw_only=True)
class PuraSensorEntityDescription(SensorEntityDescription):
    """Pura sensor entity description."""

    available_fn: Callable[[dict], bool] | None = None
    value_fn: Callable[[dict], Any | None]


SENSORS: dict[tuple[str, ...], tuple[PuraSensorEntityDescription, ...]] = {
    ("car",): (
        PuraSensorEntityDescription(
            key="intensity",
            translation_key="intensity",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:fan",
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: data["bay1"]["fanIntensity"],
        ),
        PuraSensorEntityDescription(
            key="last_active",
            translation_key="last_active",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: datetime.fromtimestamp(data["bay1"]["activeAt"], UTC),
        ),
    ),
    ("car", "mini"): (
        PuraSensorEntityDescription(
            key="fragrance",
            translation_key="fragrance",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: fragrance_name(data, 1),
        ),
        PuraSensorEntityDescription(
            key="fragrance_remaining",
            translation_key="fragrance_remaining",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: fragrance_remaining(data, 1),
        ),
        PuraSensorEntityDescription(
            key="runtime",
            translation_key="runtime",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: data["bay1"]["wearingTime"],
        ),
    ),
    ("wall", "plus"): (
        PuraSensorEntityDescription(
            key="active_fragrance",
            translation_key="active_fragrance",
            icon="mdi:scent",
            value_fn=lambda data: (
                fragrance_name(data, 1)
                if (bay := data["bay1"]) and bay["activeAt"]
                else (
                    fragrance_name(data, 2)
                    if (bay := data["bay2"]) and bay["activeAt"]
                    else "none"
                )
            ),
        ),
        PuraSensorEntityDescription(
            key="bay_1",
            translation_key="bay_fragrance",
            translation_placeholders={"bay": 1},
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: fragrance_name(data, 1),
        ),
        PuraSensorEntityDescription(
            key="bay_1_fragrance_remaining",
            translation_key="bay_fragrance_remaining",
            translation_placeholders={"bay": 1},
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: fragrance_remaining(data, 1),
        ),
        PuraSensorEntityDescription(
            key="bay_1_runtime",
            translation_key="bay_runtime",
            translation_placeholders={"bay": "1"},
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: fragrance_runtime(data, 1),
        ),
        PuraSensorEntityDescription(
            key="bay_1_installed",
            translation_key="bay_installed",
            translation_placeholders={"bay": "1"},
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: datetime.fromtimestamp(data["bay1"]["id"], UTC),
        ),
        PuraSensorEntityDescription(
            key="bay_2",
            translation_key="bay_fragrance",
            translation_placeholders={"bay": "2"},
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: fragrance_name(data, 2),
        ),
        PuraSensorEntityDescription(
            key="bay_2_fragrance_remaining",
            translation_key="bay_fragrance_remaining",
            translation_placeholders={"bay": "2"},
            entity_category=EntityCategory.DIAGNOSTIC,
            icon="mdi:scent",
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: fragrance_remaining(data, 2),
        ),
        PuraSensorEntityDescription(
            key="bay_2_runtime",
            translation_key="bay_runtime",
            translation_placeholders={"bay": "2"},
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: fragrance_runtime(data, 2),
        ),
        PuraSensorEntityDescription(
            key="bay_2_installed",
            translation_key="bay_installed",
            translation_placeholders={"bay": "2"},
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: datetime.fromtimestamp(data["bay2"]["id"], UTC),
        ),
    ),
    ("wall", "plus", "mini"): (
        PuraSensorEntityDescription(
            key="controller",
            translation_key="controller",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data: (
                "schedule"
                if (controller := data["controller"]).isnumeric()
                else controller
            ),
        ),
        PuraSensorEntityDescription(
            key="timer",
            translation_key="timer",
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=lambda data: (
                None
                if not (end := (data.get("timer") or {}).get("end"))
                else utc_from_timestamp(end)
            ),
        ),
    ),
    ("mini",): (
        PuraSensorEntityDescription(
            key="bay_1_installed",
            translation_key="bay_installed",
            translation_placeholders={"bay": ""},
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: datetime.fromtimestamp(data["bay1"]["id"], UTC),
        ),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura sensors using config entry."""
    coordinator: PuraDataUpdateCoordinator = entry.runtime_data

    entities = [
        PuraSensorEntity(
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


class PuraSensorEntity(PuraEntity, SensorEntity):
    """Pura sensor entity."""

    entity_description: PuraSensorEntityDescription

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if available_fn := self.entity_description.available_fn:
            return available_fn(self.get_device())
        return super().available

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the value reported by the sensor."""
        return self.entity_description.value_fn(self.get_device())
