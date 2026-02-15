"""Tests for the Podcast Hub config flow."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import InvalidData

from custom_components.podcast_hub.config_flow import PodcastHubConfigFlow
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
from custom_components.podcast_hub.podcast_hub import PodcastFeed, PodcastHub

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


@pytest.mark.asyncio
async def test_config_flow_aborts_when_already_configured(hass) -> None:  # noqa: ANN001
    """Second config flow aborts if already configured."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_config_flow_step_user_aborts_when_entry_exists(hass) -> None:  # noqa: ANN001
    """Direct user step aborts when an entry already exists."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    flow = PodcastHubConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user()

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_feed_subentry_invalid_url(hass) -> None:  # noqa: ANN001
    """Invalid URL produces a form error."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Bad Feed",
            CONF_URL: "not-a-url",
            CONF_MAX_EPISODES: 10,
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_URL] == "invalid_url"


@pytest.mark.asyncio
async def test_feed_subentry_empty_name_uses_url_for_id(hass) -> None:  # noqa: ANN001
    """When name is empty, feed id is generated from URL."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "",
            CONF_URL: "https://example.com/rss.xml",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ID] == "https_example_com_rss_xml"


@pytest.mark.asyncio
async def test_feed_subentry_empty_name_and_url_hits_podcast_fallback(hass) -> None:  # noqa: ANN001
    """When name and URL are empty, id fallback path executes and URL is rejected."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "",
            CONF_URL: "",
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_URL] == "invalid_url"


@pytest.mark.asyncio
async def test_feed_subentry_invalid_refresh_time(hass) -> None:  # noqa: ANN001
    """Invalid refresh times produce a form error."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Bad Feed",
            CONF_URL: "https://example.com/feed.xml",
            CONF_MAX_EPISODES: 10,
            CONF_REFRESH_TIMES: [{"time": "25:00"}],
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_REFRESH_TIMES] == "invalid_time"


@pytest.mark.asyncio
async def test_feed_subentry_refresh_times_dict_payload(hass) -> None:  # noqa: ANN001
    """Dict payload is normalized into a single refresh time."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
            CONF_REFRESH_TIMES: {"time": "08:15"},
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_REFRESH_TIMES] == ["08:15"]


@pytest.mark.asyncio
async def test_feed_subentry_refresh_times_skips_empty_list_entries(hass) -> None:  # noqa: ANN001
    """List entries without time are skipped during normalization."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
            CONF_REFRESH_TIMES: [{"time": ""}, {"time": "08:30"}],
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_REFRESH_TIMES] == ["08:30"]


@pytest.mark.asyncio
async def test_feed_subentry_refresh_times_non_collection_payload_is_invalid(
    hass: HomeAssistant,
) -> None:
    """Non-list payload reaches fallback extraction and fails time validation."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
            CONF_REFRESH_TIMES: 815,
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_REFRESH_TIMES] == "invalid_time"


@pytest.mark.asyncio
async def test_feed_subentry_duplicate_url_from_subentries(hass) -> None:  # noqa: ANN001
    """Duplicate URLs are rejected when already configured."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "create_entry"

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed 2",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "already_configured"


@pytest.mark.asyncio
async def test_feed_subentry_duplicate_url_from_hub(hass) -> None:  # noqa: ANN001
    """Duplicate URLs are rejected when already in hub feeds."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    hub = PodcastHub(
        hass,
        [
            PodcastFeed(
                feed_id="existing",
                name="Existing",
                url="https://example.com/feed.xml",
                max_episodes=10,
            )
        ],
    )
    hass.data[DOMAIN] = {"hub": hub}

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed 2",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "already_configured"


@pytest.mark.asyncio
async def test_feed_subentry_id_unique_against_hub_feed_ids(hass) -> None:  # noqa: ANN001
    """Feed id generation stays unique against ids already loaded in the hub."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    hass.data[DOMAIN] = {
        "hub": PodcastHub(
            hass,
            [
                PodcastFeed(
                    feed_id="lage_der_nation",
                    name="Existing Feed",
                    url="https://example.com/existing.xml",
                    max_episodes=10,
                )
            ],
        )
    }

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Lage der Nation",
            CONF_URL: "https://example.com/new.xml",
            CONF_MAX_EPISODES: 10,
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ID] == "lage_der_nation_2"


@pytest.mark.asyncio
async def test_feed_subentry_unique_id_when_no_hub_data(hass) -> None:  # noqa: ANN001
    """Generate unique ids from subentries when no hub runtime data is present."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    hass.data[DOMAIN] = {}

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/one.xml",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ID] == "feed"

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/two.xml",
        },
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_ID] == "feed_2"


@pytest.mark.asyncio
async def test_reconfigure_invalid_url_and_time(hass) -> None:  # noqa: ANN001
    """Reconfigure flow validates URL and times."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] == "form"

    with pytest.raises(InvalidData):
        await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Feed",
                CONF_URL: "bad",
                CONF_REFRESH_TIMES: [{"time": "25:00"}],
            },
        )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Feed",
            CONF_URL: "bad",
            CONF_REFRESH_TIMES: [{"time": "08:00"}],
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_URL] == "invalid_url"


@pytest.mark.asyncio
async def test_subentry_flow_user_shows_form(hass) -> None:  # noqa: ANN001
    """Show form when subentry flow has no user input."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"


@pytest.mark.asyncio
async def test_reconfigure_invalid_time_returns_form_error(hass) -> None:  # noqa: ANN001
    """Invalid refresh times in reconfigure raise schema InvalidData."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["type"] == "form"

    with pytest.raises(InvalidData):
        await hass.config_entries.subentries.async_configure(
            result["flow_id"],
            {
                CONF_NAME: "Feed",
                CONF_URL: "https://example.com/feed.xml",
                CONF_REFRESH_TIMES: [{"time": "25:00"}],
            },
        )


@pytest.mark.asyncio
async def test_reconfigure_invalid_time_via_direct_init_returns_form_error(
    hass: HomeAssistant,
) -> None:
    """Direct reconfigure init with bad list payload returns invalid_time error."""
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_UPDATE_INTERVAL: 15, CONF_MEDIA_TYPE: "track"},
    )
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "user"},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
        },
    )
    assert result["type"] == "create_entry"
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "feed"),
        context={"source": "reconfigure", "subentry_id": subentry_id},
        data={
            CONF_NAME: "Feed",
            CONF_URL: "https://example.com/feed.xml",
            CONF_REFRESH_TIMES: ["25:00"],
        },
    )
    assert result["type"] == "form"
    assert result["errors"][CONF_REFRESH_TIMES] == "invalid_time"
