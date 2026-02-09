"""Tests for the Podcast Hub config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from custom_components.podcast_hub.const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_REFRESH_TIMES,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DOMAIN,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("interval", "media_type"),
    [
        (5, "track"),
        (15, "podcast"),
        (30, "track"),
    ],
)
async def test_config_flow_creates_entry(
    hass: HomeAssistant, interval: int, media_type: str
) -> None:
    """Create the main config entry from the user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_UPDATE_INTERVAL: interval, CONF_MEDIA_TYPE: media_type},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Podcast Hub"
    assert result["data"][CONF_UPDATE_INTERVAL] == interval
    assert result["data"][CONF_MEDIA_TYPE] == media_type


@pytest.mark.asyncio
async def test_config_flow_adds_feed_subentry(hass) -> None:  # noqa: ANN001
    """Add a feed as a config subentry."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_REFRESH_TIMES: [{"time": "08:30"}, {"time": "18:00"}],
        CONF_UPDATE_INTERVAL: 15,
    }

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data=user_input,
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Lage der Nation"
    assert result["data"][CONF_ID] == "lage_der_nation"
    assert result["data"][CONF_NAME] == user_input[CONF_NAME]
    assert result["data"][CONF_URL] == user_input[CONF_URL]
    assert result["data"][CONF_MAX_EPISODES] == user_input[CONF_MAX_EPISODES]
    assert result["data"][CONF_REFRESH_TIMES] == ["08:30", "18:00"]
    assert result["data"][CONF_UPDATE_INTERVAL] == user_input[CONF_UPDATE_INTERVAL]

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert len(updated.subentries) == 1


@pytest.mark.asyncio
async def test_config_flow_unique_feed_id(hass) -> None:  # noqa: ANN001
    """Ensure feed ids are unique when adding multiple feeds."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data=user_input,
    )
    assert result["type"] == "create_entry"

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={**user_input, CONF_URL: "https://example.com/second.xml"},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ID] == "lage_der_nation_2"


@pytest.mark.asyncio
async def test_config_flow_settings_entry(hass) -> None:  # noqa: ANN001
    """Create a settings entry for the global default interval."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 20, CONF_MEDIA_TYPE: "track"},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Podcast Hub"
    assert result["data"][CONF_UPDATE_INTERVAL] == 20  # noqa: PLR2004
    assert result["data"][CONF_MEDIA_TYPE] == "track"


@pytest.mark.asyncio
async def test_options_flow_updates_settings(hass) -> None:  # noqa: ANN001
    """Update settings through the options flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 20, CONF_MEDIA_TYPE: "track"},
    )
    assert result["type"] == "create_entry"

    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "settings"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_UPDATE_INTERVAL: 30, CONF_MEDIA_TYPE: "podcast"},
    )
    assert result["type"] == "create_entry"

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated.options[CONF_UPDATE_INTERVAL] == 30  # noqa: PLR2004
    assert updated.options[CONF_MEDIA_TYPE] == "podcast"


@pytest.mark.asyncio
async def test_options_flow_updates_feed(hass) -> None:  # noqa: ANN001
    """Update feed details through the subentry reconfigure flow."""
    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data=user_input,
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Lage der Nation Updated",
            CONF_URL: "https://example.com/new.xml",
            CONF_MAX_EPISODES: 40,
            CONF_REFRESH_TIMES: [{"time": "06:15"}, {"time": "21:45"}],
            CONF_UPDATE_INTERVAL: 10,
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    updated_subentry = updated.subentries[subentry_id]
    assert updated_subentry.data[CONF_ID] == "lage_der_nation"
    assert updated_subentry.data[CONF_NAME] == "Lage der Nation Updated"
    assert updated_subentry.data[CONF_URL] == "https://example.com/new.xml"
    assert updated_subentry.data[CONF_REFRESH_TIMES] == ["06:15", "21:45"]


@pytest.mark.asyncio
async def test_options_flow_accepts_empty_feed_interval(hass) -> None:  # noqa: ANN001
    """Allow clearing per-feed update interval in reconfigure flow."""
    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }

    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data=user_input,
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Lage der Nation",
            CONF_URL: "https://example.com/feed.xml",
            CONF_MAX_EPISODES: 50,
            CONF_UPDATE_INTERVAL: None,
        },
    )
    assert result["type"] == "abort"
    assert result["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    updated_subentry = updated.subentries[subentry_id]
    assert updated_subentry.data[CONF_UPDATE_INTERVAL] is None


@pytest.mark.asyncio
async def test_subentry_reconfigure_does_not_reload_entry(hass) -> None:  # noqa: ANN001
    """Reconfigure a feed without scheduling a reload."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data=user_input,
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] == "form"

    with patch.object(hass.config_entries, "async_schedule_reload") as reload_mock:
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Lage der Nation Updated",
                CONF_URL: "https://example.com/new.xml",
                CONF_MAX_EPISODES: 40,
                CONF_UPDATE_INTERVAL: 10,
            },
        )
        assert result["type"] == "abort"
        assert result["reason"] == "reconfigure_successful"
        reload_mock.assert_not_called()
