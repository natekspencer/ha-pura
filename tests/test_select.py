"""Tests for the Pura select platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.pura.entity import get_active_bay
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import setup_integration
from .conftest import HOME_V5_ID

ENTITY_ID = "select.home_v5_fragrance"
ACTIVE_AT = 1700000000


@pytest.mark.parametrize(
    ("bay1", "bay2", "expected"),
    [
        (0, 0, None),
        (ACTIVE_AT, 0, 1),
        (0, ACTIVE_AT, 2),
        (ACTIVE_AT, ACTIVE_AT + 60, 2),  # bay 1 retained after a partial update
        (ACTIVE_AT + 60, ACTIVE_AT, 1),
    ],
)
def test_get_active_bay(bay1: int, bay2: int, expected: int | None) -> None:
    """Test the most recently activated bay is the active one."""
    device = {"bay1": {"activeAt": bay1}, "bay2": {"activeAt": bay2}}
    assert get_active_bay(device) == expected


def test_get_active_bay_single_slot() -> None:
    """Test devices without a second bay or with an empty bay."""
    assert get_active_bay({"bay1": {"activeAt": ACTIVE_AT}, "bay2": None}) == 1
    assert get_active_bay({"bay1": {"activeAt": ACTIVE_AT}}) == 1
    assert get_active_bay({"bay1": None, "bay2": None}) is None


async def test_fragrance_follows_active_bay(
    hass: HomeAssistant, mock_pura: MagicMock, devices: dict[str, dict[str, Any]]
) -> None:
    """Test the select shows the diffusing bay, not the bay a timer started on."""
    home = devices[HOME_V5_ID]
    home |= {
        "controller": "timer",
        "schedules": [],
        "timer": {"bay": 1, "intensity": 5},
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    home["bay1"] |= {"activeAt": 0, "fragrance": {"name": "Volcano"}}
    home["bay2"] |= {"activeAt": ACTIVE_AT, "fragrance": {"name": "Volcano"}}
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]

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
