"""Diagnostics support for Pura."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from . import PuraConfigEntry

TO_REDACT = {
    CONF_LATITUDE,
    CONF_LONGITUDE,
    "device_id",
    "deviceId",
    "mac",
    "pk",
    "serialNumber",
    "sk",
    "uid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PuraConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    A car read over Bluetooth shows the reading under "bluetooth". Its values replace
    the cloud's until the cloud has newer data.
    """
    coordinator = entry.runtime_data.coordinator
    data = dict(coordinator.data)
    for device_id, (read_at, status) in coordinator.car_readings.items():
        if device_id in data:
            data[device_id] = data[device_id] | {
                "bluetooth": {"readAt": int(read_at), **asdict(status)}
            }
    return async_redact_data(data, TO_REDACT)
