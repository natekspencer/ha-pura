"""Tests for the Pura sensor platform."""

from __future__ import annotations

from datetime import timedelta
import time
from typing import Any
from unittest.mock import MagicMock, patch

from freezegun.api import FrozenDateTimeFactory
import pytest

from custom_components.pura.const import DOMAIN
from custom_components.pura.sensor import _async_migrate_entities
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr, entity_registry as er

from . import MockConfigEntry, mock_restore_cache_with_extra_data, setup_integration
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


VIAL_URL = "https://example.com/vials/volcano.png"


async def test_fragrance_vial_picture(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    mini_only: dict[str, dict[str, Any]],
) -> None:
    """Test a single-slot fragrance sensor exposes its vial image and color."""
    mini_only[HOME_MINI_ID]["bay1"]["fragrance"] |= {
        "vialUrl": VIAL_URL,
        "placeholderColor": "646b51",
    }
    await _setup(hass, config_entry)

    state = hass.states.get("sensor.home_mini_fragrance")
    assert state.state == "Volcano"
    assert state.attributes["entity_picture"] == VIAL_URL
    assert state.attributes["color"] == "#646B51"
    assert (
        "entity_picture"
        not in hass.states.get("sensor.home_mini_fragrance_remaining").attributes
    )

    # A new fragrance's image and color replace the old ones on refresh
    coordinator = config_entry.runtime_data.coordinator
    fragrance = mini_only[HOME_MINI_ID]["bay1"]["fragrance"]
    fragrance |= {"vialUrl": f"{VIAL_URL}?v=2", "placeholderColor": "#112233"}
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.home_mini_fragrance")
    assert state.attributes["entity_picture"] == f"{VIAL_URL}?v=2"
    assert state.attributes["color"] == "#112233"

    # ...and are removed when Pura stops providing them
    del fragrance["vialUrl"], fragrance["placeholderColor"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.home_mini_fragrance")
    assert state.state == "Volcano"
    assert "entity_picture" not in state.attributes
    assert "color" not in state.attributes


async def test_bay_fragrance_vial_picture(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test each slot's fragrance sensor exposes its own vial image and color."""
    home = devices[HOME_V5_ID]
    home |= {
        "controller": "default",
        "schedules": [],
        "timer": None,
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    for bay, fragrance in (
        (
            "bay1",
            {"name": "Volcano", "vialUrl": VIAL_URL, "placeholderColor": "#A1B2C3"},
        ),
        ("bay2", {"name": "White Tea", "placeholderColor": "not a color"}),
    ):
        home[bay] |= {
            "id": 1700000000,
            "activeAt": 0,
            "wearingTime": 3600,
            "fragrance": fragrance,
            "remaining": {"percent": 90},
        }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)

    slot_1 = hass.states.get("sensor.home_v5_slot_1_fragrance")
    assert slot_1.attributes["entity_picture"] == VIAL_URL
    assert slot_1.attributes["color"] == "#A1B2C3"
    slot_2 = hass.states.get("sensor.home_v5_slot_2_fragrance")
    assert slot_2.state == "White Tea"
    assert "entity_picture" not in slot_2.attributes
    assert "color" not in slot_2.attributes
    assert hass.states.get("sensor.home_v5_active_fragrance").state == "none"

    # The active fragrance follows the bay that is diffusing
    home["bay2"]["activeAt"] = 1700000000
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_v5_active_fragrance").state == "White Tea"


async def test_luxe_sensors(
    hass: HomeAssistant, mock_pura: MagicMock, luxe: dict[str, Any]
) -> None:
    """Test the Luxe has sensors for all four slots, and follows its fourth bay."""
    luxe["bay4"] |= {
        "activeAt": 1700000000,
        "fragrance": {"name": "Volcano", "vialUrl": "https://example.com/vial.png"},
        "remaining": {"percent": 42},
    }
    await setup_integration(hass, [Platform.SENSOR])

    assert hass.states.get("sensor.home_luxe_active_fragrance").state == "Volcano"
    assert hass.states.get("sensor.home_luxe_slot_4_fragrance").state == "Volcano"
    assert (
        hass.states.get("sensor.home_luxe_slot_4_fragrance_remaining").state == "42.0"
    )
    assert hass.states.get("sensor.home_luxe_slot_3_fragrance").state == "unavailable"
    assert hass.states.get("sensor.home_luxe_controller").state == "default"


async def test_two_slot_devices_have_no_third_slot(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test the extra slots are only created for the Luxe."""
    home = devices[HOME_V5_ID]
    home |= {"controller": "default", "schedules": [], "timer": None}
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await setup_integration(hass, [Platform.SENSOR])

    assert entity_registry.async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{HOME_V5_ID}-bay_2"
    )
    assert not entity_registry.async_get_entity_id(
        SENSOR_DOMAIN, DOMAIN, f"{HOME_V5_ID}-bay_3"
    )


async def test_ended_timer_is_not_active(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Test a timer the API left behind after it ended is not shown as diffusing."""
    home = devices[HOME_V5_ID]
    # How the API reports a device after its timer ends
    home |= {
        "controller": "timer",
        "diffusionMode": "standard",
        "oscillation": None,
        "schedules": [],
        "timer": None,
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    home["bay1"] |= {
        "id": 1700000000,
        "activeAt": 1700000000,
        "wearingTime": 3600,
        "fragrance": {"name": "Volcano"},
        "remaining": {"percent": 90},
    }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    assert hass.states.get("sensor.home_v5_active_fragrance").state == "none"
    assert hass.states.get("sensor.home_v5_controller").state == "default"
    # The runtime stops counting from when the bay was activated
    assert float(hass.states.get("sensor.home_v5_slot_1_runtime").state) == 1.0

    # Auto-alternate running without a timer is tracked in the oscillation state,
    # which still reports the timer as its controller
    home |= {
        "diffusionMode": "oscillation-multi-bay",
        "oscillation": {"state": {"controllingFeature": "timer", "currentIndex": 0}},
    }
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_v5_active_fragrance").state == "Volcano"
    assert hass.states.get("sensor.home_v5_controller").state == "default"
    assert hass.states.get("sensor.home_v5_timer").state == "unknown"

    # A timer without auto-alternate is running while it has its own details
    home |= {
        "diffusionMode": "standard",
        "oscillation": None,
        "timer": {"bay": 1, "intensity": 5, "start": 1700000000, "end": 1700003600},
    }
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.home_v5_active_fragrance").state == "Volcano"
    assert hass.states.get("sensor.home_v5_controller").state == "timer"


async def test_runtime_holds_when_timer_ends(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the runtime stops at a timer's end and doesn't drop when it's cleared."""
    freezer.move_to("2026-06-15 12:00:00+00:00")
    now = int(time.time())
    home = devices[HOME_V5_ID]
    # A two hour timer that started an hour ago, on a vial that had run for an hour
    home |= {
        "controller": "timer",
        "diffusionMode": "standard",
        "oscillation": None,
        "schedules": [],
        "timer": {"bay": 1, "intensity": 5, "start": now - 3600, "end": now + 3600},
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    home["bay1"] |= {
        "id": 1700000000,
        "activeAt": now - 3600,
        "wearingTime": 3600,
        "fragrance": {"name": "Volcano"},
        "remaining": {"percent": 90},
    }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data.coordinator

    def runtime() -> float:
        return float(hass.states.get("sensor.home_v5_slot_1_runtime").state)

    async def refresh() -> None:
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert runtime() == 2

    # A timer still reported after it ends stops counting at its end
    freezer.tick(timedelta(hours=1, minutes=30))
    await refresh()
    assert runtime() == 3

    # The timer is cleared first, leaving the runtime from before it started
    home["timer"] = None
    await refresh()
    assert runtime() == 3

    # The bay can also stop before its stored runtime catches up
    home["controller"] = "default"
    home["bay1"]["activeAt"] = 0
    await refresh()
    assert runtime() == 3

    # Then the stored runtime catches up
    home["bay1"]["wearingTime"] = 10800
    await refresh()
    assert runtime() == 3

    # The vial ID can briefly go missing without losing the hold
    home["bay1"] |= {"id": None, "wearingTime": 3600}
    await refresh()
    assert runtime() == 3
    home["bay1"]["id"] = 1700000000
    await refresh()
    assert runtime() == 3

    # A new vial still starts its runtime over
    home |= {"controller": "timer", "timer": None}
    home["bay1"] |= {"id": 1800000000, "activeAt": now, "wearingTime": 0}
    await refresh()
    assert runtime() == 0


@pytest.mark.parametrize(
    ("extra_data", "vial_id", "wearing_time", "expected"),
    [
        # A different vial starts over
        ({"vial": 1600000000, "runtime": 10800}, 1700000000, 3600, 1),
        # A saved state without the vial it was held for
        ({}, 1700000000, 3600, 1),
        # A missing vial ID doesn't match another missing one
        ({"vial": None, "runtime": 10800}, None, 3600, 1),
        # Nothing saved, as before the runtime was held
        (None, 1700000000, 3600, 1),
        # A saved runtime that isn't a number of seconds
        ({"vial": 1700000000, "runtime": True}, 1700000000, 0, 0),
    ],
)
async def test_runtime_restore_needs_same_vial(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    extra_data: dict[str, Any] | None,
    vial_id: int | None,
    wearing_time: int,
    expected: float,
) -> None:
    """Test a restored runtime is only used for the vial it was held for."""
    entity_id = "sensor.home_v5_slot_1_runtime"
    if extra_data is not None:
        mock_restore_cache_with_extra_data(hass, [(State(entity_id, "3"), extra_data)])
    home = devices[HOME_V5_ID]
    home |= {"controller": "default", "schedules": [], "timer": None}
    home["bay1"] |= {
        "id": vial_id,
        "activeAt": 0,
        "wearingTime": wearing_time,
        "fragrance": {"name": "Volcano"},
        "remaining": {"percent": 90},
    }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)

    assert float(hass.states.get(entity_id).state) == expected


async def test_runtime_hold_survives_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the runtime a sensor holds is saved and restored when it reloads."""
    freezer.move_to("2026-06-15 12:00:00+00:00")
    now = int(time.time())
    entity_id = "sensor.home_v5_slot_1_runtime"
    home = devices[HOME_V5_ID]
    home |= {"controller": "default", "schedules": [], "timer": None}
    home["bay1"] |= {
        "id": 1700000000,
        "activeAt": now - 3600,
        "wearingTime": 3600,
        "fragrance": {"name": "Volcano"},
        "remaining": {"percent": 90},
    }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)
    assert float(hass.states.get(entity_id).state) == 2

    # The bay stops before its stored runtime catches up
    home["bay1"]["activeAt"] = 0
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == 2

    with patch("custom_components.pura.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_reload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == 2

    # The restored runtime is still held on the next update
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).state) == 2


async def test_runtime_ignores_bay_from_before_timer(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test a bay's old activation doesn't count while a timer runs another bay."""
    freezer.move_to("2026-06-15 12:00:00+00:00")
    now = int(time.time())
    home = devices[HOME_V5_ID]
    # A timer on bay 2 started an hour ago, while bay 1 kept an older activation
    home |= {
        "controller": "timer",
        "diffusionMode": "standard",
        "oscillation": None,
        "schedules": [],
        "timer": {"bay": 2, "intensity": 5, "start": now - 3600, "end": now + 3600},
        "deviceDefaults": {"bay1Intensity": 5, "bay2Intensity": 5},
    }
    for bay, active_at in (("bay1", now - 7200), ("bay2", now - 3600)):
        home[bay] |= {
            "id": 1700000000,
            "activeAt": active_at,
            "wearingTime": 3600,
            "fragrance": {"name": "Volcano"},
            "remaining": {"percent": 90},
        }
    for device_id in list(devices):
        if device_id != HOME_V5_ID:
            del devices[device_id]
    await _setup(hass, config_entry)

    def runtime(bay: int) -> float:
        return float(hass.states.get(f"sensor.home_v5_slot_{bay}_runtime").state)

    assert runtime(1) == 1
    assert runtime(2) == 2

    # Still after the timer ends
    freezer.tick(timedelta(hours=2))
    await config_entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert runtime(1) == 1
    assert runtime(2) == 3
