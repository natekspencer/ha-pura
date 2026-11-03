"""Tests for the Pura integration setup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration


async def test_card_registered(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_frontend: MagicMock
) -> None:
    """Test the bundled Pura card is served and loaded on every dashboard."""
    hass.http.async_register_static_paths.assert_awaited_once()
    (config,) = hass.http.async_register_static_paths.await_args.args[0]
    assert config.url_path == "/pura/pura-diffuser.js"
    assert Path(config.path).is_file()
    assert config.path.endswith("custom_components/pura/www/pura-diffuser.js")

    mock_frontend.assert_called_once()
    integration = await async_get_integration(hass, DOMAIN)
    assert integration.version
    assert (
        mock_frontend.call_args.args[1]
        == f"/pura/pura-diffuser.js?v={integration.version}"
    )
