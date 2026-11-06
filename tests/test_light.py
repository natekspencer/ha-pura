"""Tests for the Pura light platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import setup_integration


async def test_luxe_nightlight_when_reported(
    hass: HomeAssistant, mock_pura: MagicMock, luxe: dict[str, Any]
) -> None:
    """Test a Luxe that reports a nightlight gets a light."""
    luxe["deviceDefaults"] = {
        "nightlight": {"active": True, "brightness": 5, "color": "ffffff"}
    }
    await setup_integration(hass, [Platform.LIGHT])
    assert hass.states.get("light.home_luxe_nightlight").state == "on"


async def test_luxe_without_nightlight(
    hass: HomeAssistant, mock_pura: MagicMock, luxe: dict[str, Any]
) -> None:
    """Test a Luxe that doesn't report a nightlight gets no light."""
    await setup_integration(hass, [Platform.LIGHT])
    assert not hass.states.async_entity_ids("light")


async def test_luxe_nightlight_reported_later(
    hass: HomeAssistant, mock_pura: MagicMock, luxe: dict[str, Any]
) -> None:
    """Test a Luxe gets a light once it starts reporting a nightlight."""
    entry = await setup_integration(hass, [Platform.LIGHT])
    assert not hass.states.async_entity_ids("light")

    luxe["deviceDefaults"] = {
        "nightlight": {"active": True, "brightness": 5, "color": "ffffff"}
    }
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get("light.home_luxe_nightlight").state == "on"
