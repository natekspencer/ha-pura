"""Support for Pura diffuser schedule."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import logging
from typing import Any
from zoneinfo import ZoneInfo

from ical.calendar import Calendar
from ical.event import Event
from ical.types import Recur
from pypura.utils import dig, get_device_name, get_fragrance_name, parse_intensity

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityDescription,
    CalendarEvent,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import PuraConfigEntry
from .coordinator import PuraDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCHEDULE = CalendarEntityDescription(key="schedule")

ONE_DAY = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura schedule calendar using config entry."""
    entities = [
        PuraCalendarEntity(
            coordinator=entry.runtime_data.coordinator,
            description=SCHEDULE,
            entry=entry,
        )
    ]
    async_add_entities(entities)


class PuraCalendarEntity(CoordinatorEntity[PuraDataUpdateCoordinator], CalendarEntity):
    """Pura calendar entity."""

    _calendar: Calendar | None = None

    _attr_has_entity_name = True
    _attr_name = "Pura"

    def __init__(
        self,
        coordinator: PuraDataUpdateCoordinator,
        description: CalendarEntityDescription,
        entry: PuraConfigEntry,
    ) -> None:
        """Construct a PuraEntity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}-{description.key}"

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self._calendar:
            return None

        now = dt_util.now()
        events = self._calendar.timeline_tz(now.tzinfo).active_after(now)
        if not (event := next(events, None)):
            return None
        return _get_calendar_event(event)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Get all events in a specific time frame."""
        if not self._calendar:
            return []

        events = self._calendar.timeline_tz(start_date.tzinfo).overlapping(
            start_date, end_date
        )
        return [_get_calendar_event(event) for event in events]

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        now = dt_util.now()
        self._calendar = Calendar()
        self._calendar.events.extend(
            Event(
                summary=f"{get_device_name(device)}: {schedule.get('name')}",
                description=_get_schedule_description(device, schedule),
                uid=schedule["id"],
                rrule=Recur.from_rrule(
                    f"FREQ=WEEKLY;BYDAY={','.join(day[:2].upper() for day in schedule['days'] if schedule['days'][day])};INTERVAL=1"
                ),
                **_parse_start_end(
                    now,
                    schedule.get("start"),
                    duration=schedule.get("duration"),
                    end=schedule.get("end"),
                    disable_until=schedule.get("disableUntil"),
                    tz=dig(device, "deviceLocation.timezone"),
                ),
            )
            for device in self.coordinator.devices.values()
            if device.get("modelType") in ("wall", "plus", "mini")
            for schedule in device.get("schedules", [])
            if schedule.get("disableUntil") != -1
        )

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self._handle_coordinator_update()
        await super().async_added_to_hass()


def _parse_start_end(
    now: datetime,
    start: str | int,
    *,
    duration: int | None = None,
    end: str | None = None,
    disable_until: int | None = None,
    tz: str | None = None,
) -> dict[str, Any]:
    """Parse a start and end datetime for a schedule."""
    tzinfo = ZoneInfo(tz) if tz else now.tzinfo
    now = now.astimezone(tzinfo)
    start_dt = _parse_datetime(now, start, disable_until=disable_until)
    end_dt = start_dt
    if duration:
        time_duration = timedelta(minutes=duration)
        end_dt = (start_dt.astimezone(dt_util.UTC) + time_duration).astimezone(tzinfo)
    elif end:
        end_dt = _parse_datetime(start_dt, end)
    return {"start": start_dt, "end": end_dt}


def _parse_datetime(
    now: datetime, time_value: str | int, *, disable_until: int | None = None
) -> datetime | None:
    """Parse datetime."""
    _date = dt_util.dt.datetime.combine(now, _parse_time(time_value), now.tzinfo)
    if disable_until and _date <= datetime.fromtimestamp(disable_until, now.tzinfo):
        _date += ONE_DAY
    return _date


def _parse_time(time_value: str | int) -> time | None:
    """Parse time."""
    if isinstance(time_value, int):
        time_value = f"{time_value:04d}"
    return dt_util.parse_time(f"{time_value[:2]}:{time_value[2:]}")


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Return a CalendarEvent from an iCal Event."""
    return CalendarEvent(
        summary=event.summary,
        start=dt_util.as_local(event.start),
        end=dt_util.as_local(event.end),
        description=event.description,
        rrule=event.rrule.as_rrule_str(),
    )


def _get_schedule_description(device: dict[str, Any], schedule: dict[str, Any]) -> str:
    """Get a pura schedule description for a calendar event."""
    if device.get("diffusionMode") == "oscillation-multi-bay":
        description = "Auto-alternate fragrances: ON\n"
    else:
        bay = schedule.get("bay")
        description = f"Fragrance: {get_fragrance_name(device, bay)} (slot {bay})\n"
    intensity = schedule.get("intensity")
    description += f"Intensity: {parse_intensity(intensity)} (level {intensity})"
    if nightlight := schedule.get("nightlight"):
        light_on = nightlight.get("active")
        description += f"\nLight: {'on' if light_on else 'off'}"
        if light_on:
            bri = nightlight.get("brightness", 0) * 10
            description += f" (brightness: {bri}%)"
    return description
