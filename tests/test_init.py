"""Tests for the Pura integration setup."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from pypura import PuraApiException
import pytest

from custom_components.pura.const import DOMAIN
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.loader import async_get_integration

from . import MockConfigEntry, setup_integration


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


async def test_account_without_devices_removes_all_devices(
    hass: HomeAssistant, mock_pura: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test devices removed from the account are removed from Home Assistant."""
    entry = await setup_integration(hass, [Platform.SENSOR])
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    caplog.clear()
    mock_pura.get_devices.return_value = {}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.last_update_success
    assert not dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    assert not er.async_entries_for_config_entry(entity_registry, entry.entry_id)
    assert "Traceback" not in caplog.text


async def test_failed_update_keeps_devices(
    hass: HomeAssistant, mock_pura: MagicMock
) -> None:
    """Test a failed update isn't taken to mean the devices were removed."""
    entry = await setup_integration(hass, [Platform.SENSOR])
    device_registry = dr.async_get(hass)
    device_count = len(
        dr.async_entries_for_config_entry(device_registry, entry.entry_id)
    )
    assert device_count

    mock_pura.get_devices.side_effect = PuraApiException("Invalid response")
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not entry.runtime_data.coordinator.last_update_success
    assert (
        len(dr.async_entries_for_config_entry(device_registry, entry.entry_id))
        == device_count
    )


async def test_unload_stops_subscriber(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test unloading the integration stops the websocket subscriber."""
    subscriber = init_integration.runtime_data.coordinator.subscriber

    assert await hass.config_entries.async_unload(init_integration.entry_id)

    subscriber.stop.assert_awaited_once_with()
