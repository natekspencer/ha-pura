"""Support for Pura sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

from pypura.utils import dig, get_fragrance_name, get_fragrance_remaining, has_fragrance

from homeassistant.components.sensor import (
    DOMAIN as SENSOR_DOMAIN,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.util import slugify
from homeassistant.util.dt import UTC, utc_from_timestamp

from . import PuraConfigEntry
from .const import DOMAIN
from .coordinator import PuraDataUpdateCoordinator
from .entity import PuraEntity, get_active_bay, get_controller, get_runtime

HEX_COLOR = re.compile(r"#?([0-9a-fA-F]{6})")


def get_fragrance_vial_url(device: dict[str, Any], bay: int) -> str | None:
    """Get the URL of the fragrance vial image for a bay."""
    return dig(device, f"bay{bay}.fragrance.vialUrl") or None


def get_fragrance_attributes(device: dict[str, Any], bay: int) -> dict[str, Any]:
    """Get the extra state attributes for a bay's fragrance."""
    color = dig(device, f"bay{bay}.fragrance.placeholderColor")
    if isinstance(color, str) and (match := HEX_COLOR.fullmatch(color.strip())):
        return {"color": f"#{match[1].upper()}"}
    return {}


@dataclass(frozen=True, kw_only=True)
class PuraSensorEntityDescription(SensorEntityDescription):
    """Pura sensor entity description."""

    attributes_fn: Callable[[dict], dict[str, Any]] | None = None
    available_fn: Callable[[dict], bool] | None = None
    picture_fn: Callable[[dict], str | None] | None = None
    value_fn: Callable[[dict], Any | None]
    # Identifies the vial a runtime belongs to, so it doesn't drop for the same vial
    vial_fn: Callable[[dict], Any] | None = None


def _bay_sensors(bay: int) -> tuple[PuraSensorEntityDescription, ...]:
    """Return the sensors for a bay on a multi-bay device."""
    return (
        PuraSensorEntityDescription(
            key=f"bay_{bay}",
            translation_key=f"bay_{bay}_fragrance",
            entity_category=EntityCategory.DIAGNOSTIC,
            attributes_fn=lambda data: get_fragrance_attributes(data, bay),
            available_fn=lambda data: has_fragrance(data, bay),
            picture_fn=lambda data: get_fragrance_vial_url(data, bay),
            value_fn=lambda data: get_fragrance_name(data, bay),
        ),
        PuraSensorEntityDescription(
            key=f"bay_{bay}_fragrance_remaining",
            translation_key=f"bay_{bay}_fragrance_remaining",
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            available_fn=lambda data: has_fragrance(data, bay),
            value_fn=lambda data: get_fragrance_remaining(data, bay),
        ),
        PuraSensorEntityDescription(
            key=f"bay_{bay}_runtime",
            translation_key=f"bay_{bay}_runtime",
            device_class=SensorDeviceClass.DURATION,
            entity_category=EntityCategory.DIAGNOSTIC,
            native_unit_of_measurement=UnitOfTime.SECONDS,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_unit_of_measurement=UnitOfTime.HOURS,
            available_fn=lambda data: has_fragrance(data, bay),
            value_fn=lambda data: get_runtime(data, bay),
            vial_fn=lambda data: dig(data, f"bay{bay}.id"),
        ),
        PuraSensorEntityDescription(
            key=f"bay_{bay}_installed",
            translation_key=f"bay_{bay}_installed",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            available_fn=lambda data: has_fragrance(data, bay),
            value_fn=lambda data: datetime.fromtimestamp(data[f"bay{bay}"]["id"], UTC),
        ),
    )


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
            attributes_fn=lambda data: get_fragrance_attributes(data, 1),
            available_fn=lambda data: has_fragrance(data, 1),
            picture_fn=lambda data: get_fragrance_vial_url(data, 1),
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
    ("wall", "plus", "luxe"): (
        PuraSensorEntityDescription(
            key="active_fragrance",
            translation_key="active_fragrance",
            value_fn=lambda data: (
                get_fragrance_name(data, bay)
                if (bay := get_active_bay(data))
                else "none"
            ),
        ),
        *_bay_sensors(1),
        *_bay_sensors(2),
    ),
    ("luxe",): (*_bay_sensors(3), *_bay_sensors(4)),
    ("wall", "plus", "mini", "luxe"): (
        PuraSensorEntityDescription(
            key="controller",
            translation_key="controller",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data: (
                "schedule"
                if (controller := get_controller(data)) not in ("default", "timer")
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
    device_registry = dr.async_get(hass)
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
        # Only rename entity IDs generated from the device name, not customized ones
        registry_entry = entity_registry.async_get(entity_id)
        if registry_entry.device_id and (
            device_entry := device_registry.async_get(registry_entry.device_id)
        ):
            for name in filter(None, (device_entry.name_by_user, device_entry.name)):
                if entity_id != f"{SENSOR_DOMAIN}.{slugify(f'{name} slot installed')}":
                    continue
                new_entity_id = (
                    f"{SENSOR_DOMAIN}.{slugify(f'{name} fragrance installed')}"
                )
                if not entity_registry.async_is_registered(
                    new_entity_id
                ) and hass.states.async_available(new_entity_id):
                    updates["new_entity_id"] = new_entity_id
                break
        entity_registry.async_update_entity(entity_id, **updates)


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura sensors using config entry."""
    coordinator = entry.runtime_data.coordinator
    added_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        nonlocal added_devices
        current_devices = coordinator.current_devices_with_type
        if new_devices := current_devices - added_devices:
            _async_migrate_entities(hass, coordinator)
            entities = [
                (PuraRuntimeSensorEntity if description.vial_fn else PuraSensorEntity)(
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
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the fragrance color, if any."""
        if attributes_fn := self.entity_description.attributes_fn:
            return attributes_fn(self.get_device()) or None
        return None

    @property
    def entity_picture(self) -> str | None:
        """Return the fragrance vial image, if any."""
        if picture_fn := self.entity_description.picture_fn:
            return picture_fn(self.get_device())
        return super().entity_picture

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the value reported by the sensor."""
        return self.entity_description.value_fn(self.get_device())


@dataclass
class PuraRuntimeExtraStoredData(ExtraStoredData):
    """The runtime a vial has reached, kept across restarts."""

    vial: Any
    runtime: int

    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the data."""
        return {"vial": self.vial, "runtime": self.runtime}


class PuraRuntimeSensorEntity(PuraSensorEntity, RestoreEntity):
    """Pura fragrance runtime sensor that doesn't drop for the same vial.

    The API can clear a timer, or stop the bay, before the bay's stored runtime
    catches up, so the runtime would drop back to its value from before the bay
    started. Statistics treat a large drop as a reset, so keep the runtime reached
    so far for the same vial until the stored value catches up. A new vial starts
    over.
    """

    _runtime: PuraRuntimeExtraStoredData | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the runtime reached before a restart."""
        await super().async_added_to_hass()
        if (
            (last := await self.async_get_last_extra_data())
            and (data := last.as_dict()).get("vial") is not None
            and isinstance(runtime := data.get("runtime"), int)
            and not isinstance(runtime, bool)
        ):
            self._runtime = PuraRuntimeExtraStoredData(data["vial"], runtime)

    @property
    def extra_restore_state_data(self) -> PuraRuntimeExtraStoredData | None:
        """Return the runtime reached, with the vial it belongs to."""
        return self._runtime

    @property
    def native_value(self) -> int | None:
        """Return the runtime, holding it for the same vial."""
        device = self.get_device()
        if (value := self.entity_description.value_fn(device)) is None:
            return None
        held = self._runtime
        if (vial := self.entity_description.vial_fn(device)) is None:
            # The API can briefly leave out the vial ID. Nothing is held for a missing
            # ID, but keep any held runtime, and don't drop below it, until it's back.
            return max(value, held.runtime) if held else value
        if held and held.vial == vial and value < held.runtime:
            value = held.runtime
        self._runtime = PuraRuntimeExtraStoredData(vial, value)
        return value
