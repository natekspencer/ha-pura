"""Helpers."""

from __future__ import annotations

import re
from typing import Any

PARTIALLY_REDACTED = {"device_id", "deviceId", "mac"}
"""Fields holding a device ID or MAC, which keep enough to tell devices apart."""


def get_hardware_major_version(device: dict[str, Any]) -> str:
    """Get the major hardware version of a pura device."""
    return device.get("hwVersion", "").split(".")[0]


def redact_id(value: str) -> str:
    """Partially redact a device ID or MAC, keeping its last 4 hex digits.

    Separators and case are ignored, so a device's ID and MAC redact the same way
    (e.g. "AA:AA:AA:AA:AA:04" and "aaaaaaaaaa04" both become "**REDACTED**AA04").
    """
    return f"**REDACTED**{re.sub(r'[^0-9A-F]', '', value.upper())[-4:]}"


def redact_ids(data: Any) -> Any:
    """Partially redact the device IDs and MACs in nested data."""
    if isinstance(data, dict):
        return {
            key: (
                redact_id(value)
                if key in PARTIALLY_REDACTED and isinstance(value, str)
                else redact_ids(value)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [redact_ids(item) for item in data]
    return data
