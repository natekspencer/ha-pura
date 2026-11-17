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
from .conftest import HOME_V5_ID


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


async def test_device_mac_not_used_as_serial_number(
    hass: HomeAssistant, mock_pura: MagicMock
) -> None:
    """Test the MAC isn't shown as a serial number and older ones are cleared."""
    entry = await setup_integration(hass, [Platform.SENSOR])
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, HOME_V5_ID), entry.entry_id
    )
    assert device
    assert device.serial_number is None

    # Earlier versions stored the MAC as the serial number.
    device_registry.async_update_device(device.id, serial_number=HOME_V5_ID)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    device = device_registry.async_get(device.id)
    assert device
    assert device.serial_number is None


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


async def test_failed_firmware_check_redacts_device_id(
    hass: HomeAssistant, mock_pura: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed firmware check's error doesn't log the full device ID."""

    def fail(device_id: str, *_: object) -> None:
        # A connection error quotes the request's URL, which holds the device ID
        raise PuraApiException(
            f"Failed to resolve: /v3/firmware/{device_id}/config "
            f"or {device_id.replace(':', '%3A').upper()}"
        )

    mock_pura.get_latest_firmware_details.side_effect = fail
    entry = await setup_integration(hass, [Platform.SENSOR])
    await entry.runtime_data.firmware_coordinator.async_refresh()

    assert (
        "Firmware check failed for **REDACTED**AA02: Failed to resolve: "
        "/v3/firmware/**REDACTED**AA02/config or **REDACTED**AA02"
    ) in caplog.text
    assert HOME_V5_ID not in caplog.text.lower()
    assert HOME_V5_ID.replace(":", "") not in caplog.text.lower()


async def test_unload_stops_subscriber(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test unloading the integration stops the websocket subscriber."""
    subscriber = init_integration.runtime_data.coordinator.subscriber

    assert await hass.config_entries.async_unload(init_integration.entry_id)

    subscriber.stop.assert_awaited_once_with()
