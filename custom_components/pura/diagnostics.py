"""Diagnostics support for Pura."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pypura.utils import redact_id, redact_ids

from homeassistant.components.diagnostics.util import async_redact_data
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from . import PuraConfigEntry

TO_REDACT = {
    CONF_LATITUDE,
    CONF_LONGITUDE,
    "pk",
    "serialId",
    "serialNumber",
    "sk",
    "ssid",
    "uid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PuraConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    A car read over Bluetooth shows the reading under "bluetooth". Its values replace
    the cloud's until the cloud has newer data.

    Device IDs and MACs keep their last 4 hex digits, so a device can still be matched
    with its log lines.
    """
    coordinator = entry.runtime_data.coordinator
    data: dict[str, Any] = {}
    for device_id, device in coordinator.data.items():
        if reading := coordinator.car_readings.get(device_id):
            read_at, status = reading
            device = device | {"bluetooth": {"readAt": int(read_at), **asdict(status)}}
        key = redact_id(device_id)
        # Two devices can share their last 4 digits
        while key in data:
            key += "*"
        data[key] = device
    return redact_ids(async_redact_data(data, TO_REDACT))
