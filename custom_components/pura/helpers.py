"""Helpers."""

from __future__ import annotations

from typing import Any


def get_hardware_major_version(device: dict[str, Any]) -> str:
    """Get the major hardware version of a pura device."""
    return device.get("hwVersion", "").split(".")[0]
