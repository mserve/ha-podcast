"""Tests for YAML and UI setup helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigSubentry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.podcast_hub.const import (
    CONF_ID,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_PODCASTS,
    CONF_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SERVICE_RELOAD,
)
from custom_components.podcast_hub.coordinator import PodcastHubCoordinator
from custom_components.podcast_hub.init_ui import async_setup_entry, async_unload_entry
from custom_components.podcast_hub.init_yaml import async_setup
from custom_components.podcast_hub.podcast_hub import PodcastFeed, PodcastHub

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_yaml_setup_invalid_media_type_and_skips_invalid(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid media type defaults to track and invalid feeds are skipped."""
    hub = PodcastHub(hass, [])
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)

    config = {
        DOMAIN: {
            CONF_MEDIA_TYPE: "invalid",
            CONF_PODCASTS: [
                {CONF_ID: "bad", CONF_NAME: "Bad"},  # missing URL
                {
                    CONF_ID: "good",
                    CONF_NAME: "Good",
                    CONF_URL: "https://example.com/feed.xml",
                },
            ],
        }
    }

    with (
        patch(
            "custom_components.podcast_hub.init_yaml.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
    ):
        assert await async_setup(hass, config)

    assert "Skipping invalid podcast config" in caplog.text
    assert hass.data[DOMAIN]["media_type"] == "track"
    assert hass.data[DOMAIN]["yaml_feed_ids"] == {"good"}


@pytest.mark.asyncio
async def test_yaml_reload_service_handles_errors(hass) -> None:  # noqa: ANN001
    """Reload service swallows client errors."""
    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="good",
                name="Good",
                url="https://example.com/feed.xml",
                max_episodes=10,
            )
        ],
    )
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)

    config = {
        DOMAIN: {
            CONF_PODCASTS: [
                {
                    CONF_ID: "good",
                    CONF_NAME: "Good",
                    CONF_URL: "https://example.com/feed.xml",
                }
            ]
        }
    }

    with (
        patch(
            "custom_components.podcast_hub.init_yaml.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
        patch.object(
            coordinator,
            "async_force_refresh",
            AsyncMock(side_effect=aiohttp.ClientError),
        ),
    ):
        assert await async_setup(hass, config)
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)


@pytest.mark.asyncio
async def test_ui_setup_removes_stale_feeds(hass) -> None:  # noqa: ANN001
    """Remove feeds not in YAML or UI configuration."""
    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="yaml_feed",
                name="YAML Feed",
                url="https://example.com/yaml.xml",
                max_episodes=10,
            ),
            PodcastFeed(
                feed_id="stale",
                name="Stale Feed",
                url="https://example.com/stale.xml",
                max_episodes=10,
            ),
        ],
    )
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": coordinator,
        "yaml_feed_ids": {"yaml_feed"},
    }

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                CONF_ID: "ui_feed",
                CONF_NAME: "UI Feed",
                CONF_URL: "https://example.com/ui.xml",
            },
            subentry_type="feed",
            title="UI Feed",
            unique_id="ui_feed",
        ),
    )

    with (
        patch(
            "custom_components.podcast_hub.init_ui.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry)

    assert set(hub.feeds.keys()) == {"yaml_feed", "ui_feed"}


@pytest.mark.asyncio
async def test_ui_setup_skips_invalid_subentry(hass, caplog) -> None:  # noqa: ANN001
    """Skip subentries missing required fields."""
    hub = PodcastHub(hass, [])
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": coordinator,
        "yaml_feed_ids": set(),
    }

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={CONF_ID: "bad", CONF_NAME: "Bad"},
            subentry_type="feed",
            title="Bad",
            unique_id="bad",
        ),
    )

    with (
        patch(
            "custom_components.podcast_hub.init_ui.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry)

    assert "Skipping invalid podcast subentry config" in caplog.text
    assert "bad" not in hub.feeds


@pytest.mark.asyncio
async def test_ui_reload_service_handles_errors(hass) -> None:  # noqa: ANN001
    """Reload service swallows client errors for UI setup."""
    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="good",
                name="Good",
                url="https://example.com/feed.xml",
                max_episodes=10,
            )
        ],
    )
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": coordinator,
        "yaml_feed_ids": set(),
    }

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                CONF_ID: "good",
                CONF_NAME: "Good",
                CONF_URL: "https://example.com/feed.xml",
            },
            subentry_type="feed",
            title="Good",
            unique_id="good",
        ),
    )

    with (
        patch(
            "custom_components.podcast_hub.init_ui.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
        patch.object(
            coordinator,
            "async_force_refresh",
            AsyncMock(side_effect=aiohttp.ClientError),
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry)
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)


@pytest.mark.asyncio
async def test_ui_reload_service_success(hass) -> None:  # noqa: ANN001
    """Reload service completes successfully."""
    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="good",
                name="Good",
                url="https://example.com/feed.xml",
                max_episodes=10,
            )
        ],
    )
    coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)
    hass.data[DOMAIN] = {
        "hub": hub,
        "coordinator": coordinator,
        "yaml_feed_ids": set(),
    }

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={
                CONF_ID: "good",
                CONF_NAME: "Good",
                CONF_URL: "https://example.com/feed.xml",
            },
            subentry_type="feed",
            title="Good",
            unique_id="good",
        ),
    )

    force_refresh = AsyncMock()
    with (
        patch(
            "custom_components.podcast_hub.init_ui.ensure_hub_and_coordinator",
            return_value=(hub, coordinator),
        ),
        patch.object(coordinator, "async_refresh", AsyncMock()),
        patch.object(coordinator, "async_force_refresh", force_refresh),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
    ):
        assert await async_setup_entry(hass, entry)
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)
        await hass.async_block_till_done()

    force_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_ui_unload_entry_no_data(hass) -> None:  # noqa: ANN001
    """Return True when no data exists."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    assert await async_unload_entry(hass, entry)


@pytest.mark.asyncio
async def test_ui_unload_entry_returns_false_on_failure(hass) -> None:  # noqa: ANN001
    """Return False if platform unload fails."""
    hub = PodcastHub(hass, [])
    hass.data[DOMAIN] = {"hub": hub, "config_entry": MockConfigEntry(domain=DOMAIN)}
    entry = MockConfigEntry(domain=DOMAIN, data={})

    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ):
        assert await async_unload_entry(hass, entry) is False


@pytest.mark.asyncio
async def test_ui_unload_entry_skips_missing_feed_id(hass) -> None:  # noqa: ANN001
    """Skip subentries without feed ids when unloading."""
    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="feed",
                name="Feed",
                url="https://example.com/feed.xml",
                max_episodes=10,
            )
        ],
    )
    hass.data[DOMAIN] = {"hub": hub, "config_entry": MockConfigEntry(domain=DOMAIN)}
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    hass.config_entries.async_add_subentry(
        entry,
        ConfigSubentry(
            data={},
            subentry_type="feed",
            title="Missing",
            unique_id="missing",
        ),
    )

    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)
    ):
        assert await async_unload_entry(hass, entry)
