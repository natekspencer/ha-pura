"""Pura coordinator."""

from __future__ import annotations

import copy
from datetime import timedelta
import logging
import random
from typing import Any

from deepdiff import DeepDiff
from pypura import Pura
from pypura.ws_subscriber import WebSocketSubscriber

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    BACKOFF_MULTIPLIER,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_JITTER,
    MIN_MAX_BACKOFF,
)
from .helpers import deep_merge, get_device_id

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


class PuraDataUpdateCoordinator(JitterBackoffMixin, DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, client: Pura, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = client
        self.devices: dict[str, list[dict[str, Any]]] = {}

        self._init_jitter_backoff(config_entry)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._get_interval_with_jitter(),
        )

        self.subscriber = WebSocketSubscriber(
            session=async_get_clientsession(hass),
            token=client.get_tokens().get("id_token"),
        )
        self.subscriber.start(self._async_handle_message)

    def get_device(self, device_type: str | None, device_id: str) -> dict[str, Any]:
        """Get device by type and id."""
        for dev_type, devices in self.devices.items():
            if device_type is not None and device_type != dev_type:
                continue
            for device in devices:
                if device_id == get_device_id(device):
                    return {"deviceType": dev_type} | device

        raise LookupError(f"Device {device_id!r} not found")

    async def _async_handle_message(self, data: dict) -> None:
        """Handle a pushed data message."""
        event_type = data.get("eventType")
        record_type = data.get("recordType")
        search = (d for d in self.devices["wall"] if d["deviceId"] == data["deviceId"])
        device = next(search, None)
        handled = False
        if device:
            if event_type == "MODIFY" and record_type == "DEVICE":
                old_device = copy.deepcopy(device)
                deep_merge(device, data.get("deviceRecord"))
                diff = DeepDiff(
                    old_device,
                    device,
                    ignore_order=True,
                    report_repetition=True,
                    verbose_level=2,
                )
                _LOGGER.debug("Devices updated: %s", diff if diff else "no changes")
                handled = True
            elif record_type == "TIMER":
                if event_type == "REMOVE":
                    _LOGGER.debug("Removed timer from device")
                    device["timer"] = None
                    handled = True
                elif event_type in ("INSERT", "MODIFY"):
                    _LOGGER.debug("%s timer on device", event_type.capitalize())
                    device["timer"] = data.get("timerRecord")
                    handled = True

        if handled:
            self.async_set_updated_data(self.devices)
        else:
            _LOGGER.warning("Received unknown update: %s", data)

    async def _async_update_data(self) -> dict[str, list[dict[str, Any]]]:
        """Update data via library, refresh token if necessary."""
        try:
            if devices := await self.hass.async_add_executor_job(self.api.get_devices):
                diff = DeepDiff(
                    self.devices,
                    devices,
                    ignore_order=True,
                    report_repetition=True,
                    verbose_level=2,
                )
                _LOGGER.debug("Devices updated: %s", diff if diff else "no changes")
                self.devices = devices

            self._handle_success()

        except Exception as err:  # pylint: disable=broad-except
            self._handle_failure("Pura API update")
            raise UpdateFailed(err) from err
        return self.devices


class PuraCarFirmwareDataUpdateCoordinator(JitterBackoffMixin, DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self, hass: HomeAssistant, client: Pura, config_entry: ConfigEntry
    ) -> None:
        """Initialize."""
        self.api = client

        self._init_jitter_backoff(config_entry)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self._get_interval_with_jitter(),
        )

    async def _async_update_data(self) -> dict[str, str]:
        """Update data via library, refresh token if necessary."""
        try:
            details: str = await self.hass.async_add_executor_job(
                self.api.get_latest_firmware_details, "car", "v1"
            )
            result = {
                (part := line.split("=", 1))[0].lower(): part[1]
                for line in details.split("\n")
            }

            self._handle_success()

            return result
        except Exception as err:  # pylint: disable=broad-except
            self._handle_failure("Pura car firmware API update")
            raise UpdateFailed(err) from err
