"""Read Pura Car diffusers over Bluetooth while they're in range.

A car only syncs with the cloud when someone opens the Pura app, so its cloud data
can be hours old. While it's on, it advertises a Bluetooth service and answers
locally, so whenever Home Assistant sees one of the account's cars it reads it and
shows that until the cloud catches up. Nothing is sent to the cloud.
"""

from __future__ import annotations

import logging
import re
import time

from pypura import PuraBluetoothError
from pypura.car_ble import CAR_SERVICE_UUID, read_car_status

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .coordinator import PuraDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# How often to read a car while it's in range, or retry one that couldn't be read
READ_INTERVAL = 300


def _normalize(address: str) -> str:
    """Return a MAC address as uppercase hex digits, e.g. "AAAAAAAAAA04"."""
    return re.sub(r"[^0-9A-F]", "", address.upper())


@callback
def async_setup_car_bluetooth(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: PuraDataUpdateCoordinator
) -> None:
    """Read the account's cars when Home Assistant sees them over Bluetooth."""
    if "bluetooth" not in hass.config.components:
        return

    last_read: dict[str, float] = {}  # by device ID, including failed attempts
    reading: set[str] = set()

    def _find_car(address: str) -> str | None:
        """Return the ID of the account's car with this Bluetooth address."""
        mac = _normalize(address)
        return next(
            (
                device_id
                for device_id, device in coordinator.devices.items()
                if device.get("modelType") == "car" and _normalize(device_id) == mac
            ),
            None,
        )

    async def _async_read(device_id: str, address: str) -> None:
        try:
            if not (
                ble_device := bluetooth.async_ble_device_from_address(
                    hass, address, connectable=True
                )
            ):
                return
            status = await read_car_status(ble_device)
        except PuraBluetoothError as err:
            _LOGGER.debug("Couldn't read %s over Bluetooth: %s", device_id, err)
            return
        finally:
            reading.discard(device_id)
        if _normalize(status.mac) != _normalize(device_id):
            _LOGGER.debug("%s reported a different MAC: %s", device_id, status.mac)
            return
        _LOGGER.debug("Read %s over Bluetooth: %s", device_id, status)
        coordinator.async_set_car_status(device_id, status, time.time())

    @callback
    def _async_discovered(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        if not (device_id := _find_car(service_info.address)) or device_id in reading:
            return
        now = time.monotonic()
        if now - last_read.get(device_id, -READ_INTERVAL) < READ_INTERVAL:
            return
        last_read[device_id] = now
        reading.add(device_id)
        entry.async_create_background_task(
            hass,
            _async_read(device_id, service_info.address),
            f"Read Pura Car {device_id} over Bluetooth",
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_discovered,
            bluetooth.BluetoothCallbackMatcher(
                service_uuid=CAR_SERVICE_UUID, connectable=True
            ),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )
