"""Config flow for Podcast Hub."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_REFRESH_TIMES,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_MAX_EPISODES,
)
from .time_utils import normalize_refresh_times

CONF_SETTINGS = "settings"


class PodcastHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Podcast Hub."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        # Route settings vs feed entries to different options steps.
        return PodcastHubOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""
        # Always use the menu step to branch between feed and settings flows.
        return await self.async_step_menu()

    async def async_step_menu(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> config_entries.ConfigFlowResult:
        """Show menu for setup."""
        # Expose explicit choices for adding a feed vs configuring defaults.
        return self.async_show_menu(
            step_id="menu",
            menu_options=["add_feed", "settings"],
        )

    async def async_step_add_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle adding a podcast feed."""
        errors: dict[str, str] = {}
        if user_input is not None:
            refresh_times: list[str] = []
            try:
                cv.url(user_input[CONF_URL])
            except vol.Invalid:
                errors[CONF_URL] = "invalid_url"
            try:
                # Extract selector payload and normalize to HH:MM list.
                refresh_times = normalize_refresh_times(
                    _extract_refresh_times(user_input.get(CONF_REFRESH_TIMES))
                )
            except vol.Invalid:
                errors[CONF_REFRESH_TIMES] = "invalid_time"
            # Generate a unique feed id based on name/url and existing entries.
            feed_id = _generate_feed_id(
                user_input[CONF_NAME],
                user_input[CONF_URL],
                self._existing_feed_ids(),
            )
            user_input[CONF_ID] = feed_id
            user_input[CONF_REFRESH_TIMES] = refresh_times

            if not errors:
                # Ensure id uniqueness across entries and create the feed entry.
                await self.async_set_unique_id(feed_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): cv.string,
                vol.Required(CONF_URL): cv.string,
                vol.Optional(CONF_MAX_EPISODES, default=DEFAULT_MAX_EPISODES): vol.All(
                    vol.Coerce(int), vol.Clamp(min=1, max=MAX_MAX_EPISODES)
                ),
                vol.Optional(
                    CONF_REFRESH_TIMES,
                    default=[],
                ): selector.ObjectSelector(
                    selector.ObjectSelectorConfig(
                        multiple=True,
                        fields={
                            "time": selector.ObjectSelectorField(selector={"time": {}})
                        },
                    )
                ),
                vol.Optional(CONF_UPDATE_INTERVAL): vol.Any(None, vol.Coerce(int)),
            }
        )
        return self.async_show_form(
            step_id="add_feed", data_schema=schema, errors=errors
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle global settings."""
        if user_input is not None:
            # Store global defaults in a dedicated settings entry.
            settings_data = {
                CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                CONF_MEDIA_TYPE: user_input[CONF_MEDIA_TYPE],
            }
            await self.async_set_unique_id(CONF_SETTINGS)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Settings", data=settings_data)

        existing = self._settings_entry()
        default_value = (
            existing.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            if existing
            else DEFAULT_UPDATE_INTERVAL
        )
        default_media_type = (
            existing.data.get(CONF_MEDIA_TYPE, "track") if existing else "track"
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_INTERVAL, default=default_value): vol.Coerce(
                    int
                ),
                vol.Required(CONF_MEDIA_TYPE, default=default_media_type): vol.In(
                    ["track", "podcast"]
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    def _existing_feed_ids(self) -> set[str]:
        # Combine ids from config entries and any runtime-loaded YAML feeds.
        existing = {entry.data.get(CONF_ID) for entry in self._async_current_entries()}
        hub = self.hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            existing.update(hub.feeds.keys())
        return {feed_id for feed_id in existing if feed_id}

    def _settings_entry(self) -> config_entries.ConfigEntry | None:
        # Find the singleton settings entry by unique_id.
        for entry in self._async_current_entries():
            if entry.unique_id == CONF_SETTINGS:
                return entry
        return None


def _generate_feed_id(name: str, url: str, existing: set[str]) -> str:
    # Prefer a slugified name; fall back to the URL; ensure uniqueness.
    base = cv.slugify(name) or cv.slugify(url)
    if not base:
        base = "podcast"
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


class PodcastHubOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Podcast Hub settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the first step of the options flow."""
        # Route settings entry to settings options, everything else to feed options.
        if self._config_entry.unique_id == CONF_SETTINGS:
            return await self.async_step_settings(user_input)
        return await self.async_step_feed(user_input)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options for global settings."""
        if user_input is not None:
            # Options flow stores updates in entry.options.
            return self.async_create_entry(title="", data=user_input)

        source = self._config_entry.options or self._config_entry.data
        default_value = source.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        default_media_type = source.get(CONF_MEDIA_TYPE, "track")
        schema = vol.Schema(
            {
                vol.Required(CONF_UPDATE_INTERVAL, default=default_value): vol.Coerce(
                    int
                ),
                vol.Required(CONF_MEDIA_TYPE, default=default_media_type): vol.In(
                    ["track", "podcast"]
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_feed(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle options for a feed entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            refresh_times: list[str] = []
            try:
                cv.url(user_input[CONF_URL])
            except vol.Invalid:
                errors[CONF_URL] = "invalid_url"
            try:
                # Normalize refresh times from the time selector payload.
                refresh_times = normalize_refresh_times(
                    _extract_refresh_times(user_input.get(CONF_REFRESH_TIMES))
                )
            except vol.Invalid:
                errors[CONF_REFRESH_TIMES] = "invalid_time"

            if not errors:
                # Store normalized times; options update only for this entry.
                user_input[CONF_REFRESH_TIMES] = refresh_times
                return self.async_create_entry(title="", data=user_input)

        source = self._config_entry.options or self._config_entry.data
        refresh_times = source.get(CONF_REFRESH_TIMES, [])
        # Convert stored strings into selector-friendly dicts.
        default_times = [
            {"time": item} for item in _extract_refresh_times(refresh_times)
        ]
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=source.get(CONF_NAME, "")): cv.string,
                vol.Required(CONF_URL, default=source.get(CONF_URL, "")): cv.string,
                vol.Optional(
                    CONF_MAX_EPISODES,
                    default=source.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES),
                ): vol.All(vol.Coerce(int), vol.Clamp(min=1, max=MAX_MAX_EPISODES)),
                vol.Optional(
                    CONF_REFRESH_TIMES,
                    default=default_times,
                ): selector.ObjectSelector(
                    selector.ObjectSelectorConfig(
                        multiple=True,
                        fields={
                            "time": selector.ObjectSelectorField(selector={"time": {}})
                        },
                    )
                ),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=source.get(CONF_UPDATE_INTERVAL),
                ): vol.Any(None, vol.Coerce(int)),
            }
        )
        return self.async_show_form(step_id="feed", data_schema=schema, errors=errors)


def _extract_refresh_times(value: Any) -> list[str]:
    """Normalize selector payloads (list/dict/string) into a flat string list."""
    if not value:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for entry in value:
            time_value = entry.get("time") if isinstance(entry, dict) else entry
            if time_value:
                items.append(str(time_value))
        return items
    if isinstance(value, dict):
        time_value = value.get("time")
        return [str(time_value)] if time_value else []
    return [str(value)]
