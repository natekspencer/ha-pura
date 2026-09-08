"""Support for Pura update."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, override

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PuraConfigEntry
from .coordinator import PuraFirmwareDataUpdateCoordinator
from .entity import PuraEntity

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
    coordinator = entry.runtime_data.coordinator
    firmware_coordinator = entry.runtime_data.firmware_coordinator
    added_devices: set[tuple[str, str]] = set()

    def _check_devices() -> None:
        nonlocal added_devices
        current_devices = coordinator.current_devices_with_type
        if new_devices := current_devices - added_devices:
            entities = [
                PuraUpdateEntity(
                    coordinator=firmware_coordinator,
                    description=UPDATE,
                    device_type=device_type,
                    device_id=device_id,
                )
                for device_id, device_type in new_devices
            ]
            async_add_entities(entities, True)
        added_devices = current_devices

    _check_devices()
    entry.async_on_unload(coordinator.async_add_listener(_check_devices))


class PuraUpdateEntity(PuraEntity, UpdateEntity):
    """Pura update."""

    entity_description: PuraUpdateEntityDescription
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = UpdateEntityFeature.PROGRESS

    def __init__(
        self,
        coordinator: PuraFirmwareDataUpdateCoordinator,
        description: PuraUpdateEntityDescription,
        device_type: str,
        device_id: str,
    ) -> None:
        """Construct a Pura update entity."""
        super().__init__(coordinator, description, device_type, device_id)
        if device_type == "car":
            self._attr_release_summary = (
                "https://help.pura.com/en/car_diffuser/Update-Pura-Car-Firmware"
            )
        else:
            self._attr_supported_features |= UpdateEntityFeature.INSTALL

        # explicitly add this entity to the device coordinator listeners
        coordinator.device_coordinator.async_add_listener(
            self._handle_coordinator_update
        )

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        device = self.get_device()

        in_progress = False
        if ota := (device.get("ota") or {}):
            in_progress = ota.get("status") not in ("Finished")
        self._attr_in_progress = in_progress

        installed_version: str | None = None
        if self._device_type == "car":  # car uses fwVersion
            installed_version = str(device.get(self.entity_description.lookup_key))
        elif (ota_version := device.get("otaVer")) is not None:
            installed_version = str(ota_version)
        self._attr_installed_version = installed_version

        latest_version: str | None = None
        if details := (self.coordinator.data or {}).get(self._device_id):
            if self._device_type == "car":
                latest_version = ".".join(
                    str(details.get(key)) for key in ("major", "minor", "patch")
                )
            else:
                latest_version = str(details.get("version"))
        self._attr_latest_version = latest_version

        update_percentage: int | float | None = None
        if "percent" in ota:
            update_percentage = ota["percent"]
        self._attr_update_percentage = update_percentage

        super()._handle_coordinator_update()

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Install an update."""
        device = self.get_device()
        device_type = device.get("model")
        await self.hass.async_add_executor_job(
            self.coordinator.api.request_ota_update,
            self._device_id,
            device_type,
            device.get("deviceVer"),
            device.get("otaVer"),
        )
