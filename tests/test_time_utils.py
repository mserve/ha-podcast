"""Tests for time utility helpers."""

from __future__ import annotations

from datetime import time as dt_time

import pytest

from custom_components.podcast_hub.time_utils import parse_refresh_times

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_parse_refresh_times_handles_time_and_invalid() -> None:
    """Keep time objects and skip invalid strings."""
    parsed = parse_refresh_times([dt_time(9, 0), "25:00"])

    assert parsed == [dt_time(9, 0)]
