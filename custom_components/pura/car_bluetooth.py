"""Read Pura Car diffusers over Bluetooth while they're in range.

A car only syncs with the cloud when someone opens the Pura app, so its cloud data
can be hours old. While it's on, it advertises a Bluetooth service and answers
locally, so whenever Home Assistant sees one of the account's cars it reads it and
shows that until the cloud catches up. Nothing is sent to the cloud.
"""

from __future__ import annotations

from datetime import datetime
import logging
import re
import time

from pypura import PuraBluetoothError
from pypura.car_ble import CAR_SERVICE_UUID, read_car_status

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .coordinator import PuraDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# How often to read a car while it's in range, including after a failed read
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

    reading: set[str] = set()  # device IDs being read
    # The next read of each car still in range. A car repeating the same
    # advertisement doesn't call `_async_discovered` again, so it's read on a timer.
    next_reads: dict[str, CALLBACK_TYPE] = {}
    unloaded = False

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

    @callback
    def _async_start_read(device_id: str, address: str) -> None:
        reading.add(device_id)
        entry.async_create_background_task(
            hass,
            _async_read(device_id, address),
            f"Read Pura Car {device_id} over Bluetooth",
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
            _async_schedule_read(device_id, address)
        if _normalize(status.mac) != _normalize(device_id):
            _LOGGER.debug("%s reported a different MAC: %s", device_id, status.mac)
            return
        _LOGGER.debug("Read %s over Bluetooth: %s", device_id, status)
        coordinator.async_set_car_status(device_id, status, time.time())

    @callback
    def _async_schedule_read(device_id: str, address: str) -> None:
        """Read the car again after READ_INTERVAL, if it's still in range."""
        if unloaded:
            return

        @callback
        def _async_read_again(_: datetime) -> None:
            del next_reads[device_id]
            if bluetooth.async_address_present(hass, address, connectable=True):
                _async_start_read(device_id, address)

        next_reads[device_id] = async_call_later(hass, READ_INTERVAL, _async_read_again)

    @callback
    def _async_discovered(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        device_id = _find_car(service_info.address)
        # A car being read, or due to be read again, isn't read now too
        if device_id and device_id not in reading and device_id not in next_reads:
            _async_start_read(device_id, service_info.address)

    @callback
    def _async_unload() -> None:
        nonlocal unloaded
        unloaded = True
        for cancel in next_reads.values():
            cancel()
        next_reads.clear()

    entry.async_on_unload(_async_unload)
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
