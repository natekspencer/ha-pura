"""Pura coordinator."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import random
from typing import Any

from pypura import Pura, PuraAuthenticationError
from pypura.utils import merge_websocket_update
from pypura.ws_subscriber import WebSocketSubscriber

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    BACKOFF_MULTIPLIER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_JITTER,
    MIN_MAX_BACKOFF,
)

_LOGGER = logging.getLogger(__name__)


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
        if merge_websocket_update(self.devices, update):
            self._check_stale_devices()
            self.async_set_updated_data(self.devices)

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via library, refresh token if necessary."""
        try:
            devices = await self.hass.async_add_executor_job(self.api.get_devices)
            _LOGGER.debug("Devices updated")
            self.devices = devices
            self._check_stale_devices()
            self._handle_success()

        except PuraAuthenticationError as err:
            raise ConfigEntryAuthFailed from err

        except Exception as err:  # pylint: disable=broad-except
            self._handle_failure("Pura API update")
            raise UpdateFailed(err) from err

        if not self.subscriber.is_running:
            try:
                self.subscriber.token = self.api.get_tokens().get("id_token")
                self.subscriber.start(self._async_handle_message)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.warning("Could not start websocket subscriber", exc_info=True)

        return self.devices


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

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Update data via library, refresh token if necessary."""
        device_ids = list(self.device_coordinator.data)
        results = await asyncio.gather(
            *(
                self._async_fetch_one(
                    device_id, device.get("model"), device.get("deviceVer")
                )
                for device_id, device in self.device_coordinator.data.items()
            ),
            return_exceptions=True,
        )

        data = self.data or {}
        for device_id, result in zip(device_ids, results):
            if isinstance(result, Exception):
                _LOGGER.warning("Firmware check failed for %s: %s", device_id, result)
                continue
            data[device_id] = result
        return data

    async def _async_fetch_one(
        self, device_id: str, device_type: int, device_version: str
    ) -> dict[str, Any]:
        """Fetch firmware status for a single device, bounded by the semaphore."""
        async with self._semaphore:
            return await self.hass.async_add_executor_job(
                self.api.get_latest_firmware_details,
                device_id,
                device_type,
                device_version,
            )
