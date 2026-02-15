"""Tests for the PodcastHub model."""

from __future__ import annotations

import datetime
import time as time_module
from typing import TYPE_CHECKING, Self
from unittest.mock import AsyncMock, patch

import pytest
from feedparser import FeedParserDict

from custom_components.podcast_hub.podcast_hub import PodcastFeed, PodcastHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def _fetch_feed(
    hass: HomeAssistant,
    feed_overrides: dict | None = None,
    additional_entries: list[FeedParserDict] | None = None,
    *,
    use_default_entries: bool = True,
) -> PodcastFeed:
    """Fetch a test feed."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    parsed = _build_parsed_feed(
        feed_overrides=feed_overrides,
        additional_entries=additional_entries,
        use_default_entries=use_default_entries,
    )

    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    return feed


def _build_parsed_feed(
    additional_entries: list[FeedParserDict] | None = None,
    feed_overrides: dict | None = None,
    *,
    use_default_entries: bool = True,
) -> FeedParserDict:
    feed = FeedParserDict(
        title="Example Podcast",
        image={"url": "https://example.com/feed.png"},
    )
    if feed_overrides:
        feed.update(feed_overrides)
    entry = FeedParserDict(
        id="episode-1",
        title="Episode 1",
        link="https://example.com/episode1",
        links=[FeedParserDict(rel="enclosure", href="https://example.com/audio1.mp3")],
        summary="Episode 1 summary",
        published_parsed=time_module.gmtime(0),
    )
    another_entry = FeedParserDict(
        id="episode-2",
        title="Episode 2",
        link="https://example.com/episode2",
        links=[FeedParserDict(rel="enclosure", href="https://example.com/audio2.mp3")],
        summary="Episode 2 summary",
        published_parsed=time_module.gmtime(60),
    )
    entries = [entry, another_entry] if use_default_entries else []

    if additional_entries is not None:
        entries.extend(additional_entries)
    return FeedParserDict(feed=feed, entries=entries)


def test_hub_add_get_remove_feed(hass: HomeAssistant) -> None:
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
async def test_fetch_feed_updates_metadata(hass: HomeAssistant) -> None:
    """Fetch a feed and populate metadata and episodes."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    parsed = _build_parsed_feed()
    count_expected = len(parsed.entries)

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
    assert len(feed.episodes) == count_expected
    assert feed.episodes[0].guid == "episode-1"


@pytest.mark.asyncio
async def test_fetch_feed_handles_errors(hass: HomeAssistant) -> None:
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


@pytest.mark.asyncio
async def test_async_fetch_reads_response(hass: HomeAssistant) -> None:
    """_async_fetch reads response bytes."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )

    feed_xml = """<?xml version=\"1.0\"?>
<rss version=\"2.0\">
  <channel>
    <title>Lage der Nation</title>
    <image>
      <url>https://example.com/feed.png</url>
    </image>
    <item>
      <guid>episode-1</guid>
      <title>Episode 1</title>
      <link>https://example.com/episode1</link>
      <enclosure url=\"https://example.com/audio1.mp3\" type=\"audio/mpeg\" />
      <description>Episode 1 summary</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

    class _DummyResponse:
        def raise_for_status(self) -> None:
            return None

        async def read(self) -> bytes:
            return feed_xml.encode()

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

    class _DummySession:
        def get(self, url: str) -> _DummyResponse:  # noqa: ARG002
            return _DummyResponse()

    with patch(
        "custom_components.podcast_hub.podcast_hub.async_get_clientsession",
        return_value=_DummySession(),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.image_url == "https://example.com/feed.png"
    assert feed.episodes[0].guid == "episode-1"


@pytest.mark.asyncio
async def test_build_episodes_respects_limit(hass: HomeAssistant) -> None:
    """Stop building episodes at max_episodes."""
    hub = PodcastHub(hass, [])
    max_episodes = 1
    feed = PodcastFeed(
        feed_id="example",
        name="Example Podcast",
        url="https://example.com/feed.xml",
        max_episodes=max_episodes,
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

    assert len(feed.episodes) == max_episodes


@pytest.mark.asyncio
async def test_build_episodes_skips_missing_guid(hass: HomeAssistant) -> None:
    """Skip entries that cannot be converted into episodes."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [FeedParserDict(title="No guid")]
    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)

    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes == []


@pytest.mark.asyncio
async def test_entry_to_episode_uses_link_as_fallback(hass: HomeAssistant) -> None:
    """Use entry link as audio URL when no enclosure is present."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [
        FeedParserDict(id="episode-1", title="Episode", link="https://example.com/a")
    ]
    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)
    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes[0] is not None
    assert feed.episodes[0].url == "https://example.com/a"


@pytest.mark.asyncio
async def test_no_episodes_when_no_guids_and_link_empty(hass: HomeAssistant) -> None:
    """Skip entries that have no enclosure or link."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [FeedParserDict(id="episode-1", title="Episode", link="")]
    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)
    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes == []


@pytest.mark.asyncio
async def test_no_episodes_when_links_are_empty(hass: HomeAssistant) -> None:
    """Return None when no enclosure is present."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [FeedParserDict(id="episode-1", title="Episode", links=[])]
    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)
    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes == []


@pytest.mark.asyncio
async def test_entry_audio_url_handles_missing_attribute(hass: HomeAssistant) -> None:
    """Return None when enclosures attribute is missing."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "rel": "alternate",
                    "type": "text/html",
                    "href": "http://example.org/item/1",
                }
            ],
        )
    ]

    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)
    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes == []


@pytest.mark.asyncio
async def test_entry_audio_url_skips_empty_href(hass: HomeAssistant) -> None:
    """Skip enclosures without href."""
    """Return None when enclosures attribute is missing."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "href": "",
                    "type": "audio/mpeg",
                    "length": "12345",
                    "rel": "enclosure",
                }
            ],
        )
    ]

    parsed = _build_parsed_feed(additional_entries=entries, use_default_entries=False)
    with (
        patch.object(hub, "_async_fetch", new=AsyncMock(return_value=b"data")),
        patch(
            "custom_components.podcast_hub.podcast_hub.feedparser.parse",
            return_value=parsed,
        ),
    ):
        await hub.fetch_feed(feed, force_refresh=True)

    assert feed.episodes == []


@pytest.mark.asyncio
async def test_entry_audio_url_skips_then_returns(hass: HomeAssistant) -> None:
    """Skip empty href then return the next enclosure."""
    entry = FeedParserDict(
        id="episode-3",
        title="Episode",
        links=[
            {
                "href": "",
                "type": "audio/mpeg",
                "length": "12345",
                "rel": "enclosure",
            },
            {
                "href": "https://example.com/episode-3.mp3",
                "type": "audio/mpeg",
                "length": "12345",
                "rel": "enclosure",
            },
        ],
    )

    feed = await _fetch_feed(hass, additional_entries=[entry])

    assert feed.episodes[2].url == "https://example.com/episode-3.mp3"


@pytest.mark.asyncio
async def test_entry_audio_url_returns_enclosure(hass: HomeAssistant) -> None:
    """Get audio URL from enclosure."""
    entry = FeedParserDict(
        id="episode-3",
        title="Episode",
        links=[
            {
                "href": "https://example.com/c.mp3",
                "type": "audio/mpeg",
                "length": "12345",
                "rel": "enclosure",
            }
        ],
    )

    feed = await _fetch_feed(hass, additional_entries=[entry])

    assert feed.episodes[2].url == entry.links[0]["href"]


@pytest.mark.asyncio
async def test_entry_published_returns_none_without_parsed(hass: HomeAssistant) -> None:
    """Return None when no published/updated parsed timestamps exist."""
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "href": "https://example.com/episode-1.mp3",
                    "type": "audio/mpeg",
                    "length": "12345",
                    "rel": "enclosure",
                }
            ],
        )
    ]
    feed = await _fetch_feed(
        hass, additional_entries=entries, use_default_entries=False
    )
    assert feed.episodes[0].published is None


@pytest.mark.asyncio
async def test_entry_published_returns_none_for_empty_parsed(
    hass: HomeAssistant,
) -> None:
    """Return None when parsed timestamps are present but empty."""
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "href": "https://example.com/episode-1.mp3",
                    "type": "audio/mpeg",
                    "length": "12345",
                    "rel": "enclosure",
                }
            ],
            published_parsed=(),
            updated_parsed=(),
        )
    ]
    feed = await _fetch_feed(
        hass, additional_entries=entries, use_default_entries=False
    )
    assert feed.episodes[0].published is None


@pytest.mark.asyncio
async def test_entry_published_returns_none_for_empty_updated(
    hass: HomeAssistant,
) -> None:
    """Return None when published is None and updated is empty."""
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "href": "https://example.com/episode-1.mp3",
                    "type": "audio/mpeg",
                    "length": "12345",
                    "rel": "enclosure",
                }
            ],
            published_parsed=None,
            updated_parsed=(),
        )
    ]
    feed = await _fetch_feed(
        hass, additional_entries=entries, use_default_entries=False
    )
    assert feed.episodes[0].published is None


@pytest.mark.asyncio
async def test_entry_published_returns_none_for_empty_list(hass: HomeAssistant) -> None:
    """Return None when published parsed is an empty list."""
    entries = [
        FeedParserDict(
            id="episode-1",
            title="Episode",
            links=[
                {
                    "href": "https://example.com/episode-1.mp3",
                    "type": "audio/mpeg",
                    "length": "12345",
                    "rel": "enclosure",
                }
            ],
            published_parsed=[],
            updated_parsed=(),
        )
    ]
    feed = await _fetch_feed(
        hass, additional_entries=entries, use_default_entries=False
    )
    assert feed.episodes[0].published is None


@pytest.mark.asyncio
async def test_feed_image_url(hass: HomeAssistant) -> None:
    """Use image when present."""
    feed = await _fetch_feed(
        hass,
        feed_overrides={
            "image": {"href": "https://example.com/use-image.png"},
            "itunes_image": {"href": "https://example.com/itunes.png"},
        },
    )

    assert feed.image_url == "https://example.com/use-image.png"


@pytest.mark.asyncio
async def test_feed_image_url_itunes_fallback(hass: HomeAssistant) -> None:
    """Use itunes image when present."""
    feed = await _fetch_feed(
        hass,
        feed_overrides={
            "image": {},
            "itunes_image": {"href": "https://example.com/i.png"},
        },
    )

    assert feed.image_url == "https://example.com/i.png"


@pytest.mark.asyncio
async def test_feed_image_url_missing_href(hass: HomeAssistant) -> None:
    """Return None when image dict has no href/url and itunes is empty."""
    feed = await _fetch_feed(
        hass,
        feed_overrides={
            "image": {},
            "itunes_image": {},
        },
    )

    assert feed.image_url is None


@pytest.mark.asyncio
async def test_feed_image_url_non_dict_image(hass: HomeAssistant) -> None:
    """Skip non-dict image and fall back to itunes image."""
    feed = await _fetch_feed(
        hass,
        feed_overrides={
            "image": "not-a-dict",
            "itunes_image": {"href": "https://example.com/i.png"},
        },
    )

    assert feed.image_url == "https://example.com/i.png"


@pytest.mark.asyncio
async def test_entry_image_url_variants(hass: HomeAssistant) -> None:
    """Return entry image URLs from multiple sources."""
    feed = await _fetch_feed(hass, additional_entries=[])
    assert feed.image_url == "https://example.com/feed.png"

    feed = await _fetch_feed(
        hass,
        additional_entries=[
            FeedParserDict(
                id="episode-3",
                title="Episode",
                link="https://example.com/episode-3",
                image={"url": "https://example.com/image-a.png"},
                itunes_image={"href": "https://example.com/itunes-b.png"},
                media_thumbnail=[{"url": "https://example.com/media-c.png"}],
            ),
            FeedParserDict(
                id="episode-4",
                title="Episode",
                link="https://example.com/episode-4",
                itunes_image={"href": "https://example.com/itunes-d.png"},
                media_thumbnail=[{"url": "https://example.com/media-e.png"}],
            ),
            FeedParserDict(
                id="episode-5",
                title="Episode",
                link="https://example.com/episode-4",
                media_thumbnail=[{"url": "https://example.com/media-f.png"}],
            ),
        ],
    )

    assert feed.episodes[2].image_url == "https://example.com/image-a.png"
    assert feed.episodes[3].image_url == "https://example.com/itunes-d.png"
    assert feed.episodes[4].image_url == "https://example.com/media-f.png"


@pytest.mark.asyncio
async def test_entry_image_url_missing_values(hass: HomeAssistant) -> None:
    """Return None when image fields are present but empty."""
    feed = await _fetch_feed(
        hass,
        additional_entries=[
            FeedParserDict(
                id="episode-3",
                title="Episode",
                link="https://example.com/episode-3",
                image={"href": ""},
                itunes_image={"href": ""},
                media_thumbnail=[{"url": ""}],
            )
        ],
    )

    assert feed.episodes[2].image_url is None


@pytest.mark.asyncio
async def test_scheduled_refresh_due_without_last_update(hass: HomeAssistant) -> None:
    """Scheduled refresh is due when no last update exists."""
    hub = PodcastHub(hass, [])
    feed = PodcastFeed(
        feed_id="example",
        name="Example",
        url="https://example.com/feed.xml",
        max_episodes=10,
    )
    now_local = datetime.datetime.now(datetime.UTC)

    assert hub._is_scheduled_refresh_due(feed, now_local)  # noqa: SLF001


@pytest.mark.asyncio
async def test_next_scheduled_time_rolls_to_next_day(hass: HomeAssistant) -> None:
    """Next scheduled time rolls over to the next day when needed."""
    hub = PodcastHub(hass, [])
    last_local = datetime.datetime(2024, 1, 1, 20, 0, tzinfo=datetime.UTC)
    refresh_times = [datetime.time(9, 0)]

    next_time = hub._next_scheduled_time(last_local, refresh_times)  # noqa: SLF001

    assert next_time.date().day == last_local.date().day + 1
