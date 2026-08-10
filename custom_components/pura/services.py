"""Service calls for the Pura integration."""

from __future__ import annotations

import asyncio
import functools

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.service import async_extract_entity_ids

from .const import ATTR_DURATION, ATTR_INTENSITY, ATTR_SLOT, DOMAIN
from .coordinator import PuraDataUpdateCoordinator
from .helpers import (
    fragrance_remaining,
    fragrance_runtime as runtime,
    get_device_id,
    get_device_name,
    has_fragrance,
)

SERVICE_START_TIMER = "start_timer"
SERVICE_TIMER_SCHEMA = vol.All(
    cv.make_entity_service_schema(
        {
            vol.Optional(ATTR_SLOT): vol.All(vol.Coerce(int), vol.Range(min=1, max=2)),
            vol.Required(ATTR_INTENSITY): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=10)
            ),
            vol.Required(ATTR_DURATION): cv.positive_time_period,
        },
    )
)


async def async_get_devices(call: ServiceCall) -> dict[str, PuraDataUpdateCoordinator]:
    """Extract referenced devices from a service call."""
    hass = call.hass
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    devices: dict[str, PuraDataUpdateCoordinator] = {}

    for entity_id in await async_extract_entity_ids(call):
        entry = ent_reg.async_get(entity_id)
        if entry and entry.config_entry_id and entry.device_id:
            if (device_entry := dev_reg.async_get(entry.device_id)) is None:
                continue
            if device_entry.serial_number and device_entry.serial_number not in devices:
                for entry_id in device_entry.config_entries:
                    if entry := hass.config_entries.async_get_entry(entry_id):
                        if entry.domain == DOMAIN:
                            devices[device_entry.serial_number] = entry.runtime_data
                            break

    return devices


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Set up the Pura services."""

    async def start_timer(call: ServiceCall) -> None:
        """Start a fragrance timer."""
        devices = await async_get_devices(call)
        if not devices:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_devices_found",
            )

        tasks = []

        for device_id, coordinator in devices.items():
            try:
                device = coordinator.get_device(None, device_id)
            except LookupError:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_device",
                    translation_placeholders={"name": device_id},
                )

            if device["deviceType"] == "car":
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_device",
                    translation_placeholders={"name": get_device_name(device)},
                )

            if not (fragrance_bays := [i for i in (1, 2) if has_fragrance(device, i)]):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="no_fragrances_installed"
                )

            if not (slot := call.data.get(ATTR_SLOT)):
                if len(fragrance_bays) == 1:
                    slot = fragrance_bays[0]
                else:
                    slot1_remaining = fragrance_remaining(device, 1) or 0
                    slot2_remaining = fragrance_remaining(device, 2) or 0
                    if slot1_remaining > slot2_remaining:
                        slot = 1
                    elif slot2_remaining > slot1_remaining:
                        slot = 2
                    else:
                        slot = 1 if runtime(device, 1) <= runtime(device, 2) else 2
            elif slot not in fragrance_bays:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="fragrance_slot_empty",
                    translation_placeholders={"slot": slot},
                )

            _set_timer = functools.partial(
                coordinator.api.set_timer,
                get_device_id(device),
                bay=slot,
                intensity=call.data.get(ATTR_INTENSITY),
                end=call.data.get(ATTR_DURATION),
            )
            tasks.append(hass.async_add_executor_job(_set_timer))

        await asyncio.gather(*tasks)
        for coordinator in set(devices.values()):
            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_START_TIMER, start_timer, schema=SERVICE_TIMER_SCHEMA
    )
