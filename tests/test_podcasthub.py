"""Tests for the PodcastHub model."""

from __future__ import annotations

import time as time_module
from unittest.mock import AsyncMock, patch

import pytest
from feedparser import FeedParserDict

from custom_components.podcast_hub.podcast_hub import PodcastFeed, PodcastHub

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def _build_parsed_feed() -> FeedParserDict:
    feed = FeedParserDict(
        title="Example Podcast",
        image={"url": "https://example.com/feed.png"},
    )
    entry = FeedParserDict(
        id="episode-1",
        title="Episode 1",
        link="https://example.com/episode1",
        links=[FeedParserDict(rel="enclosure", href="https://example.com/audio1.mp3")],
        summary="Episode 1 summary",
        published_parsed=time_module.gmtime(0),
    )
    return FeedParserDict(feed=feed, entries=[entry])


def test_hub_add_get_remove_feed(hass) -> None:  # noqa: ANN001
    """Add, fetch, and remove a feed from the hub."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    hub.add_feed(feed)
    assert hub.get_feed("example") is feed

    hub.remove_feed("example")
    assert hub.get_feed("example") is None


@pytest.mark.asyncio
async def test_fetch_feed_updates_metadata(hass) -> None:  # noqa: ANN001
    """Fetch a feed and populate metadata and episodes."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    parsed = _build_parsed_feed()

    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.title == "Example Podcast"
    assert feed.image_url == "https://example.com/feed.png"
    assert feed.last_error is None
    assert feed.last_update is not None
    assert len(feed.episodes) == 1
    assert feed.episodes[0].guid == "episode-1"


@pytest.mark.asyncio
async def test_fetch_feed_handles_errors(hass) -> None:  # noqa: ANN001
    """Ensure fetch errors are captured on the feed without raising."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    with patch.object(hub, "_async_fetch", new=AsyncMock(side_effect=TimeoutError)):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.last_error is not None
    assert feed.last_update is not None
