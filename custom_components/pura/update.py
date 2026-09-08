"""Support for Pura update."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
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

    @property
    def in_progress(self) -> bool | None:
        """Update installation progress."""
        if ota := (self.get_device().get("ota") or {}):
            return ota.get("status") not in ("Finished")
        return None

    @property
    def installed_version(self) -> str | None:
        """Version installed and in use."""
        device = self.get_device()
        if self._device_type == "car":  # car uses fwVersion
            return str(device.get(self.entity_description.lookup_key))
        if (ota_version := device.get("otaVer")) is not None:
            return str(ota_version)
        return None

    @property
    def latest_version(self) -> str | None:
        """Latest version available for install."""
        if not (details := self.coordinator.data.get(self._device_id)):
            return

        if self._device_type == "car":
            return ".".join(
                str(details.get(key)) for key in ("major", "minor", "patch")
            )

        return str(details.get("version"))

    @property
    def update_percentage(self) -> int | float | None:
        """Update installation progress."""
        ota = self.get_device().get("ota") or {}
        if "percent" in ota:
            return ota.get("percent")

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
