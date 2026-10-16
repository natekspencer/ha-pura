"""Tests for the Pura switch platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from . import setup_integration
from .conftest import CAR_PRO_ID, HOME_MINI_ID, HOME_V3_ID, HOME_V5_ID


def _switch_keys(entity_registry: er.EntityRegistry, device_id: str) -> set[str]:
    """Return the switch description keys registered for a device."""
    prefix = f"{device_id}-"
    return {
        entry.unique_id.removeprefix(prefix)
        for entry in entity_registry.entities.values()
        if entry.domain == SWITCH_DOMAIN
        and entry.platform == DOMAIN
        and entry.unique_id.startswith(prefix)
    }


@pytest.mark.parametrize(
    ("device_id", "expected"),
    [
        (HOME_V3_ID, {"ambient_mode", "away_mode"}),
        (HOME_V5_ID, {"away_mode", "diffusion_mode"}),
        (HOME_MINI_ID, {"away_mode"}),
        (CAR_PRO_ID, set()),
    ],
    ids=["home_v3", "home_v5", "home_mini", "car_pro"],
)
async def test_switches_by_device(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    device_id: str,
    expected: set[str],
) -> None:
    """Test the switches created for each device."""
    assert _switch_keys(entity_registry, device_id) == expected


async def test_away_mode_added_when_reported(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test away mode is added once a device starts reporting it."""
    away_mode = devices[HOME_V5_ID].pop("awayMode")

    entry = await setup_integration(hass, [Platform.SWITCH])
    assert _switch_keys(entity_registry, HOME_V5_ID) == {"diffusion_mode"}

    devices[HOME_V5_ID]["awayMode"] = away_mode
    await _refresh(hass, entry)
    assert _switch_keys(entity_registry, HOME_V5_ID) == {
        "away_mode",
        "diffusion_mode",
    }

    # A further update should not attempt to re-add existing switches
    await _refresh(hass, entry)
    assert _switch_keys(entity_registry, HOME_V5_ID) == {
        "away_mode",
        "diffusion_mode",
    }
    assert "does not generate unique IDs" not in caplog.text


@pytest.mark.parametrize(
    ("away_mode", "expected"),
    [
        (None, False),
        ("enabled", False),
        ({}, False),
        ({"away": False}, False),
        ({"away": False, "enabled": False}, True),
    ],
    ids=["none", "string", "empty", "missing_enabled", "valid"],
)
async def test_away_mode_data(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    away_mode: Any,
    expected: bool,
) -> None:
    """Test away mode is only added when the device reports usable data."""
    devices[HOME_V5_ID]["awayMode"] = away_mode

    entry = await setup_integration(hass, [Platform.SWITCH])
    assert ("away_mode" in _switch_keys(entity_registry, HOME_V5_ID)) is expected

    # Valid data on a later update should add the switch
    devices[HOME_V5_ID]["awayMode"] = {"away": False, "enabled": False}
    await _refresh(hass, entry)
    assert "away_mode" in _switch_keys(entity_registry, HOME_V5_ID)


async def test_turn_on_away_mode(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    init_integration: MockConfigEntry,
) -> None:
    """Test turning on away mode uses the Home Assistant location as fallback."""
    entity_id = entity_registry.async_get_entity_id(
        SWITCH_DOMAIN, DOMAIN, f"{HOME_V5_ID}-away_mode"
    )
    assert entity_id
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    mock_pura.set_away_mode.assert_called_once_with(
        HOME_V5_ID,
        away_mode=True,
        latitude=hass.config.latitude,
        longitude=hass.config.longitude,
        radius=150,
    )


@pytest.mark.parametrize(
    ("capabilities", "expected"),
    [
        (None, False),
        ({}, False),
        ({"diffusionModes": None}, False),
        ({"diffusionModes": []}, False),
        ({"diffusionModes": ["standard"]}, False),
        ({"diffusionModes": ["standard", "oscillation-multi-bay"]}, True),
    ],
    ids=["none", "empty", "modes_none", "modes_empty", "single_mode", "multi_mode"],
)
async def test_diffusion_mode_capabilities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    capabilities: dict[str, Any] | None,
    expected: bool,
) -> None:
    """Test diffusion mode is only added when multiple modes are supported."""
    devices[HOME_V5_ID]["capabilities"] = capabilities

    await setup_integration(hass, [Platform.SWITCH])

    assert ("diffusion_mode" in _switch_keys(entity_registry, HOME_V5_ID)) is expected


async def test_diffusion_mode_added_when_capability_reported(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test diffusion mode is added once a device reports multiple modes."""
    capabilities = devices[HOME_V5_ID]["capabilities"]
    devices[HOME_V5_ID]["capabilities"] = {"diffusionModes": ["standard"]}

    entry = await setup_integration(hass, [Platform.SWITCH])
    assert _switch_keys(entity_registry, HOME_V5_ID) == {"away_mode"}

    devices[HOME_V5_ID]["capabilities"] = capabilities
    await _refresh(hass, entry)
    assert _switch_keys(entity_registry, HOME_V5_ID) == {
        "away_mode",
        "diffusion_mode",
    }


async def test_toggle_diffusion_mode(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test diffusion mode state and toggling between modes."""
    devices[HOME_V5_ID]["diffusionMode"] = "oscillation-multi-bay"
    await setup_integration(hass, [Platform.SWITCH])

    entity_id = entity_registry.async_get_entity_id(
        SWITCH_DOMAIN, DOMAIN, f"{HOME_V5_ID}-diffusion_mode"
    )
    assert entity_id
    assert hass.states.get(entity_id).state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_pura.set_diffusion_mode.assert_called_once_with(HOME_V5_ID, mode="standard")

    mock_pura.set_diffusion_mode.reset_mock()
    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    mock_pura.set_diffusion_mode.assert_called_once_with(
        HOME_V5_ID, mode="oscillation-multi-bay"
    )


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Refresh the device coordinator."""
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("device_id", "key", "entity_id", "name"),
    [
        (HOME_V3_ID, "ambient_mode", "switch.home_v3_ambient_mode", "Ambient mode"),
        (HOME_V5_ID, "away_mode", "switch.home_v5_away_mode", "Away mode"),
        (
            HOME_V5_ID,
            "diffusion_mode",
            "switch.home_v5_auto_alternate_fragrances",
            "Auto-alternate fragrances",
        ),
    ],
)
async def test_switch_names(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    device_id: str,
    key: str,
    entity_id: str,
    name: str,
) -> None:
    """Test switch names come from translations and keep their entity IDs."""
    assert (
        entity_registry.async_get_entity_id(SWITCH_DOMAIN, DOMAIN, f"{device_id}-{key}")
        == entity_id
    )
    assert hass.states.get(entity_id).attributes["friendly_name"].endswith(name)
