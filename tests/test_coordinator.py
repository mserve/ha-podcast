"""Tests for the Podcast Hub coordinator."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.setup import async_setup_component

from custom_components.podcast_hub.const import DOMAIN

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
