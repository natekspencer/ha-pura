"""Support for Pura update."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .entity import PuraEntity
from .helpers import determine_pura_model, get_device_id

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PuraUpdateEntityDescription(UpdateEntityDescription):
    """Pura update entity description."""

    lookup_key: str


UPDATE = PuraUpdateEntityDescription(key="firmware", lookup_key="fwVersion")


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura updates using config entry."""
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
            entities = [
                PuraUpdateEntity(
                    coordinator=coordinator,
                    description=UPDATE,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_type, device_id in new_devices
                if device_type == "car"
            ]
            async_add_entities(entities, True)

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


class PuraUpdateEntity(PuraEntity, UpdateEntity):
    """Pura update."""

    entity_description: PuraUpdateEntityDescription
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_should_poll = True
    _attr_release_summary = (
        "https://help.pura.com/en/car_diffuser/Update-Pura-Car-Firmware"
    )

    @property
    def installed_version(self) -> str | None:
        """Version installed and in use."""
        return self.get_device().get(self.entity_description.lookup_key)

    async def async_update(self) -> None:
        """Update the entity."""
        model = determine_pura_model(self.get_device()) or ""
        version = "v2" if "Pro" in model else "v1"
        try:
            details: str = await self.hass.async_add_executor_job(
                self.coordinator.api.get_latest_firmware_details, "car", version
            )
            firmware = {
                (part := line.split("=", 1))[0].lower(): part[1]
                for line in details.split("\n")
            }
            self._attr_latest_version = ".".join(
                firmware[key] for key in ("major", "minor", "patch")
            )
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.exception(ex)
