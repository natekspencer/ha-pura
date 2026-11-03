"""Tests for the Pura integration setup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant


async def test_card_registered(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_frontend: MagicMock
) -> None:
    """Test the bundled Pura card is served and loaded on every dashboard."""
    hass.http.async_register_static_paths.assert_awaited_once()
    (config,) = hass.http.async_register_static_paths.await_args.args[0]
    assert config.url_path == "/pura/pura-card.js"
    assert Path(config.path).is_file()
    assert config.path.endswith("custom_components/pura/www/pura-card.js")

    mock_frontend.assert_called_once()
    assert mock_frontend.call_args.args[1].startswith("/pura/pura-card.js?v=")
