"""Tests for the Pura select platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.pura.entity import get_active_bay
from homeassistant.components.select import (
    ATTR_OPTION,
    DOMAIN as SELECT_DOMAIN,
    SERVICE_SELECT_OPTION,
)
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant

from . import setup_integration
from .conftest import HOME_V5_ID

ENTITY_ID = "select.home_v5_fragrance"
INTENSITY_ENTITY_ID = "select.home_v5_intensity"
ACTIVE_AT = 1700000000


def _home_on_timer(
    devices: dict[str, dict[str, Any]], bay1_active_at: int, bay2_active_at: int
) -> dict[str, Any]:
    """Limit the account to a Home v5 running a timer started on bay 1."""
    home = devices[HOME_V5_ID]
    home |= {
        "controller": "timer",
        "schedules": [],
        "timer": {"bay": 1, "intensity": 5},
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    home["bay1"] |= {"activeAt": bay1_active_at, "fragrance": {"name": "Volcano"}}
    home["bay2"] |= {"activeAt": bay2_active_at, "fragrance": {"name": "Volcano"}}
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    return home


def test_get_active_bay() -> None:
    """Test the active bay comes from the bay's activation timestamp."""
    assert (
        get_active_bay({"bay1": {"activeAt": ACTIVE_AT}, "bay2": {"activeAt": 0}}) == 1
    )
    assert (
        get_active_bay({"bay1": {"activeAt": 0}, "bay2": {"activeAt": ACTIVE_AT}}) == 2
    )
    assert get_active_bay({"bay1": {"activeAt": ACTIVE_AT}, "bay2": None}) == 1
    assert get_active_bay({"bay1": {"activeAt": ACTIVE_AT}}) == 1
    assert get_active_bay({"bay1": {"activeAt": 0}, "bay2": {"activeAt": 0}}) is None
    assert get_active_bay({"bay1": None, "bay2": None}) is None


async def test_fragrance_follows_active_bay(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test the select shows the diffusing bay, not the bay a timer started on."""
    home = _home_on_timer(devices, 0, ACTIVE_AT)

    entry = await setup_integration(hass, [Platform.SELECT])
    coordinator = entry.runtime_data.coordinator
    assert hass.states.get(ENTITY_ID).state == "slot_2"

    # Between alternations no bay is active, so the timer's bay is still selected
    home["bay2"]["activeAt"] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "slot_1"

    # With the timer finished and nothing diffusing, the select is off
    home |= {"controller": "default", "timer": None}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == "off"


async def test_intensity_targets_active_bay(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test intensity changes go to the diffusing bay, not the timer's bay."""
    _home_on_timer(devices, 0, ACTIVE_AT)

    await setup_integration(hass, [Platform.SELECT])
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: INTENSITY_ENTITY_ID, ATTR_OPTION: "strong"},
        blocking=True,
    )

    mock_pura.set_intensity.assert_called_once_with(
        HOME_V5_ID, bay=2, controller="timer", intensity=10
    )


async def test_active_fragrance_matches_select(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test the active fragrance and select both follow the diffusing bay."""
    home = _home_on_timer(devices, ACTIVE_AT, 0)
    home["bay1"] |= {"id": ACTIVE_AT, "wearingTime": 3600, "remaining": {"percent": 90}}
    home["bay2"] |= {
        "id": ACTIVE_AT,
        "wearingTime": 3600,
        "remaining": {"percent": 90},
        "fragrance": {"name": "White Tea"},
    }

    await setup_integration(hass, [Platform.SELECT, Platform.SENSOR])
    assert hass.states.get(ENTITY_ID).state == "slot_1"
    assert hass.states.get("sensor.home_v5_active_fragrance").state == "Volcano"


async def test_intensity_shows_bay_value(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test the select shows the bay's intensity, as a timer's never updates."""
    home = _home_on_timer(devices, ACTIVE_AT, 0)
    home["deviceDefaults"] |= {"bay1Intensity": 10, "bay2Intensity": 1}

    # Correct from the first load, despite the timer's intensity of 5
    entry = await setup_integration(hass, [Platform.SELECT])
    coordinator = entry.runtime_data.coordinator
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "strong"

    # Changes to the bay's intensity are picked up
    home["deviceDefaults"]["bay1Intensity"] = 7
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "pronounced"

    # Each bay has its own intensity when auto-alternate switches bays
    home["bay1"]["activeAt"], home["bay2"]["activeAt"] = 0, ACTIVE_AT
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "subtle"

    # With no bay active, the timer's intensity is the only one to show
    home["bay2"]["activeAt"] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "medium"
