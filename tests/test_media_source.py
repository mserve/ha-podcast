"""Tests for the Podcast Hub media source."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self
from unittest.mock import patch

import pytest
from homeassistant.components.media_source import MediaSourceItem

from custom_components.podcast_hub.const import DOMAIN
from custom_components.podcast_hub.coordinator import PodcastHubCoordinator
from custom_components.podcast_hub.media_source import async_get_media_source
from custom_components.podcast_hub.podcast_hub import Episode, PodcastFeed, PodcastHub

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


class _DummyResponse:
    def __init__(self, url: str, content_type: str) -> None:
        self.url = url
        self.headers = {"Content-Type": content_type}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def raise_for_status(self) -> None:
        return None


class _DummySession:
    def __init__(self, url: str, content_type: str) -> None:
        self._url = url
        self._content_type = content_type

    def get(self, url: str, *, allow_redirects: bool = True) -> _DummyResponse:  # noqa: ARG002
        return _DummyResponse(self._url, self._content_type)


def _setup_hub(hass) -> PodcastHub:  # noqa: ANN001
    episode = Episode(
        guid="episode-1",
        title="Episode 1",
        published=datetime(2024, 1, 1, tzinfo=UTC),
        url="https://example.com/audio1.mp3",
    )
    feed = PodcastFeed(
        feed_id="example",
        name="Example Feed",
        url="https://example.com/feed.xml",
        max_episodes=50,
        episodes=[episode],
    )
    hub = PodcastHub([feed])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
    }
    return hub


@pytest.mark.asyncio
async def test_media_source_browse_root(hass) -> None:  # noqa: ANN001
    """Browse root returns feeds directly."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "", None)
    )

    assert result.title == "Podcast Hub"
    assert result.children
    assert result.children[0].title == "Example Feed"


@pytest.mark.asyncio
async def test_media_source_browse_feed(hass) -> None:  # noqa: ANN001
    """Browse a feed returns latest and all episodes entries."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "example", None)
    )

    titles = [child.title for child in result.children]
    assert titles == ["Latest", "All Episodes"]


@pytest.mark.asyncio
async def test_media_source_resolve_media(hass) -> None:  # noqa: ANN001
    """Resolve a media item returns the final URL and mime type."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    session = _DummySession(
        url="https://cdn.example.com/audio1.mp3",
        content_type="audio/mpeg",
    )

    with patch(
        "custom_components.podcast_hub.media_source.async_get_clientsession",
        return_value=session,
    ):
        play = await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "example/episode-1", None)
        )

    assert play.url == "https://cdn.example.com/audio1.mp3"
    assert play.mime_type == "audio/mpeg"
