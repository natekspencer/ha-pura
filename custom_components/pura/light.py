"""Support for Pura nightlight."""

from __future__ import annotations

import functools
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.color import color_rgb_to_hex, rgb_hex_to_rgb_list

from . import PuraConfigEntry
from .entity import PuraEntity
from .helpers import get_device_id

LIGHT_DESCRIPTION = LightEntityDescription(key="nightlight", name="Nightlight")


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura lights using config entry."""
    coordinator = entry.runtime_data
    known_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        new_devices = {
            (device_type, get_device_id(device))
            for device_type, devices in coordinator.data.items()
            for device in devices
        } - known_devices

        if new_devices:
            known_devices.update(new_devices)
            async_add_entities(
                PuraLightEntity(
                    coordinator=coordinator,
                    description=LIGHT_DESCRIPTION,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_type, device_id in new_devices
                if device_type in ("wall", "mini")
            )

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


class PuraLightEntity(PuraEntity, LightEntity):
    """Pura Light."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}

    @property
    def is_on(self) -> bool:
        """Return True if the light is on."""
        return self._nightlight_data["active"]

    @property
    def brightness(self) -> int:
        """Return the brightness of the light between 0..255.

        Pura uses a range of 1..10 to control brightness.
        """
        return round((self._nightlight_data["brightness"] / 10) * 255)

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return the rgb color value [int, int, int]."""
        return tuple(rgb_hex_to_rgb_list(self._nightlight_data["color"]))

    @property
    def _nightlight_data(self) -> dict:
        """Get the nightlight data."""
        device = self.get_device()
        data: dict | None = None
        if (controller := device["controller"]).isnumeric():
            for schedule in device["schedules"]:
                if str(schedule["number"]) == controller:
                    data = schedule["nightlight"]
                    break
        if not data:
            data = device["deviceDefaults"]["nightlight"]
        return data | {"controller": str(controller)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        data = self._nightlight_data

        brightness = data["brightness"]
        if new_brightness := kwargs.get(ATTR_BRIGHTNESS):
            # Pura uses a range of 1..10 to control brightness.
            brightness = max(1, round((new_brightness / 255) * 10))

        color = data["color"]
        if new_color := kwargs.get(ATTR_RGB_COLOR):
            color = color_rgb_to_hex(*new_color)

        if await self.hass.async_add_executor_job(
            functools.partial(
                self.coordinator.api.set_nightlight,
                self._device_id,
                active=True,
                brightness=brightness,
                color=color,
                controller=data["controller"],
            )
        ):
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        data = self._nightlight_data

        if await self.hass.async_add_executor_job(
            functools.partial(
                self.coordinator.api.set_nightlight,
                self._device_id,
                active=False,
                brightness=data["brightness"],
                color=data["color"],
                controller=data["controller"],
            )
        ):
            await self.coordinator.async_request_refresh()
