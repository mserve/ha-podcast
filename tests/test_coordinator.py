"""Tests for the Podcast Hub coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.setup import async_setup_component

from custom_components.podcast_hub.const import DOMAIN, EVENT_NEW_EPISODE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


FEED_XML = """<?xml version=\"1.0\"?>
<rss version=\"2.0\">
  <channel>
    <title>Lage der Nation</title>
    <item>
      <guid>episode-1</guid>
      <title>Episode 1</title>
      <link>https://example.com/episode1</link>
      <enclosure url=\"https://example.com/audio1.mp3\" type=\"audio/mpeg\" />
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

FEED_XML_WITH_NEW = """<?xml version=\"1.0\"?>
<rss version=\"2.0\">
  <channel>
    <title>Lage der Nation</title>
    <item>
      <guid>episode-2</guid>
      <title>Episode 2</title>
      <link>https://example.com/episode2</link>
      <enclosure url=\"https://example.com/audio2.mp3\" type=\"audio/mpeg\" />
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    </item>
    <item>
      <guid>episode-1</guid>
      <title>Episode 1</title>
      <link>https://example.com/episode1</link>
      <enclosure url=\"https://example.com/audio1.mp3\" type=\"audio/mpeg\" />
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.mark.asyncio
async def test_coordinator_updates_and_sensor_attributes(hass: HomeAssistant) -> None:
    """Verify coordinator refresh updates sensor state and attributes."""
    config = {
        DOMAIN: {
            "update_interval": 15,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "max_episodes": 50,
                }
            ],
        }
    }

    async def fake_fetch(self, url) -> bytes:  # noqa: ANN001, ARG001
        return FEED_XML.encode()

    with patch(
        "custom_components.podcast_hub.coordinator.PodcastHubCoordinator._async_fetch",
        new=fake_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.podcast_lage_der_nation")
    assert state is not None
    assert state.state == "1"
    attrs = state.attributes
    assert attrs["title"] == "Lage der Nation"
    assert attrs["feed_url"] == "https://example.com/feed.xml"
    assert attrs["latest_episode_title"] == "Episode 1"
    assert attrs["latest_episode_url"] == "https://example.com/audio1.mp3"
    assert len(attrs["episodes"]) == 1


@pytest.mark.asyncio
async def test_new_episode_event_fires(hass: HomeAssistant) -> None:
    """Fire an event when a new episode appears after initial refresh."""
    config = {
        DOMAIN: {
            "update_interval": 15,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "max_episodes": 50,
                }
            ],
        }
    }

    async def fake_fetch_first(self, url) -> bytes:  # noqa: ANN001, ARG001
        return FEED_XML.encode()

    async def fake_fetch_second(self, url) -> bytes:  # noqa: ANN001, ARG001
        return FEED_XML_WITH_NEW.encode()

    with patch(
        "custom_components.podcast_hub.coordinator.PodcastHubCoordinator._async_fetch",
        new=fake_fetch_first,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    events: list[dict] = []

    def _capture(event) -> None:  # noqa: ANN001
        events.append(event.data)

    hass.bus.async_listen(EVENT_NEW_EPISODE, _capture)

    coordinator = hass.data[DOMAIN]["coordinator"]
    with patch(
        "custom_components.podcast_hub.coordinator.PodcastHubCoordinator._async_fetch",
        new=fake_fetch_second,
    ):
        await coordinator.async_request_refresh()
        await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0]["feed_id"] == "lage_der_nation"
    assert events[0]["episode"]["guid"] == "episode-2"
