"""Tests for Pura diagnostics."""

from __future__ import annotations

import json
import re
from typing import Any
from unittest.mock import MagicMock

from custom_components.pura.diagnostics import async_get_config_entry_diagnostics
from homeassistant.core import HomeAssistant

from . import setup_integration
from .conftest import CAR_PRO_ID, HOME_MINI_ID, HOME_V5_ID


def _hex(value: str) -> str:
    return re.sub(r"[^0-9A-F]", "", value.upper())


async def test_device_ids_partially_redacted(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Device IDs keep their last 4 digits, including where they're keys."""
    entry = await setup_integration(hass, [])
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    car = diagnostics["**REDACTED**AA04"]
    assert car["deviceId"] == "**REDACTED**AA04"
    assert car["displayName"] == {"name": "Car Pro"}
    # No full ID is left anywhere, in any format
    dumped = _hex(json.dumps(diagnostics))
    for device_id in devices:
        assert _hex(device_id) not in dumped


async def test_identifying_details_redacted(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """A car's serial and the Wi-Fi network's name are redacted."""
    devices[CAR_PRO_ID]["serialId"] = "810-00000-XX00XX00000000"
    devices[HOME_MINI_ID]["wifi"] = {"rssi": -50, "ssid": "My Network"}
    entry = await setup_integration(hass, [])
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["**REDACTED**AA04"]["serialId"] == "**REDACTED**"
    assert diagnostics["**REDACTED**AA03"]["wifi"] == {
        "rssi": -50,
        "ssid": "**REDACTED**",
    }


async def test_devices_sharing_last_digits_kept(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Two devices whose IDs end the same both stay in the diagnostics."""
    other_id = "bb:bb:bb:bb:aa:02"  # ends like HOME_V5_ID
    devices[other_id] = devices[HOME_V5_ID] | {
        "deviceId": other_id,
        "displayName": {"name": "Other Home v5"},
    }
    entry = await setup_integration(hass, [])
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    names = {
        diagnostics[key]["displayName"]["name"]
        for key in ("**REDACTED**AA02", "**REDACTED**AA02*")
    }
    assert names == {"Home v5", "Other Home v5"}
