"""Service calls for the Pura integration."""

from __future__ import annotations

import asyncio
import functools

from pypura.utils import get_device_name, get_fragrance_remaining, has_fragrance
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.service import async_extract_entity_ids

from .const import ATTR_DURATION, ATTR_INTENSITY, ATTR_SLOT, BAYS, DOMAIN
from .coordinator import PuraDataUpdateCoordinator
from .entity import get_runtime

SERVICE_START_TIMER = "start_timer"
SERVICE_TIMER_SCHEMA = vol.All(
    cv.make_entity_service_schema(
        {
            vol.Optional(ATTR_SLOT): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=len(BAYS))
            ),
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
        entity_entry = ent_reg.async_get(entity_id)
        if entity_entry and entity_entry.config_entry_id and entity_entry.device_id:
            if (device_entry := dev_reg.async_get(entity_entry.device_id)) is None:
                continue
            if (serial := device_entry.serial_number) and serial not in devices:
                entry = hass.config_entries.async_get_entry(
                    device_entry.config_entry_id
                )
                if (
                    entry
                    and entry.domain == DOMAIN
                    and entry.state is ConfigEntryState.LOADED
                ):
                    devices[serial] = entry.runtime_data.coordinator

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

            if device["modelType"] == "car":
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="invalid_device",
                    translation_placeholders={"name": get_device_name(device)},
                )

            if not (fragrance_bays := [i for i in BAYS if has_fragrance(device, i)]):
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="no_fragrances_installed"
                )

            if not (slot := call.data.get(ATTR_SLOT)):
                # Most remaining first, then the least runtime, then the lowest slot
                slot = min(
                    fragrance_bays,
                    key=lambda bay: (
                        -(get_fragrance_remaining(device, bay) or 0),
                        get_runtime(device, bay),
                    ),
                )
            elif slot not in fragrance_bays:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="fragrance_slot_empty",
                    translation_placeholders={"slot": slot},
                )

            _set_timer = functools.partial(
                coordinator.api.set_timer,
                device_id,
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
