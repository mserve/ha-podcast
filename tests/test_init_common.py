"""Tests for shared init helpers."""

from __future__ import annotations

import pytest

from custom_components.podcast_hub.const import (
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
)
from custom_components.podcast_hub.init_common import (
    coerce_max_episodes,
    coerce_update_interval,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_coerce_max_episodes_invalid_value() -> None:
    """Invalid values fall back to defaults."""
    assert coerce_max_episodes("bad") == DEFAULT_MAX_EPISODES


def test_coerce_update_interval_invalid_value() -> None:
    """Invalid values fall back to defaults."""
    assert coerce_update_interval("bad") == DEFAULT_UPDATE_INTERVAL
