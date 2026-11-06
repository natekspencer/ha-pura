"""Tests for the Pura services."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.pura.const import DOMAIN
from custom_components.pura.services import SERVICE_START_TIMER
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from . import MockConfigEntry, setup_integration
from .conftest import HOME_LUXE_ID, HOME_V5_ID


async def _start_luxe_timer(hass: HomeAssistant, **data: Any) -> None:
    """Start a timer on the Home Luxe."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_TIMER,
        {
            ATTR_ENTITY_ID: "switch.home_luxe_away_mode",
            "intensity": 5,
            "duration": {"minutes": 30},
        }
        | data,
        blocking=True,
    )


async def test_start_timer(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    init_integration: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test starting a timer resolves the device from the targeted entity."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_START_TIMER,
        {
            ATTR_ENTITY_ID: "switch.home_v5_away_mode",
            "slot": 2,
            "intensity": 5,
            "duration": {"minutes": 30},
        },
        blocking=True,
    )

    mock_pura.set_timer.assert_called_once_with(
        HOME_V5_ID, bay=2, intensity=5, end=timedelta(minutes=30)
    )
    assert "config_entries" not in caplog.text


async def test_start_timer_no_pura_device(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test targeting an entity without a Pura device raises an error."""
    hass.states.async_set("switch.other", "off")

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_TIMER,
            {
                ATTR_ENTITY_ID: "switch.other",
                "intensity": 5,
                "duration": {"minutes": 30},
            },
            blocking=True,
        )

    assert err.value.translation_key == "no_devices_found"
    mock_pura.set_timer.assert_not_called()


async def test_start_timer_entry_not_loaded(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test targeting a device whose config entry is not loaded raises an error."""
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            SERVICE_START_TIMER,
            {
                ATTR_ENTITY_ID: "switch.home_v5_away_mode",
                "intensity": 5,
                "duration": {"minutes": 30},
            },
            blocking=True,
        )

    assert err.value.translation_key == "no_devices_found"
    mock_pura.set_timer.assert_not_called()


@pytest.mark.parametrize(
    ("bays", "expected"),
    [
        ({"bay3": {"code": "A", "remaining": {"percent": 90}}}, 3),
        (
            {
                "bay1": {"code": "A", "remaining": {"percent": 50}},
                "bay2": {"code": "B", "remaining": {"percent": 50}, "wearingTime": 9},
                "bay4": {"code": "C", "remaining": {"percent": 80}},
            },
            4,
        ),
        (
            {
                "bay2": {"code": "B", "remaining": {"percent": 50}, "wearingTime": 9},
                "bay3": {"code": "C", "remaining": {"percent": 50}, "wearingTime": 5},
            },
            3,
        ),
        (
            {
                "bay3": {"code": "C", "remaining": {"percent": 50}},
                "bay4": {"code": "D", "remaining": {"percent": 50}},
            },
            3,
        ),
    ],
    ids=["only_slot", "most_remaining", "least_runtime", "lowest_slot"],
)
async def test_start_timer_picks_best_slot(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    bays: dict[str, dict[str, Any]],
    expected: int,
) -> None:
    """Test a timer without a slot picks the best of the Luxe's four slots."""
    devices[HOME_LUXE_ID] |= {f"bay{i}": None for i in (1, 2, 3, 4)} | bays
    await setup_integration(hass, [Platform.SWITCH])
    await _start_luxe_timer(hass)
    assert mock_pura.set_timer.call_args.kwargs["bay"] == expected


async def test_start_timer_empty_luxe_slot(
    hass: HomeAssistant, mock_pura: MagicMock
) -> None:
    """Test a timer can't start on an empty Luxe slot."""
    await setup_integration(hass, [Platform.SWITCH])
    with pytest.raises(ServiceValidationError):
        await _start_luxe_timer(hass, slot=3)
    mock_pura.set_timer.assert_not_called()
