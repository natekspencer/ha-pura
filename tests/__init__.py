"""Tests for the Pura integration."""

from __future__ import annotations

from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant


async def setup_integration(
    hass: HomeAssistant, platforms: list[Platform]
) -> MockConfigEntry:
    """Set up the Pura integration with only the given platforms."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_USERNAME: "user@example.com"},
    )
    entry.add_to_hass(hass)

    with patch("custom_components.pura.PLATFORMS", platforms):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry
