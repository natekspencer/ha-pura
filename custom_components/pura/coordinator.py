"""Pura coordinator."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import timedelta
from functools import partial
import logging
import random
from typing import Any, Literal, NamedTuple

from pypura import Pura, PuraApiException, PuraAuthenticationError
from pypura.car_ble import PuraCarStatus
from pypura.utils import dig, merge_websocket_update
from pypura.ws_subscriber import WebSocketSubscriber

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    BACKOFF_MULTIPLIER,
    BAYS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_JITTER,
    MIN_MAX_BACKOFF,
    UNKNOWN_FRAGRANCE_CODE,
)

_LOGGER = logging.getLogger(__name__)

type FragranceFormat = Literal["puck", "vial"]

CAR_READINGS_VERSION = 1
CAR_READINGS_SAVE_DELAY = 10


def car_readings_store(hass: HomeAssistant, entry_id: str) -> Store[dict[str, Any]]:
    """Return the store that keeps a config entry's car readings across restarts."""
    return Store(hass, CAR_READINGS_VERSION, f"{DOMAIN}.{entry_id}.car_readings")


def apply_car_status(
    device: dict[str, Any], status: PuraCarStatus, read_at: float
) -> bool:
    """Layer a car's Bluetooth reading over its cloud data.

    The car only syncs with the cloud through the Pura app, so a reading is usually
    newer. Returns `False` if the cloud has caught up since, changing nothing but
    dropping the intensity an earlier reading kept for a car without a pod.
    """
    # Only a reading without a pod sets this (the cloud never does), and pushed cloud
    # updates are merged into the device, so it would outlive the reading
    device.pop("fanIntensity", None)
    cloud_at = max(
        device.get("lastConnectedAt") or 0, dig(device, "bay1.activeAt") or 0
    )
    if cloud_at >= read_at:
        return False

    if status.battery_level is not None:  # a Car v1 has no battery
        device["batteryRemaining"] = status.battery_level
    device["fwVersion"] = status.firmware
    if status.unknown_pod:
        # The car can't tell which pod it has, so neither can the cloud or an
        # earlier reading. Show it as the app does, without a runtime.
        device["bay1"] = {
            "code": UNKNOWN_FRAGRANCE_CODE,
            "fanIntensity": status.intensity,
            "lowFragrance": False,
            "wearingTime": None,
            "activeAt": int(read_at),
        }
        return True
    if status.fragrance_code is None:
        device["bay1"] = None
        # Without a pod there's no bay to hold it, but the car still has an intensity
        device["fanIntensity"] = status.intensity
        return True

    bay = device["bay1"] = dict(device.get("bay1") or {})
    if bay.get("code") != status.fragrance_code:
        # A new fragrance, whose name and details only the cloud has
        bay.pop("fragrance", None)
        bay["lowFragrance"] = False
    elif bay.get("refillId") not in (None, status.cartridge_id):
        bay["lowFragrance"] = False  # a new pod of the same fragrance
    bay |= {
        "code": status.fragrance_code,
        "refillId": status.cartridge_id,
        "wearingTime": status.runtime,
        "fanIntensity": status.intensity,
        # The car only answers while it's on
        "activeAt": int(read_at),
    }
    return True


class JitterBackoffMixin:
    """Mixin to add jitter and exponential backoff to coordinators."""

    _base_interval: float
    _consecutive_failures: int
    update_interval: timedelta

    def _init_jitter_backoff(self, config_entry: ConfigEntry) -> None:
        """Initialize jitter and backoff settings from config entry."""
        self._base_interval = config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        self._consecutive_failures = 0

    def _get_interval_with_jitter(self) -> timedelta:
        """Calculate the update interval with jitter (50% of interval, capped at 30s)."""
        interval = self._base_interval
        # Calculate jitter as 50% of base interval, capped at MAX_JITTER
        jitter_max = min(self._base_interval * 0.5, MAX_JITTER)
        jitter = random.uniform(0, jitter_max)
        interval += jitter
        _LOGGER.debug(
            "Next update in %.1fs (base: %ds, jitter: %.1fs)",
            interval,
            self._base_interval,
            jitter,
        )
        return timedelta(seconds=interval)

    def _handle_success(self) -> None:
        """Handle successful API call - reset backoff and apply jitter to next interval."""
        if self._consecutive_failures > 0:
            _LOGGER.debug("API call succeeded, resetting backoff")
            self._consecutive_failures = 0
        self.update_interval = self._get_interval_with_jitter()

    def _handle_failure(self, context: str) -> None:
        """Handle failed API call - apply exponential backoff."""
        self._consecutive_failures += 1
        max_backoff = max(self._base_interval * BACKOFF_MULTIPLIER, MIN_MAX_BACKOFF)
        backoff = min(2**self._consecutive_failures, max_backoff)
        new_interval = self._base_interval + backoff
        self.update_interval = timedelta(seconds=new_interval)
        if self._consecutive_failures < 2:
            log_method = _LOGGER.debug
        elif self._consecutive_failures < 5:
            log_method = _LOGGER.warning
        else:
            log_method = _LOGGER.exception
        log_method(
            "%s failed (attempt %d), next update in %ds",
            context,
            self._consecutive_failures,
            new_interval,
        )


class PuraDataUpdateCoordinator(
    JitterBackoffMixin, DataUpdateCoordinator[dict[str, dict[str, Any]]]
):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, client: Pura, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = client
        self.devices: dict[str, dict[str, Any]] = {}
        # Bluetooth readings of cars, with when each was read
        self._car_readings: dict[str, tuple[float, PuraCarStatus]] = {}
        self._car_readings_store = car_readings_store(hass, config_entry.entry_id)
        # Whether the readings changed since they were loaded. A delayed save can
        # still be writing, or have failed, so this stays set until the unload
        # writes them for certain.
        self._car_readings_changed = False
        # Set once the unload starts saving them, after which only it writes
        self._car_readings_closing = False
        # Fragrances looked up by format and code, None if there's no such code
        self._fragrances: dict[tuple[FragranceFormat, str], dict[str, Any] | None] = {}
        self._fragrance_lookups: set[tuple[FragranceFormat, str]] = set()

        self._init_jitter_backoff(config_entry)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN.capitalize()} device",
            update_interval=self._get_interval_with_jitter(),
        )

        self.subscriber = WebSocketSubscriber(
            session=async_get_clientsession(hass),
            token=client.get_tokens().get("id_token"),
        )

        self.previous_devices: set[str] = set()

        # Initialize previous_devices from the device registry so that
        # stale devices can be detected on the first update after restart.
        device_registry = dr.async_get(hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, config_entry.entry_id
        ):
            for domain, identifier in device.identifiers:
                if domain == DOMAIN:
                    self.previous_devices.add(identifier)

    @property
    def current_devices_with_type(self) -> set[tuple[str, str]]:
        """Return the current devices with type."""
        return {
            (device_id, device.get("modelType", ""))
            for device_id, device in self.data.items()
        }

    def get_device(self, device_type: str | None, device_id: str) -> dict[str, Any]:
        """Get device by type and id."""
        device = self.devices.get(device_id)
        if device and (device_type is None or device.get("modelType") == device_type):
            return device

        raise LookupError(f"Device {device_id!r} not found")

    @property
    def car_readings(self) -> dict[str, tuple[float, PuraCarStatus]]:
        """Return the Bluetooth readings shown over the cloud data, with when each was read."""
        return self._car_readings

    async def async_load_car_readings(self) -> None:
        """Load the readings saved before a restart, so the cars don't show older cloud data."""
        stored = await self._car_readings_store.async_load() or {}
        for device_id, reading in stored.items():
            try:
                fields = dict(reading)
                read_at = float(fields.pop("read_at"))
                self._car_readings[device_id] = (read_at, PuraCarStatus(**fields))
            except (AttributeError, KeyError, TypeError, ValueError):
                _LOGGER.debug("Ignoring a saved reading of %s: %s", device_id, reading)

    def _car_readings_data(self) -> dict[str, Any]:
        return {
            device_id: {"read_at": read_at, **asdict(status)}
            for device_id, (read_at, status) in self._car_readings.items()
        }

    @callback
    def _async_save_car_readings(self) -> None:
        self._car_readings_changed = True
        if self._car_readings_closing:
            return  # the unload's save picks the change up
        self._car_readings_store.async_delay_save(
            self._car_readings_data, CAR_READINGS_SAVE_DELAY
        )

    async def async_flush_car_readings(self) -> None:
        """Save the readings now if they changed, as before a reload or removal.

        The save waits for any write still in progress, then writes the latest
        readings and cancels the pending one. A reading that arrives during the
        write is saved too. Nothing is written after it, so the file can be
        removed safely.
        """
        self._car_readings_closing = True
        while self._car_readings_changed:
            self._car_readings_changed = False
            await self._car_readings_store.async_save(self._car_readings_data())

    @callback
    def async_set_car_status(
        self, device_id: str, status: PuraCarStatus, read_at: float
    ) -> None:
        """Show a car's Bluetooth reading until the cloud has newer data."""
        self._car_readings[device_id] = (read_at, status)
        self._apply_car_readings()
        self._async_save_car_readings()
        self.async_update_listeners()

    def _apply_car_readings(self) -> None:
        """Layer the Bluetooth readings over the cloud data, dropping outdated ones."""
        dropped = False
        for device_id, (read_at, status) in list(self._car_readings.items()):
            device = self.devices.get(device_id)
            if not device or device.get("modelType") != "car":
                del self._car_readings[device_id]
                dropped = True
            elif not apply_car_status(device, status, read_at):
                _LOGGER.debug("The cloud has newer data for %s", device_id)
                del self._car_readings[device_id]
                dropped = True
        if dropped:
            self._async_save_car_readings()
        self._fill_fragrances()

    def _fill_fragrances(self) -> None:
        """Add the details of fragrances known only by their code.

        A car's Bluetooth reading only has the pod's code, and the cloud can lack
        a fragrance's details too. Codes not looked up yet are looked up in the
        background, as the app does. That includes UNKNOWN_FRAGRANCE_CODE, which
        the API has as "Unknown fragrance".
        """
        for device in self.devices.values():
            fragrance_format: FragranceFormat = (
                "puck" if device.get("modelType") == "car" else "vial"
            )
            for number in BAYS:
                bay = device.get(f"bay{number}")
                if (
                    not isinstance(bay, dict)
                    or bay.get("fragrance")
                    or not (code := bay.get("code"))
                ):
                    continue
                key = (fragrance_format, code)
                if key in self._fragrances:
                    if fragrance := self._fragrances[key]:
                        bay["fragrance"] = fragrance
                elif key not in self._fragrance_lookups and self.config_entry:
                    self._fragrance_lookups.add(key)
                    self.config_entry.async_create_background_task(
                        self.hass,
                        self._async_look_up_fragrance(key),
                        f"{DOMAIN} look up fragrance {code}",
                    )

    async def _async_look_up_fragrance(self, key: tuple[FragranceFormat, str]) -> None:
        """Look up a fragrance by its code, then show it on the bays that have it."""
        fragrance_format, code = key
        try:
            fragrance = await self.hass.async_add_executor_job(
                partial(self.api.get_fragrance, code, fragrance_format=fragrance_format)
            )
        except PuraApiException as err:
            # Not remembered, so the next update tries again
            _LOGGER.debug("Couldn't look up fragrance %s: %s", code, err)
            return
        finally:
            self._fragrance_lookups.discard(key)
        self._fragrances[key] = fragrance
        if fragrance:
            self._fill_fragrances()
            self.async_update_listeners()
        else:
            _LOGGER.debug("No %s fragrance has the code %s", fragrance_format, code)

    def _check_stale_devices(self) -> None:
        """Check for stale devices."""
        current_devices = set(self.devices)
        if stale_devices := self.previous_devices - current_devices:
            device_registry = dr.async_get(self.hass)
            for device_id in stale_devices:
                if device := device_registry.async_get_device_by_identifier(
                    (DOMAIN, device_id), self.config_entry.entry_id
                ):
                    device_registry.async_remove_device(device.id)
        self.previous_devices = current_devices

    async def _async_handle_message(self, update: dict[str, Any]) -> None:
        """Handle a pushed data message."""
        current_devices = set(self.devices)
        if merge_websocket_update(self.devices, update):
            if set(self.devices) - current_devices:
                # schedule a refresh since we have a new device
                await self.async_request_refresh()
            else:
                # The update may carry older cloud values for a car read since
                self._apply_car_readings()
                self._check_stale_devices()
                self.async_set_updated_data(self.devices)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via library, refresh token if necessary."""
        try:
            devices = await self.hass.async_add_executor_job(self.api.get_devices)
            _LOGGER.debug("Devices updated")
            self.devices = devices
            self._apply_car_readings()
            self._check_stale_devices()
            self._handle_success()

        except PuraAuthenticationError as err:
            raise ConfigEntryAuthFailed from err

        except Exception as err:  # pylint: disable=broad-except
            self._handle_failure("Pura API update")
            raise UpdateFailed(err) from err

        if not (subscriber := self.subscriber).is_running:
            try:
                await subscriber.stop()
                subscriber.token = self.api.get_tokens().get("id_token")
                subscriber.start(self._async_handle_message)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.warning("Could not start websocket subscriber", exc_info=True)

        return self.devices


class DeviceVersion(NamedTuple):
    """Identifies a device's known model/type and version."""

    id: str
    model: int
    version: str


class PuraFirmwareDataUpdateCoordinator(
    JitterBackoffMixin, DataUpdateCoordinator[dict[str, dict[str, Any]]]
):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_coordinator: PuraDataUpdateCoordinator,
    ) -> None:
        """Initialize."""
        self.api = device_coordinator.api
        self.device_coordinator = device_coordinator

        self._base_interval = timedelta(days=1).total_seconds()
        self._consecutive_failures = 0

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN.capitalize()} firmware",
            update_interval=self._get_interval_with_jitter(),
        )

        self._semaphore = asyncio.Semaphore(4)
        self._data_lock = asyncio.Lock()

        self._devices: set[DeviceVersion] = set()
        self._update_device_versions(False)
        config_entry.async_on_unload(
            self.device_coordinator.async_add_listener(self._update_device_versions)
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch latest firmware details for every known device."""
        return await self._async_fetch_devices(self._devices)

    async def _async_refresh_devices(self, devices: set[DeviceVersion]) -> None:
        """Fetch latest firmware details for a set of devices and set coordinator data."""
        data = await self._async_fetch_devices(devices)
        self.async_set_updated_data(data)

    async def _async_fetch_devices(
        self, devices: set[DeviceVersion]
    ) -> dict[str, dict[str, Any]]:
        """Fetch and merge latest firmware details for a set of devices."""
        async with self._data_lock:
            device_list = list(devices)
            results = await asyncio.gather(
                *(
                    self._async_fetch_one(device.id, device.model, device.version)
                    for device in device_list
                ),
                return_exceptions=True,
            )

            data = dict(self.data or {})
            for device, result in zip(device_list, results):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Firmware check failed for %s: %s", device.id, result
                    )
                    continue
                data[device.id] = result
            return data

    async def _async_fetch_one(
        self, device_id: str, device_type: int, device_version: str
    ) -> dict[str, Any]:
        """Fetch latest firmware details for a single device, bounded by the semaphore."""
        async with self._semaphore:
            return await self.hass.async_add_executor_job(
                self.api.get_latest_firmware_details,
                device_id,
                device_type,
                device_version,
            )

    def _update_device_versions(self, request_refresh: bool = True) -> None:
        """React to devices whose device version just became known or changed."""
        current_devices = {
            DeviceVersion(device_id, device.get("model"), device_version)
            for device_id, device in self.device_coordinator.data.items()
            if (device_version := device.get("deviceVer"))
        }
        if request_refresh and (new_devices := current_devices - self._devices):
            self.config_entry.async_create_task(
                self.hass, self._async_refresh_devices(new_devices)
            )
        self._devices = current_devices
