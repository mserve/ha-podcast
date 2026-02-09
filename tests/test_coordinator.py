"""Tests for the Podcast Hub coordinator."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigSubentry
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.podcast_hub.const import DOMAIN, EVENT_NEW_EPISODE

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


FEED_XML = """<?xml version=\"1.0\"?>
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

FEED_XML_WITH_NEW = """<?xml version=\"1.0\"?>
<rss version=\"2.0\">
  <channel>
    <title>Lage der Nation</title>
    <item>
      <guid>episode-2</guid>
      <title>Episode 2</title>
      <link>https://example.com/episode2</link>
      <enclosure url=\"https://example.com/audio2.mp3\" type=\"audio/mpeg\" />
      <description>Episode 2 summary</description>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    </item>
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
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
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
    assert attrs["feed_id"] == "lage_der_nation"
    assert attrs["latest_episode_title"] == "Episode 1"
    assert attrs["latest_episode_guid"] == "episode-1"
    assert attrs["latest_episode_url"] == "https://example.com/audio1.mp3"
    assert attrs["last_update"] is not None
    assert len(attrs["episodes"]) == 1
    assert attrs["episodes"][0]["image_url"] is None
    assert attrs["image_url"] == "https://example.com/feed.png"


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
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
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
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=fake_fetch_second,
    ):
        await coordinator.async_force_refresh()
        await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0]["feed_id"] == "lage_der_nation"
    assert events[0]["episode"]["guid"] == "episode-2"


@pytest.mark.asyncio
async def test_config_entry_setup_without_yaml(
    hass: HomeAssistant,
) -> None:
    """Set up a config entry without YAML defaults present."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "update_interval": 15,
            "media_type": "track",
        },
        title="Podcast Hub",
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "id": "lage_der_nation",
                "name": "Lage der Nation",
                "url": "https://example.com/feed.xml",
                "max_episodes": 50,
            },
            subentry_type="feed",
            title="Lage der Nation",
            unique_id="lage_der_nation",
        ),
    )

    async def fake_fetch(self, url) -> bytes:  # noqa: ANN001, ARG001
        return FEED_XML.encode()

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=fake_fetch,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.podcast_lage_der_nation")
    assert state is not None
    assert state.state == "1"


@pytest.mark.asyncio
async def test_per_feed_update_interval_skips_refresh(hass: HomeAssistant) -> None:
    """Skip fetching when per-feed update interval has not elapsed."""
    config = {
        DOMAIN: {
            "update_interval": 1440,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "max_episodes": 50,
                    "update_interval": 60,
                }
            ],
        }
    }

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        first_time = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
        second_time = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
        third_time = datetime(2024, 1, 1, 9, 5, tzinfo=UTC)

        count_expected_requests = 2  # Initial fetch + third_time fetch

        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=first_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            assert await async_setup_component(hass, DOMAIN, config)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN]["coordinator"]
        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=second_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=third_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert async_fetch.call_count == count_expected_requests


@pytest.mark.asyncio
async def test_service_reload_forces_refresh(hass: HomeAssistant) -> None:
    """Service reload forces refresh regardless of schedule."""
    config = {
        DOMAIN: {
            "update_interval": 1440,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "update_interval": 60,
                }
            ],
        }
    }

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

        await hass.services.async_call(DOMAIN, "reload_sources", blocking=True)
        await hass.async_block_till_done()

    expected_calls = 2  # Initial fetch + reload fetch
    assert async_fetch.call_count == expected_calls


@pytest.mark.asyncio
async def test_default_interval_applies_when_feed_interval_missing(
    hass: HomeAssistant,
) -> None:
    """Use the global update interval when a feed has no per-feed interval."""
    config = {
        DOMAIN: {
            "update_interval": 10,
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

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    first_time = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    second_time = datetime(2024, 1, 1, 8, 5, tzinfo=UTC)
    third_time = datetime(2024, 1, 1, 8, 11, tzinfo=UTC)

    count_expected_requests = 2  # Initial fetch + third_time fetch

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=first_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            assert await async_setup_component(hass, DOMAIN, config)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN]["coordinator"]
        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=second_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=third_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert async_fetch.call_count == count_expected_requests


@pytest.mark.asyncio
async def test_refresh_schedule_updates_only_when_due(
    hass: HomeAssistant,
) -> None:
    """Update feed only when the next scheduled time is reached."""
    config = {
        DOMAIN: {
            "update_interval": 1440,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "max_episodes": 50,
                    "refresh_times": ["09:00"],
                }
            ],
        }
    }

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    first_time = datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    second_time = datetime(2024, 1, 1, 8, 30, tzinfo=UTC)
    third_time = datetime(2024, 1, 1, 9, 5, tzinfo=UTC)

    # Initial and first scheduled refresh only
    count_expected_requests = 2

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=first_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            assert await async_setup_component(hass, DOMAIN, config)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN]["coordinator"]
        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=second_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        with (
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.utcnow",
                return_value=third_time,
            ),
            patch(
                "custom_components.podcast_hub.podcast_hub.dt_util.as_local",
                side_effect=lambda value: value,
            ),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

    assert async_fetch.call_count == count_expected_requests


@pytest.mark.asyncio
async def test_coordinator_uses_global_update_interval(
    hass: HomeAssistant,
) -> None:
    """Set coordinator interval from the global update interval."""
    config = {
        DOMAIN: {
            "update_interval": 30,
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

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    with (
        patch(
            "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
            new=async_fetch,
        ),
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN]["coordinator"]
    assert coordinator.update_interval == timedelta(minutes=30)


@pytest.mark.asyncio
async def test_yaml_media_type_setting(hass: HomeAssistant) -> None:
    """Store media type from YAML configuration."""
    config = {
        DOMAIN: {
            "update_interval": 15,
            "media_type": "podcast",
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
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=fake_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    assert hass.data[DOMAIN]["media_type"] == "podcast"


@pytest.mark.asyncio
async def test_yaml_refresh_times_parsed_and_sorted(hass: HomeAssistant) -> None:
    """Parse and sort refresh_times from YAML configuration."""
    config = {
        DOMAIN: {
            "update_interval": 15,
            "podcasts": [
                {
                    "id": "lage_der_nation",
                    "name": "Lage der Nation",
                    "url": "https://example.com/feed.xml",
                    "max_episodes": 50,
                    "refresh_times": ["18:00", "9:05"],
                }
            ],
        }
    }

    async def fake_fetch(self, url) -> bytes:  # noqa: ANN001, ARG001
        return FEED_XML.encode()

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=fake_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    hub = hass.data[DOMAIN]["hub"]
    feed = hub.get_feed("lage_der_nation")
    assert feed is not None
    assert feed.refresh_times == [time(9, 5), time(18, 0)]


@pytest.mark.asyncio
async def test_mixed_yaml_and_ui_feeds_create_distinct_entities(
    hass: HomeAssistant,
) -> None:
    """Create sensors for YAML and UI feeds without duplicates."""
    config = {
        DOMAIN: {
            "update_interval": 15,
            "podcasts": [
                {
                    "id": "yaml_feed",
                    "name": "YAML Feed",
                    "url": "https://example.com/yaml.xml",
                    "max_episodes": 5,
                }
            ],
        }
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "update_interval": 15,
            "media_type": "track",
        },
        title="Podcast Hub",
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "id": "ui_feed",
                "name": "UI Feed",
                "url": "https://example.com/ui.xml",
                "max_episodes": 5,
            },
            subentry_type="feed",
            title="UI Feed",
            unique_id="ui_feed",
        ),
    )

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    state_yaml = hass.states.get("sensor.podcast_yaml_feed")
    state_ui = hass.states.get("sensor.podcast_ui_feed")
    assert state_yaml is not None
    assert state_ui is not None

    entity_registry = er.async_get(hass)
    entry_yaml = entity_registry.async_get("sensor.podcast_yaml_feed")
    entry_ui = entity_registry.async_get("sensor.podcast_ui_feed")
    assert entry_yaml is not None
    assert entry_ui is not None
    assert entry_yaml.unique_id == f"{DOMAIN}_yaml_feed"
    assert entry_ui.unique_id == f"{DOMAIN}_ui_feed"


@pytest.mark.asyncio
async def test_yaml_defaults_only_with_ui_feeds(hass: HomeAssistant) -> None:
    """Ensure YAML defaults do not create duplicate entities for UI feeds."""
    config = {
        DOMAIN: {
            "update_interval": 15,
        }
    }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "update_interval": 15,
            "media_type": "track",
        },
        title="Podcast Hub",
    )
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                "id": "ui_feed",
                "name": "UI Feed",
                "url": "https://example.com/ui.xml",
                "max_episodes": 5,
            },
            subentry_type="feed",
            title="UI Feed",
            unique_id="ui_feed",
        ),
    )

    async_fetch = AsyncMock(return_value=FEED_XML.encode())

    with patch(
        "custom_components.podcast_hub.podcast_hub.PodcastHub._async_fetch",
        new=async_fetch,
    ):
        assert await async_setup_component(hass, DOMAIN, config)
        await hass.async_block_till_done()

    state_ui = hass.states.get("sensor.podcast_ui_feed")
    assert state_ui is not None
    entity_registry = er.async_get(hass)
    entry_ui = entity_registry.async_get("sensor.podcast_ui_feed")
    assert entry_ui is not None
    assert entry_ui.unique_id == f"{DOMAIN}_ui_feed"
