"""Tests for reading Pura Car diffusers over Bluetooth."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
import copy
from datetime import timedelta
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pypura import PuraBluetoothError
from pypura.car_ble import PuraCarStatus
import pytest

from custom_components.pura import car_bluetooth
from custom_components.pura.car_bluetooth import READ_INTERVAL
from custom_components.pura.diagnostics import async_get_config_entry_diagnostics
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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


@pytest.mark.usefixtures("mock_pura", "car")
async def test_new_fragrance(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A new fragrance shows its code until the cloud has its name."""
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__ | {"fragrance_code": "NDMH", "cartridge_id": "pod-2"}
    )
    entry, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "fragrance") == "Unknown (NDMH)"
    bay = entry.runtime_data.coordinator.devices[CAR_PRO_ID]["bay1"]
    assert bay["lowFragrance"] is False
    assert "fragrance" not in bay


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


@pytest.mark.usefixtures("mock_pura", "car")
async def test_pod_removed(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """Without a pod, the fragrance entities are unavailable."""
    read_car.return_value = PuraCarStatus(
        **STATUS.__dict__
        | {"fragrance_code": None, "cartridge_id": None, "runtime": None}
    )
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()

    assert _state(hass, "fragrance") == "unavailable"
    assert _state(hass, "battery") == "90"


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
async def test_diagnostics_show_reading(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """Diagnostics show a car's Bluetooth reading, with its MAC redacted."""
    entry, discover = await _setup(hass, register)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert "bluetooth" not in diagnostics[CAR_PRO_ID]

    before = int(time.time())
    discover(ADDRESS)
    await hass.async_block_till_done()
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    reading = diagnostics[CAR_PRO_ID]["bluetooth"]
    assert reading["readAt"] >= before
    assert reading["mac"] == "**REDACTED**"
    assert reading["battery_level"] == 90
    assert reading["runtime"] == 192120
    assert diagnostics[CAR_PRO_ID]["bay1"]["activeAt"] == reading["readAt"]
    assert "bluetooth" not in diagnostics[HOME_V5_ID]
    # The coordinator's data is left as is
    assert "bluetooth" not in entry.runtime_data.coordinator.data[CAR_PRO_ID]


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
async def test_different_mac_ignored(
    hass: HomeAssistant, register: MagicMock, read_car: AsyncMock
) -> None:
    """A reading from a car reporting another MAC isn't applied."""
    read_car.return_value = PuraCarStatus(**STATUS.__dict__ | {"mac": "BBBBBBBBBB04"})
    _, discover = await _setup(hass, register)
    discover(ADDRESS)
    await hass.async_block_till_done()
    assert _state(hass, "battery") == "45"


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
