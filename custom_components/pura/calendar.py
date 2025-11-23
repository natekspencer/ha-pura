"""Support for Pura diffuser schedule."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from ical.calendar import Calendar
from ical.event import Event
from ical.types import Recur

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import PuraConfigEntry
from .coordinator import PuraDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCHEDULE = EntityDescription(key="schedule")
ONE_DAY = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant, entry: PuraConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Pura schedule calendar using config entry."""
    entities = [
        PuraCalendarEntity(
            coordinator=entry.runtime_data, description=SCHEDULE, entry=entry
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
        description: EntityDescription,
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
                summary=f"{schedule['name']} - {device['displayName']['name']}",
                start=_parse_datetime(now, schedule["start"], schedule["disableUntil"]),
                end=_parse_datetime(now, schedule["end"], schedule["disableUntil"]),
                description=f"Fragrance slot {schedule['bay']} ("
                + (
                    bay.get("fragrance", {}).get("name", "Unknown")
                    if (bay := device.get(f"bay{schedule['bay']}"))
                    else "Empty"
                )
                + f") with {schedule['intensity']} intensity",
                uid=schedule["id"],
                rrule=Recur.from_rrule(
                    f"FREQ=WEEKLY;BYDAY="
                    f"{','.join(day[:2].upper() for day in schedule['days'] if schedule['days'][day])};INTERVAL=1"
                ),
            )
            for device_type, devices in self.coordinator.devices.items()
            if device_type in ("wall", "plus", "mini")
            for device in devices
            for schedule in device.get("schedules", [])
            if schedule["disableUntil"] != -1
        )

        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self._handle_coordinator_update()
        await super().async_added_to_hass()


def _parse_datetime(
    now: datetime, time_str: str, disable_until: int | None = None
) -> datetime | None:
    """Parse datetime safely."""
    # FIX: Use now.date() instead of invalid combine(now, ...)
    base_time = _parse_time(time_str)
    _date = datetime.combine(now.date(), base_time, now.tzinfo)

    # If disabled until a future timestamp, move event to next day
    if disable_until and _date <= datetime.fromtimestamp(disable_until, now.tzinfo):
        _date += ONE_DAY

    return _date


def _parse_time(time_str: str) -> dt_util.dt.time | None:
    """Parse HHMM string into time."""
    return dt_util.parse_time(f"{time_str[:2]}:{time_str[2:]}")


def _get_calendar_event(event: Event) -> CalendarEvent:
    """Convert an iCal Event to a safe Home Assistant CalendarEvent."""
    start = dt_util.as_local(event.start)
    end = dt_util.as_local(event.end) if event.end else None

    # FIX 1: Missing end time → zero-duration event
    if end is None:
        end = start

    # FIX 2: Overnight or reversed event (00:00 < 22:00) → add one day
    if end < start:
        end = end + ONE_DAY

    return CalendarEvent(
        summary=event.summary,
        start=start,
        end=end,
        description=event.description,
        rrule=event.rrule.as_rrule_str() if event.rrule else None,
    )
