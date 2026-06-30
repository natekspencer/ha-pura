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
from .helpers import get_device_id, get_hardware_major_version


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
    coordinator = entry.runtime_data
    known_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        new_devices = {
            (device_type, get_device_id(device))
            for device_type, devices in coordinator.data.items()
            for device in devices
        } - known_devices

        if not new_devices:
            return

        known_devices.update(new_devices)
        entities: list[PuraSwitchEntity] = []

        for device_type, device_id in new_devices:
            device = coordinator.get_device(device_type, device_id)
            hardware_version = get_hardware_major_version(device)

            for hardware_versions, descriptions in SWITCHES.items():
                if hardware_version not in hardware_versions:
                    continue
                entities.extend(
                    PuraSwitchEntity(
                        coordinator=coordinator,
                        description=description,
                        device_type=device_type,
                        device_id=device_id,
                    )
                    for description in descriptions
                )

            capabilities = device.get("capabilities") or {}
            if len(capabilities.get("diffusionModes") or []) > 1:
                entities.append(
                    PuraSwitchEntity(
                        coordinator=coordinator,
                        description=DIFFUSION_MODE_SWITCH,
                        device_type=device_type,
                        device_id=device_id,
                    )
                )

        async_add_entities(entities)

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


@dataclass(frozen=True, kw_only=True)
class PuraSwitchEntityDescription(SwitchEntityDescription):
    """Pura switch entity description."""

    lookup_key: str
    is_on_fn: Callable[[Any], bool]
    toggle_fn: Callable[[PuraSwitchEntity, bool], tuple[Callable[..., bool], dict]]


SWITCHES: dict[tuple[str, ...], tuple[PuraSwitchEntityDescription, ...]] = {
    ("2",): (
        PuraSwitchEntityDescription(
            key="ambient_mode",
            name="Ambient mode",
            lookup_key="ambientMode",
            is_on_fn=lambda data: data,
            toggle_fn=lambda self, value: (
                self.coordinator.api.set_ambient_mode,
                {"ambient_mode": value},
            ),
        ),
    ),
    ("2", "3", "4", "26", "22"): (
        PuraSwitchEntityDescription(
            key="away_mode",
            name="Away mode",
            lookup_key="awayMode",
            is_on_fn=lambda data: data["enabled"],
            toggle_fn=lambda self, value: (
                self.coordinator.api.set_away_mode,
                build_away_mode_json(self, value),
            ),
        ),
    ),
}

DIFFUSION_MODE_SWITCH = PuraSwitchEntityDescription(
    key="diffusion_mode",
    translation_key="diffusion_mode",
    lookup_key="diffusionMode",
    is_on_fn=lambda data: data == "oscillation-multi-bay",
    toggle_fn=lambda self, value: (
        self.coordinator.api.set_diffusion_mode,
        {"mode": "oscillation-multi-bay" if value else "standard"},
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
