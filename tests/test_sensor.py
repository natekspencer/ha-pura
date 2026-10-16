"""Tests for the Pura sensor platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pura.const import DOMAIN
from custom_components.pura.sensor import _async_migrate_entities
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import HOME_MINI_ID, HOME_V5_ID

# TODO: Remove the migration tests along with _async_migrate_entities after April 2027
OLD_UNIQUE_ID = f"{HOME_MINI_ID}-bay_1_installed"
NEW_UNIQUE_ID = f"{HOME_MINI_ID}-fragrance_installed"


@pytest.fixture
def mini_only(devices: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Limit the account to a Home Mini with the data its sensors need."""
    mini = devices[HOME_MINI_ID]
    mini |= {"controller": "default", "schedules": [], "timer": None}
    mini["bay1"] |= {
        "id": 1700000000,
        "activeAt": 0,
        "wearingTime": 3600,
        "fragrance": {"name": "Volcano"},
        "remaining": {"percent": 90, "lowFragrance": False},
    }
    for device_id in list(devices):
        if device_id != HOME_MINI_ID:
            del devices[device_id]
    return devices


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a Pura config entry added to Home Assistant."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=DOMAIN, data={CONF_USERNAME: "user@example.com"}
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Set up the integration with only the sensor platform."""
    with patch("custom_components.pura.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


def _register_old(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    unique_id: str = OLD_UNIQUE_ID,
    object_id: str = "home_mini_slot_installed",
    device_name: str | None = "Home Mini",
) -> er.RegistryEntry:
    """Register an installed sensor as created by previous versions."""
    device_id = None
    if device_name:
        device_id = (
            dr.async_get(hass)
            .async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, unique_id.split("-")[0])},
                name=device_name,
            )
            .id
        )
    return er.async_get(hass).async_get_or_create(
        SENSOR_DOMAIN,
        DOMAIN,
        unique_id,
        config_entry=entry,
        device_id=device_id,
        suggested_object_id=object_id,
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )


async def test_new_install(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test the Mini's installed sensor matches its other single-slot sensors."""
    await _setup(hass, config_entry)

    assert (
        entity_registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, NEW_UNIQUE_ID)
        == "sensor.home_mini_fragrance_installed"
    )
    assert (
        entity_registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, OLD_UNIQUE_ID)
        is None
    )
    assert entity_registry.async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{HOME_MINI_ID}-fragrance_remaining"
    ) == ("sensor.home_mini_fragrance_remaining")


async def test_migrate_installed_sensor(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test the existing entity is migrated in place rather than duplicated."""
    old = _register_old(hass, config_entry)
    assert old.entity_id == "sensor.home_mini_slot_installed"

    await _setup(hass, config_entry)

    migrated = entity_registry.async_get(old.id)
    assert migrated.unique_id == NEW_UNIQUE_ID
    assert migrated.entity_id == "sensor.home_mini_fragrance_installed"
    assert migrated.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert (
        entity_registry.async_get_entity_id(SENSOR_DOMAIN, DOMAIN, OLD_UNIQUE_ID)
        is None
    )
    assert [
        entry.id
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
        if entry.unique_id.endswith("installed")
    ] == [old.id]


async def test_migrate_keeps_custom_entity_id(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test a user-customized entity ID is kept when migrating."""
    old = _register_old(hass, config_entry, object_id="my_custom_sensor")

    await _setup(hass, config_entry)

    migrated = entity_registry.async_get(old.id)
    assert migrated.unique_id == NEW_UNIQUE_ID
    assert migrated.entity_id == "sensor.my_custom_sensor"


async def test_migrate_keeps_entity_id_when_new_one_taken(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test the entity ID is not changed if the new one is already in use."""
    old = _register_old(hass, config_entry)
    other = entity_registry.async_get_or_create(
        SENSOR_DOMAIN,
        "other",
        "other-id",
        suggested_object_id="home_mini_fragrance_installed",
    )

    await _setup(hass, config_entry)

    migrated = entity_registry.async_get(old.id)
    assert migrated.unique_id == NEW_UNIQUE_ID
    assert migrated.entity_id == "sensor.home_mini_slot_installed"
    assert entity_registry.async_get(other.id).entity_id == (
        "sensor.home_mini_fragrance_installed"
    )


async def test_migrate_ignores_dual_slot_devices(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test dual-slot devices keep their per-slot installed sensors."""
    wall = _register_old(
        hass,
        config_entry,
        unique_id=f"{HOME_V5_ID}-bay_1_installed",
        object_id="home_v5_slot_1_installed",
        device_name="Home v5",
    )
    coordinator = MagicMock(data=devices)

    _async_migrate_entities(hass, coordinator)

    unchanged = entity_registry.async_get(wall.id)
    assert unchanged.unique_id == f"{HOME_V5_ID}-bay_1_installed"
    assert unchanged.entity_id == "sensor.home_v5_slot_1_installed"


async def test_migrate_keeps_entity_id_when_state_exists(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test the entity ID is not changed if an unregistered entity uses it."""
    old = _register_old(hass, config_entry)
    hass.states.async_set("sensor.home_mini_fragrance_installed", "template")

    await _setup(hass, config_entry)

    migrated = entity_registry.async_get(old.id)
    assert migrated.unique_id == NEW_UNIQUE_ID
    assert migrated.entity_id == "sensor.home_mini_slot_installed"


async def test_migrate_keeps_custom_id_with_same_suffix(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test a customized entity ID is kept even if it ends with the old suffix."""
    old = _register_old(hass, config_entry, object_id="kitchen_slot_installed")

    await _setup(hass, config_entry)

    migrated = entity_registry.async_get(old.id)
    assert migrated.unique_id == NEW_UNIQUE_ID
    assert migrated.entity_id == "sensor.kitchen_slot_installed"


async def test_migrate_uses_renamed_device_name(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    device_registry: dr.DeviceRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test generated IDs from a user-renamed device are migrated."""
    old = _register_old(hass, config_entry, object_id="kitchen_slot_installed")
    device_registry.async_update_device(old.device_id, name_by_user="Kitchen")

    await _setup(hass, config_entry)

    assert entity_registry.async_get(old.id).entity_id == (
        "sensor.kitchen_fragrance_installed"
    )


async def test_migrate_device_discovered_after_setup(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
    config_entry: MockConfigEntry,
) -> None:
    """Test a Mini that appears after setup is migrated instead of duplicated."""
    old = _register_old(hass, config_entry, device_name=None)
    mini = mini_only.pop(HOME_MINI_ID)

    await _setup(hass, config_entry)
    assert entity_registry.async_get(old.id).unique_id == OLD_UNIQUE_ID

    mini_only[HOME_MINI_ID] = mini
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entity_registry.async_get(old.id).unique_id == NEW_UNIQUE_ID
    assert [
        entry.id
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
        if entry.unique_id.endswith("installed")
    ] == [old.id]
