"""Tests for the Pura binary sensor platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from homeassistant.components.binary_sensor import DOMAIN as BINARY_SENSOR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .conftest import CAR_PRO_ID, HOME_MINI_ID, HOME_V3_ID, HOME_V5_ID


@pytest.fixture
def platforms() -> list[Platform]:
    """Return the platforms to set up."""
    return [Platform.BINARY_SENSOR]


def _state(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, device_id: str, key: str
) -> str | None:
    """Return the state of a binary sensor by device and description key."""
    if not (
        entity_id := entity_registry.async_get_entity_id(
            BINARY_SENSOR_DOMAIN, DOMAIN, f"{device_id}-{key}"
        )
    ):
        return None
    return hass.states.get(entity_id).state


@pytest.mark.parametrize(
    ("device_id", "key", "expected"),
    [
        (HOME_V3_ID, "bay_1_low_fragrance", STATE_OFF),
        (HOME_V3_ID, "bay_2_low_fragrance", STATE_UNAVAILABLE),
        (HOME_V3_ID, "connected", STATE_ON),
        (HOME_V3_ID, "low_fragrance", None),
        (HOME_V5_ID, "bay_1_low_fragrance", STATE_OFF),
        (HOME_V5_ID, "bay_2_low_fragrance", STATE_ON),
        (HOME_MINI_ID, "low_fragrance", STATE_ON),
        (HOME_MINI_ID, "bay_1_low_fragrance", None),
        (CAR_PRO_ID, "low_fragrance", STATE_OFF),
        (CAR_PRO_ID, "connected", None),
    ],
    ids=[
        "home_v3_slot_1",
        "home_v3_empty_slot_2",
        "home_v3_connected",
        "home_v3_no_single_slot_sensor",
        "home_v5_slot_1",
        "home_v5_slot_2_low",
        "home_mini_remaining_fallback",
        "home_mini_no_slot_sensor",
        "car_pro",
        "car_pro_no_connected",
    ],
)
async def test_binary_sensors(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    device_id: str,
    key: str,
    expected: str | None,
) -> None:
    """Test the binary sensors created for each device and their states."""
    assert _state(hass, entity_registry, device_id, key) == expected


async def test_slot_low_fragrance_name(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
) -> None:
    """Test per-slot sensors include the slot number in their name."""
    entity_id = entity_registry.async_get_entity_id(
        BINARY_SENSOR_DOMAIN, DOMAIN, f"{HOME_V5_ID}-bay_2_low_fragrance"
    )
    assert entity_id == "binary_sensor.home_v5_slot_2_low_fragrance"
    assert (
        hass.states.get(entity_id).attributes["friendly_name"]
        == "Home v5 Slot 2 low fragrance"
    )


async def test_low_fragrance_updates(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test low fragrance updates and becomes available when a slot is filled."""
    entry = await setup_integration(hass, [Platform.BINARY_SENSOR])
    assert _state(hass, entity_registry, HOME_V3_ID, "bay_2_low_fragrance") == (
        STATE_UNAVAILABLE
    )

    devices[HOME_V3_ID]["bay1"]["lowFragrance"] = True
    devices[HOME_V3_ID]["bay2"] = {"code": "WHTH", "lowFragrance": False}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, entity_registry, HOME_V3_ID, "bay_1_low_fragrance") == STATE_ON
    assert _state(hass, entity_registry, HOME_V3_ID, "bay_2_low_fragrance") == (
        STATE_OFF
    )
