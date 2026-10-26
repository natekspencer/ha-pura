"""Tests for the Pura services."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from custom_components.pura.services import SERVICE_START_TIMER
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import HOME_V5_ID


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
