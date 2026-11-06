"""Tests for the Pura calendar platform."""

from __future__ import annotations

from datetime import timedelta
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


@pytest.mark.parametrize(
    ("times", "hours"),
    [
        ({"start": "0800", "end": "1000"}, 2),
        ({"start": "2200", "end": "0600"}, 8),
        ({"start": "2200", "end": "0000"}, 2),
        ({"start": "2200", "duration": 120}, 2),
    ],
    ids=["same_day_end", "overnight_end", "midnight_end", "overnight_duration"],
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
