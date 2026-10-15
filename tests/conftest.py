"""Fixtures for Pura tests."""

from __future__ import annotations

from collections.abc import Generator
import copy
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import setup_integration

HOME_V3_ID = "aa:aa:aa:aa:aa:01"
HOME_V5_ID = "aa:aa:aa:aa:aa:02"
HOME_MINI_ID = "aa:aa:aa:aa:aa:03"
CAR_PRO_ID = "aa:aa:aa:aa:aa:04"

DEVICES: dict[str, dict[str, Any]] = {
    HOME_V3_ID: {
        "deviceId": HOME_V3_ID,
        "deviceVer": "v2",
        "hwVersion": "2.5",
        "model": 1,
        "modelType": "wall",
        "displayName": {"name": "Home v3"},
        "deviceLocation": {"timezone": "America/New_York"},
        "ambientMode": False,
        "awayMode": {"away": False, "enabled": False},
    },
    HOME_V5_ID: {
        "deviceId": HOME_V5_ID,
        "deviceVer": "wall_5",
        "hwVersion": "35.22",
        "model": 1,
        "modelType": "wall",
        "displayName": {"name": "Home v5"},
        "deviceLocation": {"timezone": "America/New_York"},
        "ambientMode": False,
        "awayMode": {"away": False, "enabled": False},
        "diffusionMode": "standard",
        "capabilities": {"diffusionModes": ["standard", "oscillation-multi-bay"]},
    },
    HOME_MINI_ID: {
        "deviceId": HOME_MINI_ID,
        "deviceVer": "mini_1",
        "hwVersion": "26.12",
        "model": 4,
        "modelType": "mini",
        "displayName": {"name": "Home Mini"},
        "deviceLocation": {"timezone": "America/New_York"},
        "awayMode": {"away": False, "enabled": False},
        "diffusionMode": "standard",
        "capabilities": {"diffusionModes": ["standard"]},
    },
    CAR_PRO_ID: {
        "deviceId": CAR_PRO_ID,
        "deviceVer": "27",
        "hwVersion": "27.1",
        "model": 2,
        "modelType": "car",
        "displayName": {"name": "Car Pro"},
        "awayMode": {"away": False, "enabled": False},
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in all tests."""


@pytest.fixture
def devices() -> dict[str, dict[str, Any]]:
    """Return a copy of the device data returned by the API."""
    return copy.deepcopy(DEVICES)


@pytest.fixture
def mock_pura(devices: dict[str, dict[str, Any]]) -> Generator[MagicMock]:
    """Mock the Pura API client and websocket subscriber."""
    with (
        patch("custom_components.pura.Pura", autospec=True) as pura_cls,
        patch(
            "custom_components.pura.coordinator.WebSocketSubscriber"
        ) as subscriber_cls,
    ):
        client = pura_cls.return_value
        client.get_devices.return_value = devices
        client.get_tokens.return_value = {"id_token": "id-token"}
        client.get_latest_firmware_details.return_value = {}
        client.set_away_mode.return_value = True
        subscriber = subscriber_cls.return_value
        subscriber.is_running = True
        subscriber.stop = AsyncMock()
        yield client


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to set up."""
    return [Platform.SWITCH]


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_pura: MagicMock, platforms: list[Platform]
) -> MockConfigEntry:
    """Set up the Pura integration."""
    return await setup_integration(hass, platforms)
