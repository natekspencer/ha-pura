"""Pura constants."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pura"

CONF_ID_TOKEN: Final = "id_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_UPDATE_INTERVAL: Final = "update_interval"

MIN_UPDATE_INTERVAL: Final = 30
MAX_UPDATE_INTERVAL: Final = 300
DEFAULT_UPDATE_INTERVAL: Final = 30
MAX_JITTER: Final = 30  # Maximum jitter in seconds (50% of interval, capped at 30s)
BACKOFF_MULTIPLIER: Final = 2  # Max backoff = user interval * this
MIN_MAX_BACKOFF: Final = 300  # 5 minute floor for max backoff

ATTR_SLOT: Final = "slot"

BAYS: Final = (1, 2, 3, 4)
ATTR_INTENSITY: Final = "intensity"
ATTR_DURATION: Final = "duration"
