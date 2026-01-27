"""Time helpers for podcast_hub."""

from __future__ import annotations

from datetime import time as dt_time
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

if TYPE_CHECKING:
    from collections.abc import Iterable


def normalize_refresh_times(value: Iterable[str | dt_time] | None) -> list[str]:
    """Normalize refresh time entries to HH:MM strings."""
    if not value:
        return []
    normalized: list[str] = []
    for item in value:
        parsed = item if isinstance(item, dt_time) else cv.time(item)
        normalized.append(parsed.strftime("%H:%M"))
    return normalized


def parse_refresh_times(value: Iterable[str | dt_time] | None) -> list[dt_time]:
    """Parse refresh time strings into time objects."""
    if not value:
        return []
    parsed_times: list[dt_time] = []
    for item in value:
        if isinstance(item, dt_time):
            parsed_times.append(item)
            continue
        try:
            parsed_times.append(cv.time(item))
        except vol.Invalid:
            continue
    parsed_times.sort()
    return parsed_times
