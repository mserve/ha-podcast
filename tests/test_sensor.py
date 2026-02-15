"""Tests for podcast_hub sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigSubentry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.podcast_hub.const import CONF_ID, DOMAIN
from custom_components.podcast_hub.coordinator import PodcastHubCoordinator
from custom_components.podcast_hub.podcast_hub import Episode, PodcastFeed, PodcastHub
from custom_components.podcast_hub.sensor import (
    PodcastFeedSensor,
    async_setup_entry,
    async_setup_platform,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _build_hub(hass) -> PodcastHub:  # noqa: ANN001
    episode = Episode(
        guid="episode-1",
        title="Episode 1",
        published=datetime(2024, 1, 1, tzinfo=UTC),
        url="https://example.com/audio1.mp3",
    )
    feed = PodcastFeed(
        feed_id="yaml_feed",
        name="YAML Feed",
        url="https://example.com/feed.xml",
        max_episodes=10,
        episodes=[episode],
    )
    hub = PodcastHub(hass, [feed])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
        "yaml_feed_ids": {"yaml_feed"},
    }
    return hub


@pytest.mark.asyncio
async def test_async_setup_platform_no_data(hass) -> None:  # noqa: ANN001
    """Return early when hass data is missing."""
    async_add = AsyncMock()

    await async_setup_platform(hass, {}, async_add, None)

    async_add.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_platform_no_yaml_feed_ids(hass) -> None:  # noqa: ANN001
    """Return early when no YAML feeds exist."""
    hub = PodcastHub(hass, [])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
        "yaml_feed_ids": set(),
    }
    async_add = AsyncMock()

    await async_setup_platform(hass, {}, async_add, None)

    async_add.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_platform_skips_subentry_feeds(hass) -> None:  # noqa: ANN001
    """Do not create YAML entities that also exist as subentries."""
    _build_hub(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={CONF_ID: "yaml_feed"},
            subentry_type="feed",
            title="YAML Feed",
            unique_id="yaml_feed",
        ),
    )
    hass.data[DOMAIN]["config_entry"] = entry
    async_add = AsyncMock()

    await async_setup_platform(hass, {}, async_add, None)

    async_add.assert_called_once()
    args, _ = async_add.call_args
    assert args[0] == []


@pytest.mark.asyncio
async def test_async_setup_entry_no_data(hass) -> None:  # noqa: ANN001
    """Return early when hass data is missing."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    async_add = AsyncMock()

    await async_setup_entry(hass, entry, async_add)

    async_add.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_skips_missing_feed_id(hass) -> None:  # noqa: ANN001
    """Skip subentries without feed ids."""
    hub = PodcastHub(hass, [])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
    }
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={},
            subentry_type="feed",
            title="Missing Feed",
            unique_id="missing_feed",
        ),
    )
    async_add = AsyncMock()

    await async_setup_entry(hass, entry, async_add)

    async_add.assert_not_called()


def test_feed_sensor_missing_feed_attributes(hass) -> None:  # noqa: ANN001
    """Return empty attributes when feed is missing."""
    hub = PodcastHub(hass, [])
    coordinator = PodcastHubCoordinator(hass, hub, 15)
    sensor = PodcastFeedSensor(coordinator, "missing")

    assert sensor.extra_state_attributes == {}


def test_feed_sensor_includes_last_error(hass) -> None:  # noqa: ANN001
    """Expose last_error and format dates safely."""
    feed = PodcastFeed(
        feed_id="broken",
        name="Broken Feed",
        url="https://example.com/bad.xml",
        max_episodes=10,
    )
    feed.last_error = "boom"
    hub = PodcastHub(hass, [feed])
    coordinator = PodcastHubCoordinator(hass, hub, 15)
    sensor = PodcastFeedSensor(coordinator, "broken")

    attrs = sensor.extra_state_attributes
    assert attrs["last_error"] == "boom"
    assert attrs["last_update"] is None
