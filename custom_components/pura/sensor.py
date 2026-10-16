"""Support for Pura sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pypura.utils import (
    get_fragrance_name,
    get_fragrance_remaining,
    get_fragrance_runtime,
    has_fragrance,
)

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.dt import UTC, utc_from_timestamp

from . import PuraConfigEntry
from .const import DOMAIN
from .coordinator import PuraDataUpdateCoordinator
from .entity import PuraEntity


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
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: get_fragrance_name(data, 1),
        ),
        PuraSensorEntityDescription(
            key="fragrance_remaining",
            translation_key="fragrance_remaining",
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: get_fragrance_remaining(data, 1),
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
            value_fn=lambda data: (
                get_fragrance_name(data, 1)
                if (bay := data["bay1"]) and bay["activeAt"]
                else (
                    get_fragrance_name(data, 2)
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
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: get_fragrance_name(data, 1),
        ),
        PuraSensorEntityDescription(
            key="bay_1_fragrance_remaining",
            translation_key="bay_fragrance_remaining",
            translation_placeholders={"bay": 1},
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: get_fragrance_remaining(data, 1),
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
            value_fn=lambda data: get_fragrance_runtime(data, 1),
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
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: get_fragrance_name(data, 2),
        ),
        PuraSensorEntityDescription(
            key="bay_2_fragrance_remaining",
            translation_key="bay_fragrance_remaining",
            translation_placeholders={"bay": "2"},
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, 2),
            value_fn=lambda data: get_fragrance_remaining(data, 2),
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
            value_fn=lambda data: get_fragrance_runtime(data, 2),
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
                if (controller := data["controller"]) not in ("default", "timer")
                and controller in {s.get("id") for s in data.get("schedules") or []}
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
            key="fragrance_installed",
            translation_key="fragrance_installed",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            available_fn=lambda data: has_fragrance(data, 1),
            value_fn=lambda data: datetime.fromtimestamp(data["bay1"]["id"], UTC),
        ),
    ),
}

BATTERY_SENSOR = PuraSensorEntityDescription(
    key="battery",
    translation_key="battery",
    device_class=SensorDeviceClass.BATTERY,
    entity_category=EntityCategory.DIAGNOSTIC,
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda data: data["batteryRemaining"],
)


@callback
def _async_migrate_entities(
    hass: HomeAssistant, coordinator: PuraDataUpdateCoordinator
) -> None:
    """Migrate the Mini's installed sensor to match its other single-slot sensors.

    The sensor used the dual-slot `bay_1_installed` key with an empty slot number,
    resulting in a `..._slot_installed` entity ID.

    TODO: Added in October 2026. Remove this migration, and its tests in
    tests/test_sensor.py, in a release after April 2027.
    """
    entity_registry = er.async_get(hass)
    for device_id, device in coordinator.data.items():
        if device.get("modelType") != "mini":
            continue
        if not (
            entity_id := entity_registry.async_get_entity_id(
                SENSOR_DOMAIN, DOMAIN, f"{device_id}-bay_1_installed"
            )
        ):
            continue
        new_unique_id = f"{device_id}-fragrance_installed"
        if entity_registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, new_unique_id):
            continue
        updates: dict[str, Any] = {"new_unique_id": new_unique_id}
        # Only rename entity IDs that have not been customized
        if entity_id.endswith("_slot_installed"):
            new_entity_id = (
                f"{entity_id.removesuffix('_slot_installed')}_fragrance_installed"
            )
            if not entity_registry.async_is_registered(
                new_entity_id
            ) and hass.states.async_available(new_entity_id):
                updates["new_entity_id"] = new_entity_id
        entity_registry.async_update_entity(entity_id, **updates)


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura sensors using config entry."""
    coordinator = entry.runtime_data.coordinator
    _async_migrate_entities(hass, coordinator)
    added_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        nonlocal added_devices
        current_devices = coordinator.current_devices_with_type
        if new_devices := current_devices - added_devices:
            entities = [
                PuraSensorEntity(
                    coordinator=coordinator,
                    description=description,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_types, descriptions in SENSORS.items()
                for device_id, device_type in new_devices
                if device_type in device_types
                for description in descriptions
            ]
            entities.extend(
                PuraSensorEntity(
                    coordinator=coordinator,
                    description=BATTERY_SENSOR,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_id, device_type in new_devices
                if device_type == "car"
                and coordinator.get_device(device_type, device_id).get(
                    "batteryRemaining"
                )
                is not None
            )
            async_add_entities(entities)
        added_devices = current_devices

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


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
