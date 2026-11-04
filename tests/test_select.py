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
SCHEDULE_ID = "a1ebf574-ddcc-4261-9098-619ab8022037"


def _home_on_timer(
    devices: dict[str, dict[str, Any]], bay1_active_at: int, bay2_active_at: int
) -> dict[str, Any]:
    """Limit the account to an auto-alternating Home v5 on a timer started on bay 1."""
    home = devices[HOME_V5_ID]
    home |= {
        "controller": "timer",
        "diffusionMode": "oscillation-multi-bay",
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


def _home_on_schedule(
    devices: dict[str, dict[str, Any]], bay1_active_at: int, bay2_active_at: int
) -> dict[str, Any]:
    """Limit the account to an auto-alternating Home v5 on a schedule for bay 1."""
    home = _home_on_timer(devices, bay1_active_at, bay2_active_at)
    home |= {
        "controller": SCHEDULE_ID,
        "schedules": [{"id": SCHEDULE_ID, "bay": 1, "intensity": 7}],
        "timer": None,
    }
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
        {ATTR_ENTITY_ID: INTENSITY_ENTITY_ID, ATTR_OPTION: "intense"},
        blocking=True,
    )

    mock_pura.set_intensity.assert_called_once_with(
        HOME_V5_ID, bay=2, controller="default", intensity=10
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
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "intense"

    # Changes to the bay's intensity are picked up
    home["deviceDefaults"]["bay1Intensity"] = 7
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "strong"

    # Each bay has its own intensity when auto-alternate switches bays
    home["bay1"]["activeAt"], home["bay2"]["activeAt"] = 0, ACTIVE_AT
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "gentle"

    # With no bay active, the timer's bay is the one a change would go to
    home["bay2"]["activeAt"] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "strong"

    # The timer's intensity is the only one left without the bay's own
    home["deviceDefaults"] = {}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "medium"


async def test_intensity_auto_alternate_schedule(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test a schedule uses each bay's intensity when auto-alternating."""
    home = _home_on_schedule(devices, ACTIVE_AT, 0)
    home["deviceDefaults"] |= {"bay1Intensity": 10, "bay2Intensity": 1}

    entry = await setup_integration(hass, [Platform.SELECT])
    coordinator = entry.runtime_data.coordinator
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "intense"

    # Changes go to the bay, leaving the saved schedule alone
    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: INTENSITY_ENTITY_ID, ATTR_OPTION: "medium"},
        blocking=True,
    )
    mock_pura.set_intensity.assert_called_once_with(
        HOME_V5_ID, bay=1, controller="default", intensity=5
    )

    home["bay1"]["activeAt"], home["bay2"]["activeAt"] = 0, ACTIVE_AT
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "gentle"

    # With no bay active, the schedule's bay is the one a change would go to
    home["bay2"]["activeAt"] = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "intense"
    assert hass.states.get(ENTITY_ID).state == "slot_1"


async def test_intensity_standard_schedule(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test a schedule keeps its own intensity without auto-alternate."""
    home = _home_on_schedule(devices, ACTIVE_AT, 0)
    home["diffusionMode"] = "standard"
    home["deviceDefaults"]["bay1Intensity"] = 10

    await setup_integration(hass, [Platform.SELECT])
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "strong"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: INTENSITY_ENTITY_ID, ATTR_OPTION: "medium"},
        blocking=True,
    )
    mock_pura.set_intensity.assert_called_once_with(
        HOME_V5_ID, bay=1, controller=SCHEDULE_ID, intensity=5
    )


async def test_intensity_standard_timer(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test a timer keeps its own intensity without auto-alternate."""
    home = _home_on_timer(devices, ACTIVE_AT, 0)
    home["diffusionMode"] = "standard"
    home["deviceDefaults"]["bay1Intensity"] = 10

    await setup_integration(hass, [Platform.SELECT])
    assert hass.states.get(INTENSITY_ENTITY_ID).state == "medium"

    await hass.services.async_call(
        SELECT_DOMAIN,
        SERVICE_SELECT_OPTION,
        {ATTR_ENTITY_ID: INTENSITY_ENTITY_ID, ATTR_OPTION: "intense"},
        blocking=True,
    )
    mock_pura.set_intensity.assert_called_once_with(
        HOME_V5_ID, bay=1, controller="timer", intensity=10
    )
