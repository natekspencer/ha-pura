"""Pura entities."""

from __future__ import annotations

from typing import Any

from pypura.utils import dig, get_device_name, get_model_name

from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    CONNECTION_NETWORK_MAC,
    format_mac,
)
from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PuraDataUpdateCoordinator, PuraFirmwareDataUpdateCoordinator

UPDATE_INTERVAL = 30


def get_active_bay(device: dict[str, Any]) -> int | None:
    """Get the bay that is currently diffusing, if any."""
    return next((i for i in (1, 2) if dig(device, f"bay{i}.activeAt")), None)


class PuraEntity(
    CoordinatorEntity[PuraDataUpdateCoordinator | PuraFirmwareDataUpdateCoordinator]
):
    """Base class for Pura entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PuraDataUpdateCoordinator | PuraFirmwareDataUpdateCoordinator,
        description: EntityDescription,
        device_type: str,
        device_id: str,
    ) -> None:
        """Construct a PuraEntity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_type = device_type
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}-{description.key}"

        device = self.get_device()
        fw_version = device.get("fwVersion")
        if ota_version := device.get("otaVer"):
            fw_version = f"{fw_version} ({ota_version})"
        self._attr_device_info = DeviceInfo(
            connections={
                (
                    CONNECTION_BLUETOOTH
                    if device_type == "car"
                    else CONNECTION_NETWORK_MAC,
                    format_mac(device_id),
                )
            },
            identifiers={(DOMAIN, device_id)},
            manufacturer="Pura",
            model=get_model_name(device),
            name=get_device_name(device),
            serial_number=device_id,
            suggested_area=dig(device, "roomProfile.name"),
            sw_version=fw_version,
            hw_version=device.get("hwVersion"),
        )

    def get_device(self) -> dict:
        """Get the device from the coordinator."""
        coordinator = self.coordinator
        if isinstance(coordinator, PuraFirmwareDataUpdateCoordinator):
            coordinator = coordinator.device_coordinator
        return coordinator.get_device(self._device_type, self._device_id)

    @property
    def _intensity_data(self) -> dict:
        """Get the intensity data."""
        device = self.get_device()
        if (controller := device["controller"]) == "timer" and device[controller]:
            data = device[controller] | {"controller": controller}
            # A timer keeps the intensity it started with, but the bay's own follows
            # any changes, and differs per bay when auto-alternate switches bays.
            if bay := get_active_bay(device):
                intensity = dig(device, f"deviceDefaults.bay{bay}Intensity")
                data["intensity"] = intensity or data["intensity"]
            return data
        elif controller != "default":
            for schedule in device.get("schedules") or []:
                if schedule.get("id") == controller:
                    return schedule | {"controller": controller}
        bay = get_active_bay(device) or 0
        intensity = device["deviceDefaults"][f"bay{bay}Intensity"] if bay else None
        return {"bay": bay, "controller": str(controller), "intensity": intensity}
