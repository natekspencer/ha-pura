"""Support for Pura switches."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import functools
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .entity import PuraEntity
from .helpers import get_hardware_major_version


def build_away_mode_json(entity: PuraSwitchEntity, away_mode: bool) -> dict:
    """Build away mode json."""
    away_mode_details = {"away_mode": away_mode}

    if not away_mode:
        return away_mode_details

    device_location = entity.get_device()["deviceLocation"] or {}
    return away_mode_details | {
        "latitude": device_location.get("latitude") or entity.hass.config.latitude,
        "longitude": device_location.get("longitude") or entity.hass.config.longitude,
        "radius": device_location.get("radius") or 150,
    }


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura switchs using config entry."""
    coordinator = entry.runtime_data.coordinator
    added_switches: dict[tuple[str, str], set[str]] = {}

    def _check_devices() -> None:
        nonlocal added_switches
        current_devices = coordinator.current_devices_with_type
        added_switches = {
            device: keys
            for device, keys in added_switches.items()
            if device in current_devices
        }

        entities: list[PuraSwitchEntity] = []

        # Re-evaluate switches not yet added, as device capabilities may change
        for device_id, device_type in current_devices:
            device = coordinator.get_device(device_type, device_id)
            added_keys = added_switches.setdefault((device_id, device_type), set())
            for description in SWITCHES:
                if description.key in added_keys or not description.exists_fn(
                    device_type, device
                ):
                    continue
                added_keys.add(description.key)
                entities.append(
                    PuraSwitchEntity(
                        coordinator=coordinator,
                        description=description,
                        device_type=device_type,
                        device_id=device_id,
                    )
                )

        if entities:
            async_add_entities(entities)

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


@dataclass(frozen=True, kw_only=True)
class PuraSwitchEntityDescription(SwitchEntityDescription):
    """Pura switch entity description."""

    lookup_key: str
    exists_fn: Callable[[str, dict[str, Any]], bool]
    is_on_fn: Callable[[Any], bool]
    toggle_fn: Callable[[PuraSwitchEntity, bool], tuple[Callable[..., bool], dict]]


SWITCHES: tuple[PuraSwitchEntityDescription, ...] = (
    PuraSwitchEntityDescription(
        key="ambient_mode",
        name="Ambient mode",
        lookup_key="ambientMode",
        # Ambient mode is only available on Pura 3 (v2 hardware)
        exists_fn=lambda device_type, device: get_hardware_major_version(device) == "2",
        is_on_fn=lambda data: data,
        toggle_fn=lambda self, value: (
            self.coordinator.api.set_ambient_mode,
            {"ambient_mode": value},
        ),
    ),
    PuraSwitchEntityDescription(
        key="away_mode",
        name="Away mode",
        lookup_key="awayMode",
        # Away mode is available on all home devices, but not on car diffusers.
        exists_fn=lambda device_type, device: (
            device_type != "car"
            and isinstance(away_mode := device.get("awayMode"), dict)
            and "enabled" in away_mode
        ),
        is_on_fn=lambda data: data["enabled"],
        toggle_fn=lambda self, value: (
            self.coordinator.api.set_away_mode,
            build_away_mode_json(self, value),
        ),
    ),
    PuraSwitchEntityDescription(
        key="diffusion_mode",
        translation_key="diffusion_mode",
        lookup_key="diffusionMode",
        # Only expose when the device supports more than one diffusion mode.
        exists_fn=lambda device_type, device: (
            len((device.get("capabilities") or {}).get("diffusionModes") or []) > 1
        ),
        is_on_fn=lambda data: data == "oscillation-multi-bay",
        toggle_fn=lambda self, value: (
            self.coordinator.api.set_diffusion_mode,
            {"mode": "oscillation-multi-bay" if value else "standard"},
        ),
    ),
)


class PuraSwitchEntity(PuraEntity, SwitchEntity):
    """Pura switch."""

    entity_description: PuraSwitchEntityDescription
    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        """Return True if the switch is on."""
        return self.entity_description.is_on_fn(self._data)

    @property
    def _data(self) -> Any:
        """Get the fragrance data."""
        return self.get_device().get(self.entity_description.lookup_key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.async_toggle(value=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.async_toggle(value=False)

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        if (value := kwargs.get("value")) is None:
            value = not self.is_on
        _fn, _data = self.entity_description.toggle_fn(self, value)

        if await self.hass.async_add_executor_job(
            functools.partial(_fn, self._device_id, **_data)
        ):
            await self.coordinator.async_request_refresh()
