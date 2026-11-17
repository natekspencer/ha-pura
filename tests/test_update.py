"""Tests for the Pura update platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from homeassistant.components.update import ATTR_IN_PROGRESS, ATTR_UPDATE_PERCENTAGE
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from . import setup_integration
from .conftest import HOME_V5_ID

ENTITY_ID = "update.home_v5_firmware"


@pytest.mark.parametrize(
    ("ota", "in_progress", "update_percentage"),
    [
        (None, False, None),
        ({"percent": 100, "status": "Finished"}, False, None),
        # An idle diffuser can report an empty or missing OTA status
        ({"percent": 0, "status": ""}, False, None),
        ({"percent": 0, "status": None}, False, None),
        ({"percent": 0}, False, None),
        ({"percent": 42, "status": "Downloading"}, True, 42),
    ],
)
async def test_in_progress(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    ota: dict[str, Any] | None,
    in_progress: bool,
    update_percentage: int | None,
) -> None:
    """Test an update only shows as installing while an OTA is running."""
    devices[HOME_V5_ID] |= {"ota": ota, "otaVer": "1.0.0"}

    await setup_integration(hass, [Platform.UPDATE])

    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_IN_PROGRESS] is in_progress
    assert state.attributes[ATTR_UPDATE_PERCENTAGE] == update_percentage
