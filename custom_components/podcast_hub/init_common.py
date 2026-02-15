"""Shared setup helpers for Podcast Hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import (
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_MAX_EPISODES,
)
from .coordinator import PodcastHubCoordinator
from .podcast_hub import PodcastHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def ensure_hub_and_coordinator(
    hass: HomeAssistant, update_interval: int
) -> tuple[PodcastHub, PodcastHubCoordinator]:
    """
    Ensure the Podcast Hub and its coordinator are set up in Home Assistant.

    :param hass: The Home Assistant instance.
    :type hass: HomeAssistant
    :param update_interval: The update interval in minutes.
    :type update_interval: int
    :return: The hub and coordinator.
    :rtype: tuple[PodcastHub, PodcastHubCoordinator]
    """
    data = hass.data.setdefault(DOMAIN, {})
    hub = data.get("hub")
    coordinator = data.get("coordinator")
    if hub and coordinator:
        return hub, coordinator
    hub = PodcastHub(hass, [])
    coordinator = PodcastHubCoordinator(hass, hub, update_interval)
    data["hub"] = hub
    data["coordinator"] = coordinator
    return hub, coordinator


def coerce_max_episodes(value: int | None) -> int:
    """
    Coerce a value to a valid max episodes count.

    :param value: The value to coerce.
    :type value: int | None
    :return: The coerced value.
    :rtype: int
    """
    try:
        coerced = int(value) if value is not None else DEFAULT_MAX_EPISODES
    except (TypeError, ValueError):
        coerced = DEFAULT_MAX_EPISODES
    return max(1, min(coerced, MAX_MAX_EPISODES))


def coerce_update_interval(value: int | None) -> int:
    """
    Coerce a value to a valid update interval in minutes.

    :param value: The value to coerce.
    :type value: int | None
    :return: The coerced value.
    :rtype: int
    """
    minutes = _safe_interval(value)
    return minutes if minutes is not None else DEFAULT_UPDATE_INTERVAL


def _safe_interval(value: int | None) -> int | None:
    """
    Safely coerce an interval value to a positive integer larger than zero or None.

    :param value: The value to coerce.
    :type value: int | None
    :return: The coerced value or None if invalid.
    :rtype: int | None
    """
    try:
        minutes = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return minutes if minutes and minutes > 0 else None
