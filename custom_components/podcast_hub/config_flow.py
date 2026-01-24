"""Config flow for Podcast Hub."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

CONF_SETTINGS = "settings"


class PodcastHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Podcast Hub."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        return await self.async_step_menu()

    async def async_step_menu(self, user_input: dict[str, Any] | None = None):
        """Show menu for setup."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["add_feed", "settings"],
        )

    async def async_step_add_feed(self, user_input: dict[str, Any] | None = None):
        """Handle adding a podcast feed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                cv.url(user_input[CONF_URL])
            except vol.Invalid:
                errors[CONF_URL] = "invalid_url"
            feed_id = _generate_feed_id(
                user_input[CONF_NAME],
                user_input[CONF_URL],
                self._existing_feed_ids(),
            )
            user_input[CONF_ID] = feed_id

            if not errors:
                await self.async_set_unique_id(feed_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_URL): cv.string,
                vol.Optional(CONF_MAX_EPISODES, default=DEFAULT_MAX_EPISODES): vol.Coerce(
                    int
                ),
                vol.Optional(CONF_UPDATE_INTERVAL): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="add_feed", data_schema=schema, errors=errors)

    async def async_step_settings(self, user_input: dict[str, Any] | None = None):
        """Handle global settings."""
        if user_input is not None:
            settings_data = {CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL]}
            await self.async_set_unique_id(CONF_SETTINGS)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Settings", data=settings_data)

        existing = self._settings_entry()
        default_value = (
            existing.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            if existing
            else DEFAULT_UPDATE_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=default_value
                ): vol.Coerce(int),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    def _existing_feed_ids(self) -> set[str]:
        existing = {entry.data.get(CONF_ID) for entry in self._async_current_entries()}
        hub = self.hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            existing.update(hub.feeds.keys())
        return {feed_id for feed_id in existing if feed_id}

    def _settings_entry(self) -> config_entries.ConfigEntry | None:
        for entry in self._async_current_entries():
            if entry.unique_id == CONF_SETTINGS:
                return entry
        return None


def _generate_feed_id(name: str, url: str, existing: set[str]) -> str:
    base = cv.slugify(name) or cv.slugify(url)
    if not base:
        base = "podcast"
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate
