"""Helpers."""

from __future__ import annotations

import re
from typing import Any

from pypura.utils import redact_id


def get_hardware_major_version(device: dict[str, Any]) -> str:
    """Get the major hardware version of a pura device."""
    return device.get("hwVersion", "").split(".")[0]


def redact_id_in(text: object, device_id: str) -> str:
    """Partially redact a device ID or MAC wherever it shows in text, e.g. an error.

    Errors can quote it, say in a request's URL or a Bluetooth address, in any case
    and with colons, hyphens, URL-encoded colons or no separators at all.
    """
    if not (digits := re.sub(r"[^0-9A-Fa-f]", "", device_id)):
        return str(text)
    pattern = "(?::|-|%3A)?".join(
        re.escape(digits[i : i + 2]) for i in range(0, len(digits), 2)
    )
    return re.sub(pattern, redact_id(device_id), str(text), flags=re.IGNORECASE)
