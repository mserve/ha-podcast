"""Tests for the Podcast Hub media source."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Self
from unittest.mock import patch

import aiohttp
import pytest
from homeassistant.components.media_source import MediaSourceError, MediaSourceItem

from custom_components.podcast_hub.const import CONF_MEDIA_TYPE, DOMAIN
from custom_components.podcast_hub.coordinator import PodcastHubCoordinator
from custom_components.podcast_hub.media_source import (
    _find_episode,
    _parse_episode_id,
    async_get_media_source,
)
from custom_components.podcast_hub.podcast_hub import Episode, PodcastFeed, PodcastHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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


class _FailingResponse:
    async def __aenter__(self) -> Self:
        msg = "Simulated client error for testing"
        raise aiohttp.ClientError(msg)

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None


class _FailingSession:
    def get(self, url: str, *, allow_redirects: bool = True) -> _FailingResponse:  # noqa: ARG002
        return _FailingResponse()


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
    hub = PodcastHub(hass, [feed])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
    }
    return hub


def _setup_hub_with_feeds(hass, feeds: list[PodcastFeed]) -> PodcastHub:  # noqa: ANN001
    hub = PodcastHub(hass, feeds)
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
async def test_media_source_browse_root_sorted(hass) -> None:  # noqa: ANN001
    """Browse root returns feeds sorted alphabetically."""
    feeds = [
        PodcastFeed(
            feed_id="beta",
            name="beta feed",
            url="https://example.com/b.xml",
            max_episodes=10,
        ),
        PodcastFeed(
            feed_id="alpha",
            name="Alpha feed",
            url="https://example.com/a.xml",
            max_episodes=10,
        ),
    ]
    _setup_hub_with_feeds(hass, feeds)
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "", None)
    )
    children = result.children
    assert children
    titles = [child.title for child in children]
    assert titles == ["Alpha feed", "beta feed"]


@pytest.mark.asyncio
async def test_media_source_browse_feed(hass) -> None:  # noqa: ANN001
    """Browse a feed returns latest and all episodes entries."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "example", None)
    )
    children = result.children
    assert children
    titles = [child.title for child in children]
    assert titles == ["Latest", "All Episodes"]


@pytest.mark.asyncio
async def test_media_source_browse_feeds_root(hass) -> None:  # noqa: ANN001
    """Browse the feeds root node."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "feeds", None)
    )

    assert result.title == "Podcast Hub"
    assert result.children


@pytest.mark.asyncio
async def test_media_source_browse_latest_list(hass) -> None:  # noqa: ANN001
    """Latest list returns only the most recent episode."""
    episode = Episode(
        guid="episode-2",
        title="Episode 2",
        published=datetime(2024, 1, 2, tzinfo=UTC),
        url="https://example.com/audio2.mp3",
    )
    feed = PodcastFeed(
        feed_id="example",
        name="Example Feed",
        url="https://example.com/feed.xml",
        max_episodes=50,
        episodes=[
            episode,
            Episode(
                guid="episode-1",
                title="Episode 1",
                published=datetime(2024, 1, 1, tzinfo=UTC),
                url="https://example.com/audio1.mp3",
            ),
        ],
    )
    hub = PodcastHub(hass, [feed])
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": PodcastHubCoordinator(hass, hub, 15),
    }
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "example/latest", None)
    )

    assert result.title == "Latest"
    assert result.children
    assert len(result.children) == 1
    assert result.children[0]
    assert result.children[0].title == "Episode 2"
    assert result.children[0].identifier.endswith("latest")


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


@pytest.mark.asyncio
async def test_media_source_resolve_latest(hass) -> None:  # noqa: ANN001
    """Resolve the latest alias to the newest episode."""
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
            MediaSourceItem(hass, DOMAIN, "example/latest", None)
        )

    assert play.url == "https://cdn.example.com/audio1.mp3"
    assert play.mime_type == "audio/mpeg"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("podcast", "podcast"),
        ("track", "audio/mpeg"),
    ],
)
async def test_media_source_uses_configured_media_type(
    hass: HomeAssistant, configured: str, expected: str
) -> None:
    """Use configured media type when set on the config entry."""
    _setup_hub(hass)
    hass.data[DOMAIN]["config_entry"] = type(
        "_Entry",
        (),
        {"options": {CONF_MEDIA_TYPE: configured}, "data": {}},
    )()
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "example/all", None)
    )

    assert result.children
    assert result.children[0].media_content_type == expected


@pytest.mark.asyncio
async def test_media_source_falls_back_to_yaml_media_type(hass: HomeAssistant) -> None:
    """Fallback to YAML media type when no config entry is present."""
    _setup_hub(hass)
    hass.data[DOMAIN]["media_type"] = "podcast"
    media_source = await async_get_media_source(hass)

    result = await media_source.async_browse_media(
        MediaSourceItem(hass, DOMAIN, "example/all", None)
    )

    assert result.children
    assert result.children[0].media_content_type == "podcast"


@pytest.mark.asyncio
async def test_async_get_media_source_creates_hub_and_coordinator(
    hass: HomeAssistant,
) -> None:
    """Create hub/coordinator when missing and reuse them in the media source."""
    media_source = await async_get_media_source(hass)

    data = hass.data[DOMAIN]
    assert isinstance(data["hub"], PodcastHub)
    assert isinstance(data["coordinator"], PodcastHubCoordinator)
    assert media_source.hub is data["hub"]
    assert media_source.coordinator is data["coordinator"]


@pytest.mark.asyncio
async def test_async_get_media_source_reuses_existing(
    hass: HomeAssistant,
) -> None:
    """Reuse existing hub/coordinator from hass.data."""
    hub = _setup_hub(hass)
    coordinator = hass.data[DOMAIN]["coordinator"]

    media_source = await async_get_media_source(hass)

    assert media_source.hub is hub
    assert media_source.coordinator is coordinator


@pytest.mark.asyncio
async def test_media_source_browse_unknown_path(hass: HomeAssistant) -> None:
    """Unknown browse paths raise a media source error."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            MediaSourceItem(hass, DOMAIN, "feeds/unknown/extra", None)
        )


@pytest.mark.asyncio
async def test_media_source_browse_podcast_not_found(hass: HomeAssistant) -> None:
    """Unknown feed ids raise an error."""
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            MediaSourceItem(hass, DOMAIN, "missing", None)
        )


@pytest.mark.asyncio
async def test_media_source_browse_episode_list_not_found(hass: HomeAssistant) -> None:
    """Unknown feed ids raise errors for episode lists."""
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_browse_media(
            MediaSourceItem(hass, DOMAIN, "missing/latest", None)
        )


@pytest.mark.asyncio
async def test_media_source_resolve_missing_identifier(hass: HomeAssistant) -> None:
    """Missing identifiers raise media source errors."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, None, None)
        )


@pytest.mark.asyncio
async def test_media_source_resolve_invalid_identifier(hass: HomeAssistant) -> None:
    """Invalid identifiers raise media source errors."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "bad", None)
        )


@pytest.mark.asyncio
async def test_media_source_resolve_feed_not_found(hass: HomeAssistant) -> None:
    """Unknown feeds raise media source errors."""
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "missing/episode", None)
        )


@pytest.mark.asyncio
async def test_media_source_resolve_episode_not_found(hass: HomeAssistant) -> None:
    """Missing episodes raise media source errors."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    with pytest.raises(MediaSourceError):
        await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "example/unknown", None)
        )


@pytest.mark.asyncio
async def test_media_source_resolve_handles_client_errors(
    hass: HomeAssistant,
) -> None:
    """Client errors are wrapped in MediaSourceError."""
    _setup_hub(hass)
    media_source = await async_get_media_source(hass)

    with (
        patch(
            "custom_components.podcast_hub.media_source.async_get_clientsession",
            return_value=_FailingSession(),
        ),
        pytest.raises(MediaSourceError),
    ):
        await media_source.async_resolve_media(
            MediaSourceItem(hass, DOMAIN, "example/episode-1", None)
        )


def test_parse_episode_id_variants() -> None:
    """Support feeds root and invalid paths."""
    parsed = _parse_episode_id("feeds/myfeed/myguid")
    assert parsed.feed_id == "myfeed"
    assert parsed.item_id == "myguid"

    invalid = _parse_episode_id("feeds/a/b/c")
    assert invalid.feed_id is None
    assert invalid.item_id is None


def test_find_episode_returns_none(hass) -> None:  # noqa: ANN001
    """Return None when no episode matches."""
    hub = _setup_hub(hass)
    feed = hub.get_feed("example")

    assert feed is not None
    assert _find_episode(feed, "missing") is None


@pytest.mark.asyncio
async def test_failing_response_exit_is_noop() -> None:
    """Cover failing response exit path."""
    response = _FailingResponse()

    assert await response.__aexit__(None, None, None) is None
