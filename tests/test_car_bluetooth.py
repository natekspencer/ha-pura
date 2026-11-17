"""Tests for reading Pura Car diffusers over Bluetooth."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
import copy
from datetime import timedelta
import logging
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pypura import PuraApiException, PuraBluetoothError
from pypura.car_ble import PuraCarStatus
import pytest

from custom_components.pura import async_unload_entry, car_bluetooth
from custom_components.pura.car_bluetooth import READ_INTERVAL
from custom_components.pura.diagnostics import async_get_config_entry_diagnostics
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.file import WriteError

from . import MockConfigEntry, async_fire_time_changed, setup_integration
from .conftest import CAR_PRO_ID, HOME_V5_ID

ADDRESS = "AA:AA:AA:AA:AA:04"  # CAR_PRO_ID
CLOUD_AT = int(time.time()) - 3600  # when the app last synced the car
STATUS = PuraCarStatus(
    mac="AAAAAAAAAA04",
    firmware="9.1.16",
    hardware="27.5",
    battery_level=90,
    charging=True,
    intensity="high",
    fragrance_code="FZYC",
    cartridge_id="pod-1",
    runtime=192120,
)

type Discover = Callable[[str], None]


@pytest.fixture
def car(devices: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Limit the account to the Car Pro and a Home v5, with the data they need."""
    for device_id in list(devices):
        if device_id not in (CAR_PRO_ID, HOME_V5_ID):
            del devices[device_id]
    devices[HOME_V5_ID] |= {"controller": "default", "schedules": [], "timer": None}
    device = devices[CAR_PRO_ID]
    device |= {
        "batteryRemaining": 45,
        "fwVersion": "9.1.10",
        "lastConnectedAt": CLOUD_AT,
    }
    device["bay1"] = {
        "id": 1,
        "activeAt": CLOUD_AT,
        "code": "FZYC",
        "fanIntensity": "low",
        "lowFragrance": True,
        "refillId": "pod-1",
        "wearingTime": 181236,
        "fragrance": {"name": "Fresh Sea Salt", "expectedLifeHours": 60},
    }
    return device


@pytest.fixture
def read_car() -> Generator[AsyncMock]:
    """Mock reading a car, returning STATUS."""
    with patch.object(
        car_bluetooth, "read_car_status", AsyncMock(return_value=STATUS)
    ) as read:
        yield read


@pytest.fixture
def present() -> Generator[MagicMock]:
    """Mock whether a car is still in range, which it is by default."""
    with patch.object(
        car_bluetooth.bluetooth, "async_address_present", return_value=True
    ) as present:
        yield present


@pytest.fixture
def register(present: MagicMock) -> Generator[MagicMock]:
    """Mock Home Assistant's Bluetooth callbacks."""
    with (
        patch.object(
            car_bluetooth.bluetooth, "async_register_callback", return_value=MagicMock()
        ) as register,
        patch.object(
            car_bluetooth.bluetooth,
            "async_ble_device_from_address",
            side_effect=lambda hass, address, connectable: MagicMock(address=address),
        ),
    ):
        yield register


async def _setup(
    hass: HomeAssistant, register: MagicMock, *, bluetooth: bool = True
) -> tuple[MockConfigEntry, Discover]:
    """Set up the integration and return a function that advertises an address."""
    if bluetooth:
        hass.config.components.add("bluetooth")
    entry = await setup_integration(hass, [Platform.SENSOR])

    def discover(address: str) -> None:
        callback = register.call_args.args[1]
        callback(MagicMock(address=address), MagicMock())

    return entry, discover


def _state(hass: HomeAssistant, key: str) -> str:
    return hass.states.get(f"sensor.car_pro_{key}").state


@pytest.mark.usefixtures("mock_pura", "car")
async def test_reading_updates_car(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A car in range is read, and its entities show the reading."""
    _, discover = await _setup(hass, register)
    assert _state(hass, "battery") == "45"
    matcher = register.call_args.args[2]
    assert matcher["service_uuid"] == car_bluetooth.CAR_SERVICE_UUID
    assert matcher["connectable"]

    before = time.time()
    discover(ADDRESS)
    await hass.async_block_till_done()

    read_car.assert_awaited_once()
    assert read_car.call_args.args[0].address == ADDRESS
    assert _state(hass, "battery") == "90"
    assert _state(hass, "fan_intensity") == "high"
    assert _state(hass, "fragrance") == "Fresh Sea Salt"
    assert float(_state(hass, "runtime")) == pytest.approx(192120 / 3600, abs=0.01)
    last_active = hass.states.get("sensor.car_pro_last_active")
    assert last_active.state >= time.strftime(
        "%Y-%m-%dT%H:%M", time.gmtime(before - 60)
    )
    # The same pod keeps the cloud's low fragrance flag
    coordinator = hass.config_entries.async_entries("pura")[0].runtime_data.coordinator
    assert coordinator.devices[CAR_PRO_ID]["bay1"]["lowFragrance"] is True
    assert coordinator.devices[CAR_PRO_ID]["fwVersion"] == "9.1.16"


NEW_POD = PuraCarStatus(
    **STATUS.__dict__ | {"fragrance_code": "NDMH", "cartridge_id": "pod-2"}
)
NEW_FRAGRANCE = {
    "fragranceCode": "NDMH",
    "fragranceFormat": "puck",
    "name": "Midnight Hour",
    "expectedLifeHours": 60,
}


def _car_lookups(pura: MagicMock) -> list[str]:
    """Return the codes looked up as car pods, leaving out the Home v5's vials."""
    return [
        call.args[0]
        for call in pura.get_fragrance.call_args_list
        if call.kwargs["fragrance_format"] == "puck"
    ]


@pytest.mark.usefixtures("car")
async def test_new_fragrance(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    devices: dict[str, dict[str, Any]],
    register: MagicMock,
    read_car: AsyncMock,
) -> None:
    """A new fragrance's details are looked up by its code."""
    mock_pura.get_fragrance.return_value = NEW_FRAGRANCE
    # Each poll gets the cloud's pod again, without the reading's
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    read_car.return_value = NEW_POD
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _car_lookups(mock_pura) == ["NDMH"]
    assert _state(hass, "fragrance") == "Midnight Hour"
    # 192120 seconds of a 60 hour pod
    assert float(_state(hass, "fragrance_remaining")) == pytest.approx(11.1, abs=0.1)
    bay = entry.runtime_data.coordinator.devices[CAR_PRO_ID]["bay1"]
    assert bay["lowFragrance"] is False

    # It's remembered, and shown again after the cloud's older data
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "fragrance") == "Midnight Hour"
    assert _car_lookups(mock_pura) == ["NDMH"]


@pytest.mark.usefixtures("car")
async def test_new_fragrance_not_found(
    hass: HomeAssistant, mock_pura: MagicMock, register: MagicMock, read_car: AsyncMock
) -> None:
    """A code with no fragrance shows the code, and isn't looked up again."""
    read_car.return_value = NEW_POD
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "fragrance") == "Unknown (NDMH)"
    assert "fragrance" not in entry.runtime_data.coordinator.devices[CAR_PRO_ID]["bay1"]
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _car_lookups(mock_pura) == ["NDMH"]


@pytest.mark.usefixtures("car")
async def test_new_fragrance_lookup_fails(
    hass: HomeAssistant, mock_pura: MagicMock, register: MagicMock, read_car: AsyncMock
) -> None:
    """A failed lookup shows the code, and is tried again on the next update."""
    mock_pura.get_fragrance.side_effect = PuraApiException("Request failed")
    read_car.return_value = NEW_POD
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert _state(hass, "fragrance") == "Unknown (NDMH)"

    mock_pura.get_fragrance.side_effect = None
    mock_pura.get_fragrance.return_value = NEW_FRAGRANCE
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _car_lookups(mock_pura) == ["NDMH", "NDMH"]
    assert _state(hass, "fragrance") == "Midnight Hour"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_new_pod_of_same_fragrance(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A new pod of the same fragrance keeps its name but isn't low."""
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__ | {"cartridge_id": "pod-2", "runtime": 60}
    )
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "fragrance") == "Fresh Sea Salt"
    assert (
        entry.runtime_data.coordinator.devices[CAR_PRO_ID]["bay1"]["lowFragrance"]
        is False
    )


@pytest.mark.usefixtures("car")
async def test_pod_removed(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    register: MagicMock,
    read_car: AsyncMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Without a pod, the fragrance entities are unavailable, but not the intensity."""
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__
        | {
            "intensity": "off",
            "fragrance_code": None,
            "cartridge_id": None,
            "runtime": None,
        }
    )
    # Each poll returns new data, like the API
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "fragrance") == "unavailable"
    assert _state(hass, "fan_intensity") == "off"
    assert _state(hass, "battery") == "90"

    # The cloud has no intensity without a pod, so it goes with the reading
    devices[CAR_PRO_ID] |= {"lastConnectedAt": int(time.time()) + 60, "bay1": None}
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "fan_intensity") == "unavailable"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_reading_without_battery(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A car without a battery (v1) leaves the cloud's battery value alone."""
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__ | {"battery_level": None, "charging": None}
    )
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "battery") == "45"
    assert _state(hass, "fan_intensity") == "high"


UNKNOWN_POD = PuraCarStatus(
    **STATUS.__dict__
    | {
        "intensity": "medium",
        "fragrance_code": None,
        "cartridge_id": None,
        "runtime": None,
        "unknown_pod": True,
    }
)


def _assert_unknown_pod(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """The car shows a pod it can't identify, as the app does, with no runtime."""
    assert _state(hass, "fragrance") == "Unknown (UKNC)"
    assert _state(hass, "runtime") == "unknown"
    assert _state(hass, "fragrance_remaining") == "unknown"
    assert _state(hass, "fan_intensity") == "medium"
    assert _state(hass, "battery") == "90"
    bay = entry.runtime_data.coordinator.devices[CAR_PRO_ID]["bay1"]
    assert bay["lowFragrance"] is False
    assert bay["activeAt"] > CLOUD_AT


@pytest.mark.usefixtures("mock_pura", "car")
async def test_unknown_pod_replaces_cloud_pod(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A newer reading of a pod the car can't identify replaces the cloud's pod."""
    read_car.return_value = UNKNOWN_POD
    entry, discover = await _setup(hass, register)
    assert _state(hass, "fragrance") == "Fresh Sea Salt"
    discover(ADDRESS)
    await hass.async_block_till_done()

    _assert_unknown_pod(hass, entry)


@pytest.mark.usefixtures("car")
async def test_unknown_pod_looked_up(
    hass: HomeAssistant, mock_pura: MagicMock, register: MagicMock, read_car: AsyncMock
) -> None:
    """A pod the car can't identify shows the API's "Unknown fragrance", still with
    no runtime or fragrance remaining, though the API gives it an expected life."""
    mock_pura.get_fragrance.return_value = {
        "fragranceCode": "UKNC",
        "fragranceFormat": "puck",
        "name": "Unknown fragrance",
        "expectedLifeHours": 30,
    }
    read_car.return_value = UNKNOWN_POD
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _car_lookups(mock_pura) == ["UKNC"]
    assert _state(hass, "fragrance") == "Unknown fragrance"
    assert _state(hass, "runtime") == "unknown"
    assert _state(hass, "fragrance_remaining") == "unknown"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_unknown_pod_replaces_last_reading(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A pod the car can't identify replaces the pod from its last reading too."""
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert float(_state(hass, "runtime")) == pytest.approx(192120 / 3600, abs=0.01)

    read_car.return_value = UNKNOWN_POD
    await _later(hass)

    assert read_car.await_count == 2
    _assert_unknown_pod(hass, entry)
    _, status = entry.runtime_data.coordinator.car_readings[CAR_PRO_ID]
    assert status == UNKNOWN_POD


@pytest.mark.usefixtures("mock_pura", "car")
async def test_unknown_pod_without_cloud_pod(
    hass: HomeAssistant,
    register: MagicMock,
    read_car: AsyncMock,
    car: dict[str, Any],
) -> None:
    """A pod the car can't identify shows even when the cloud has no pod."""
    car["bay1"] = None
    read_car.return_value = UNKNOWN_POD
    entry, discover = await _setup(hass, register)
    assert _state(hass, "fragrance") == "unavailable"
    discover(ADDRESS)
    await hass.async_block_till_done()

    _assert_unknown_pod(hass, entry)


@pytest.mark.usefixtures("car")
async def test_reading_kept_until_cloud_is_newer(
    hass: HomeAssistant,
    mock_pura: MagicMock,
    register: MagicMock,
    read_car: AsyncMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """Cloud refreshes with older data keep the reading; newer data replaces it."""
    # Each poll returns new data, like the API
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    entry, discover = await _setup(hass, register)
    coordinator = entry.runtime_data.coordinator
    discover(ADDRESS)
    await hass.async_block_till_done()

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "90"

    devices[CAR_PRO_ID]["lastConnectedAt"] = int(time.time()) + 60
    devices[CAR_PRO_ID]["batteryRemaining"] = 80
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "80"
    assert _state(hass, "fan_intensity") == "low"

    # And the outdated reading isn't applied again
    devices[CAR_PRO_ID]["lastConnectedAt"] = CLOUD_AT
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "80"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_reading_kept_after_websocket_update(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A pushed update with older cloud data keeps the reading; newer replaces it."""
    entry, discover = await _setup(hass, register)
    coordinator = entry.runtime_data.coordinator
    discover(ADDRESS)
    await hass.async_block_till_done()

    def push(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "deviceId": CAR_PRO_ID,
            "recordType": "DEVICE",
            "eventType": "MODIFY",
            "deviceRecord": record,
        }

    await coordinator._async_handle_message(
        push({"batteryRemaining": 45, "lastConnectedAt": CLOUD_AT})
    )
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "90"

    await coordinator._async_handle_message(
        push({"batteryRemaining": 80, "lastConnectedAt": int(time.time()) + 60})
    )
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "80"
    assert CAR_PRO_ID not in coordinator.car_readings


@pytest.mark.usefixtures("mock_pura", "car")
async def test_podless_intensity_dropped_with_reading(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A pushed update that outdates a reading without a pod drops its intensity.

    Pushed updates are merged into the cloud data, so the intensity the reading kept
    would otherwise stay.
    """
    no_pod = {"intensity": "off", "fragrance_code": None, "cartridge_id": None}
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__ | no_pod | {"runtime": None}
    )
    entry, discover = await _setup(hass, register)
    coordinator = entry.runtime_data.coordinator
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert _state(hass, "fan_intensity") == "off"

    await coordinator._async_handle_message(
        {
            "deviceId": CAR_PRO_ID,
            "recordType": "DEVICE",
            "eventType": "MODIFY",
            "deviceRecord": {"bay1": None, "lastConnectedAt": int(time.time()) + 60},
        }
    )
    await hass.async_block_till_done()
    assert CAR_PRO_ID not in coordinator.car_readings
    assert _state(hass, "fan_intensity") == "unavailable"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_podless_intensity_dropped_by_reading_with_pod(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A reading with a pod replaces the intensity a reading without one kept."""
    no_pod = {"intensity": "off", "fragrance_code": None, "cartridge_id": None}
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__ | no_pod | {"runtime": None}
    )
    entry, discover = await _setup(hass, register)
    coordinator = entry.runtime_data.coordinator
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert coordinator.data[CAR_PRO_ID]["fanIntensity"] == "off"

    read_car.return_value = STATUS
    await _later(hass)
    assert read_car.await_count == 2
    assert coordinator.data[CAR_PRO_ID]["bay1"]["code"] == "FZYC"
    assert _state(hass, "fan_intensity") == "high"
    assert "fanIntensity" not in coordinator.data[CAR_PRO_ID]


@pytest.mark.usefixtures("mock_pura", "car")
async def test_diagnostics_show_reading(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """Diagnostics show a car's Bluetooth reading, with its MAC partially redacted."""
    car, home = "**REDACTED**AA04", "**REDACTED**AA02"  # CAR_PRO_ID, HOME_V5_ID
    entry, discover = await _setup(hass, register)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "bluetooth" not in diagnostics[car]

    before = int(time.time())
    discover(ADDRESS)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    reading = diagnostics[car]["bluetooth"]
    assert reading["readAt"] >= before
    assert reading["mac"] == car
    assert reading["battery_level"] == 90
    assert reading["runtime"] == 192120
    assert diagnostics[car]["bay1"]["activeAt"] == reading["readAt"]
    assert "bluetooth" not in diagnostics[home]
    # The coordinator's data is left as is
    assert "bluetooth" not in entry.runtime_data.coordinator.data[CAR_PRO_ID]


def _saved(hass_storage: dict[str, Any], entry: MockConfigEntry) -> dict[str, Any]:
    return hass_storage[f"pura.{entry.entry_id}.car_readings"]["data"]


@pytest.mark.usefixtures("car")
async def test_reading_kept_after_reload(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_pura: MagicMock,
    register: MagicMock,
    read_car: AsyncMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """A reading is saved, and still shown after a reload until the cloud is newer."""
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    saved = _saved(hass_storage, entry)[CAR_PRO_ID]
    assert saved["battery_level"] == 90
    assert saved["mac"] == "AAAAAAAAAA04"
    assert _state(hass, "battery") == "90"
    assert _state(hass, "fan_intensity") == "high"

    # The cloud catches up, and the saved reading is dropped
    devices[CAR_PRO_ID]["lastConnectedAt"] = int(time.time()) + 60
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "45"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _saved(hass_storage, entry) == {}
    assert _state(hass, "battery") == "45"


@pytest.mark.usefixtures("car")
async def test_reading_saved_on_reload_after_failed_write(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_pura: MagicMock,
    register: MagicMock,
    read_car: AsyncMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """A delayed save that fails after building its data is retried on reload."""
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    write = Store._async_write_data
    key = f"pura.{entry.entry_id}.car_readings"

    async def fail_once(store: Store, data: dict[str, Any]) -> None:
        # Other stores, like the registries, may write meanwhile
        if store.key == key and not failed:
            # Like a real failure, after the delayed save built its data
            failed.append(data.pop("data_func")())
            raise WriteError("disk full")
        await write(store, data)

    failed: list[dict[str, Any]] = []
    with patch.object(Store, "_async_write_data", fail_once):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
        await hass.async_block_till_done()
        assert CAR_PRO_ID in failed[0]
        assert key not in hass_storage

        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert CAR_PRO_ID in _saved(hass_storage, entry)
    assert _state(hass, "battery") == "90"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_saved_reading_loaded(
    hass: HomeAssistant, hass_storage: dict[str, Any], register: MagicMock
) -> None:
    """A reading saved before a restart is shown; an unreadable one is ignored."""
    entry = MockConfigEntry(
        domain="pura", unique_id="pura", data={"username": "user@example.com"}
    )
    hass_storage[f"pura.{entry.entry_id}.car_readings"] = {
        "version": 1,
        "key": f"pura.{entry.entry_id}.car_readings",
        "data": {
            CAR_PRO_ID: {"read_at": time.time() - 60, **STATUS.__dict__},
            "aa:aa:aa:aa:aa:99": {"read_at": time.time(), "battery": 1},
        },
    }
    entry.add_to_hass(hass)
    hass.config.components.add("bluetooth")
    with patch("custom_components.pura.PLATFORMS", [Platform.SENSOR]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _state(hass, "battery") == "90"
    assert list(entry.runtime_data.coordinator.car_readings) == [CAR_PRO_ID]


@pytest.mark.usefixtures("mock_pura", "car")
async def test_readings_saved_before_unload_returns(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    register: MagicMock,
    read_car: AsyncMock,
) -> None:
    """The unload itself saves the readings, and nothing is written after it."""
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator

    assert await async_unload_entry(hass, entry)
    assert CAR_PRO_ID in _saved(hass_storage, entry)

    # A pushed update arriving before the websocket stops drops the reading,
    # but doesn't write again
    await coordinator._async_handle_message(
        {
            "deviceId": CAR_PRO_ID,
            "recordType": "DEVICE",
            "eventType": "MODIFY",
            "deviceRecord": {"lastConnectedAt": int(time.time()) + 60},
        }
    )
    assert CAR_PRO_ID not in coordinator.car_readings
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
    await hass.async_block_till_done()
    assert CAR_PRO_ID in _saved(hass_storage, entry)


@pytest.mark.usefixtures("car")
async def test_reading_during_unload_write_saved(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    mock_pura: MagicMock,
    register: MagicMock,
    read_car: AsyncMock,
    devices: dict[str, dict[str, Any]],
) -> None:
    """A reading that arrives while the unload is writing is saved too."""
    mock_pura.get_devices.side_effect = lambda: copy.deepcopy(devices)
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator

    write = Store._async_write_data
    key = f"pura.{entry.entry_id}.car_readings"
    writing, release = asyncio.Event(), asyncio.Event()

    async def slow_write(store: Store, data: dict[str, Any]) -> None:
        if store.key == key and not writing.is_set():
            writing.set()
            await release.wait()
        await write(store, data)

    with patch.object(Store, "_async_write_data", slow_write):
        unload = hass.async_create_task(
            hass.config_entries.async_unload(entry.entry_id)
        )
        await writing.wait()
        newer = PuraCarStatus(**STATUS.__dict__ | {"battery_level": 70})
        coordinator.async_set_car_status(CAR_PRO_ID, newer, time.time())
        release.set()
        assert await unload
    assert _saved(hass_storage, entry)[CAR_PRO_ID]["battery_level"] == 70

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "70"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_saved_readings_removed_with_entry(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    register: MagicMock,
    read_car: AsyncMock,
) -> None:
    """Removing the config entry deletes its saved readings."""
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    assert CAR_PRO_ID in _saved(hass_storage, entry)

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert f"pura.{entry.entry_id}.car_readings" not in hass_storage


async def _later(hass: HomeAssistant) -> None:
    """Move past READ_INTERVAL."""
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=READ_INTERVAL))
    await hass.async_block_till_done()


@pytest.mark.usefixtures("mock_pura", "car")
async def test_read_again_while_in_range(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock, present: MagicMock
) -> None:
    """A car still in range is read every READ_INTERVAL, without new advertisements."""
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    # Advertisements before the next read are ignored
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert read_car.await_count == 1

    read_car.return_value = PuraCarStatus(**STATUS.__dict__ | {"battery_level": 80})
    await _later(hass)
    assert read_car.await_count == 2
    assert _state(hass, "battery") == "80"
    present.assert_called_with(hass, ADDRESS, connectable=True)

    await _later(hass)
    assert read_car.await_count == 3


@pytest.mark.usefixtures("mock_pura", "car")
async def test_not_read_again_out_of_range(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock, present: MagicMock
) -> None:
    """A car that left isn't read again until it's seen again."""
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    present.return_value = False
    await _later(hass)
    await _later(hass)
    assert read_car.await_count == 1

    present.return_value = True
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert read_car.await_count == 2


@pytest.mark.usefixtures("mock_pura", "car")
async def test_failed_read(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A car that can't be read keeps its cloud data, and is retried later."""
    read_car.side_effect = PuraBluetoothError("No reply to command 1")
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert read_car.await_count == 1
    assert _state(hass, "battery") == "45"

    read_car.side_effect = None
    await _later(hass)
    assert _state(hass, "battery") == "90"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_logs_partially_redact_car(
    hass: HomeAssistant,
    register: MagicMock,
    read_car: AsyncMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Logs show a car's ID and MAC as diagnostics do, keeping the last 4 digits."""
    caplog.set_level(logging.DEBUG, logger="custom_components.pura")
    # pypura's connection errors quote the car's address
    read_car.side_effect = PuraBluetoothError(f"Couldn't connect to {ADDRESS}")
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    read_car.side_effect = None
    await _later(hass)

    assert (
        "Couldn't read **REDACTED**AA04 over Bluetooth: "
        "Couldn't connect to **REDACTED**AA04"
    ) in caplog.text
    assert "Read **REDACTED**AA04 over Bluetooth" in caplog.text
    assert "mac='**REDACTED**AA04'" in caplog.text
    for full in (CAR_PRO_ID, STATUS.mac):
        assert full.upper() not in caplog.text.upper()


@pytest.mark.usefixtures("mock_pura", "car")
async def test_read_in_progress(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """Advertisements while a car is being read don't start another read."""
    release = asyncio.Event()

    async def slow_read(_: Any) -> PuraCarStatus:
        await release.wait()
        return STATUS

    read_car.side_effect = slow_read
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await asyncio.sleep(0)
    discover(ADDRESS)
    release.set()
    await hass.async_block_till_done()
    assert read_car.await_count == 1
    assert _state(hass, "battery") == "90"


@pytest.mark.parametrize(
    "address",
    [
        "AA:AA:AA:AA:AA:99",  # not one of the account's devices
        "AA:AA:AA:AA:AA:02",  # HOME_V5_ID, which isn't a car
    ],
)
@pytest.mark.usefixtures("mock_pura", "car")
async def test_other_devices_ignored(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock, address: str
) -> None:
    """Only the account's cars are read."""
    _, discover = await _setup(hass, register)
    discover(address)
    await hass.async_block_till_done()
    read_car.assert_not_awaited()


@pytest.mark.usefixtures("mock_pura", "car")
async def test_car_no_longer_connectable(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A car that can't be connected to by the time it's read is skipped."""
    _, discover = await _setup(hass, register)
    with patch.object(
        car_bluetooth.bluetooth, "async_ble_device_from_address", return_value=None
    ):
        discover(ADDRESS)
        await hass.async_block_till_done()
    read_car.assert_not_awaited()


@pytest.mark.usefixtures("mock_pura", "car")
async def test_different_mac_applied(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A car is matched by its Bluetooth address, whatever MAC it reports.

    A v1 reports its chip's base MAC, which differs from its Bluetooth MAC.
    """
    read_car.return_value = PuraCarStatus(**STATUS.__dict__ | {"mac": "AAAAAAAAAA02"})
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "90"


@pytest.mark.usefixtures("mock_pura", "car")
async def test_without_bluetooth(hass: HomeAssistant, register: MagicMock) -> None:
    """Without Home Assistant's Bluetooth integration, nothing is registered."""
    await _setup(hass, register, bluetooth=False)
    register.assert_not_called()


@pytest.mark.usefixtures("mock_pura", "car")
async def test_unload_stops_listening(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """Unloading the entry removes the Bluetooth callback and the next read."""
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    await hass.config_entries.async_unload(entry.entry_id)
    register.return_value.assert_called_once()
    # Nor is the car read again
    await _later(hass)
    assert read_car.await_count == 1
