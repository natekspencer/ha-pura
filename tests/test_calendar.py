"""Tests for the Pura calendar platform."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import setup_integration

EVERY_DAY = dict.fromkeys(
    ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"),
    True,
)
# 03:00 in the device's timezone, and 23:00 the night before
AFTER_MIDNIGHT = datetime(2026, 6, 16, 7, tzinfo=UTC)
DISABLED_UNTIL = int((AFTER_MIDNIGHT - timedelta(hours=4)).timestamp())


@pytest.mark.parametrize(
    ("times", "hours"),
    [
        ({"start": "0800", "end": "1000"}, 2),
        ({"start": "2200", "end": "0600"}, 8),
        ({"start": "2200", "end": "0000"}, 2),
        ({"start": "0800", "end": "0800"}, 0),
        ({"start": "2200", "duration": 120}, 2),
    ],
    ids=[
        "same_day_end",
        "overnight_end",
        "midnight_end",
        "matching_end",
        "overnight_duration",
    ],
)
async def test_schedule_event_times(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_pura: MagicMock,
    luxe: dict[str, Any],
    times: dict[str, Any],
    hours: int,
) -> None:
    """Test a schedule's event ends the right time after it starts."""
    freezer.move_to("2026-06-15 12:00:00+00:00")
    luxe["schedules"] = [
        {"id": "schedule", "name": "Test", "bay": 1, "intensity": 5}
        | {"days": EVERY_DAY}
        | times
    ]
    await setup_integration(hass, [Platform.CALENDAR])
    entity_id = hass.states.async_entity_ids("calendar")[0]

    now = dt_util.now()
    response = await hass.services.async_call(
        "calendar",
        "get_events",
        {
            "start_date_time": now,
            "end_date_time": now + timedelta(days=3),
        },
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )

    events = response[entity_id]["events"]
    assert events
    for event in events:
        start = dt_util.parse_datetime(event["start"])
        end = dt_util.parse_datetime(event["end"])
        assert end - start == timedelta(hours=hours)


@pytest.mark.parametrize(
    ("schedule", "active"),
    [
        ({"start": "2200", "end": "0600"}, True),
        ({"start": "2200", "duration": 480}, True),
        ({"start": "2200", "end": "0200"}, False),
        ({"start": "2200", "end": "0600", "disableUntil": DISABLED_UNTIL}, False),
    ],
    ids=["end", "duration", "already_ended", "disabled"],
)
async def test_overnight_schedule_after_midnight(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    mock_pura: MagicMock,
    luxe: dict[str, Any],
    schedule: dict[str, Any],
    active: bool,
) -> None:
    """Test an overnight schedule stays active past midnight unless it's over."""
    freezer.move_to(AFTER_MIDNIGHT)
    luxe["schedules"] = [
        {"id": "schedule", "name": "Test", "bay": 1, "intensity": 5}
        | {"days": EVERY_DAY}
        | schedule
    ]
    await setup_integration(hass, [Platform.CALENDAR])
    entity_id = hass.states.async_entity_ids("calendar")[0]

    assert hass.states.get(entity_id).state == ("on" if active else "off")
