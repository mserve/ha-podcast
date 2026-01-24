"""Tests for the Podcast Hub config flow."""

from __future__ import annotations

import pytest

from custom_components.podcast_hub.const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.mark.asyncio
async def test_config_flow_creates_entry(hass) -> None:  # noqa: ANN001
    """Create a config entry from the user flow."""
    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=user_input
    )

    assert result["type"] == "form"
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "menu"}, data={"next_step_id": "add_feed"}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "add_feed"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "add_feed"}, data=user_input
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Lage der Nation"
    assert result["data"][CONF_ID] == "lage_der_nation"
    assert result["data"][CONF_NAME] == user_input[CONF_NAME]
    assert result["data"][CONF_URL] == user_input[CONF_URL]
    assert result["data"][CONF_MAX_EPISODES] == user_input[CONF_MAX_EPISODES]
    assert result["data"][CONF_UPDATE_INTERVAL] == user_input[CONF_UPDATE_INTERVAL]


@pytest.mark.asyncio
async def test_config_flow_rejects_duplicate_id(hass) -> None:  # noqa: ANN001
    """Reject a feed id that is already configured."""
    user_input = {
        CONF_NAME: "Lage der Nation",
        CONF_URL: "https://example.com/feed.xml",
        CONF_MAX_EPISODES: 50,
        CONF_UPDATE_INTERVAL: 15,
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=user_input
    )
    assert result["type"] == "form"
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "menu"}, data={"next_step_id": "add_feed"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "add_feed"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "add_feed"}, data=user_input
    )
    assert result["type"] == "create_entry"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data=user_input
    )
    assert result["type"] == "form"
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "menu"}, data={"next_step_id": "add_feed"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "add_feed"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "add_feed"}, data=user_input
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "already_configured"


@pytest.mark.asyncio
async def test_config_flow_settings_entry(hass) -> None:  # noqa: ANN001
    """Create a settings entry for the global default interval."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "menu"

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "menu"}, data={"next_step_id": "settings"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "settings"},
        data={CONF_UPDATE_INTERVAL: 20, CONF_MEDIA_TYPE: "track"},
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Settings"
    assert result["data"][CONF_UPDATE_INTERVAL] == 20  # noqa: PLR2004
    assert result["data"][CONF_MEDIA_TYPE] == "track"
