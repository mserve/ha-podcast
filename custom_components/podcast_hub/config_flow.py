"""Config flow for Podcast Hub."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
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


class PodcastHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Podcast Hub."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, _config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[config_entries.ConfigSubentryFlow]]:
        """Return supported subentry flows."""
        return {"feed": PodcastHubFeedSubentryFlowHandler}

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return PodcastHubOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle global settings."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        if user_input is not None:
            return self.async_create_entry(
                title="Podcast Hub",
                data={
                    CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    CONF_MEDIA_TYPE: user_input[CONF_MEDIA_TYPE],
                },
            )

        default_value = DEFAULT_UPDATE_INTERVAL
        default_media_type = "track"
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
        return self.async_show_form(step_id="user", data_schema=schema)


def _generate_feed_id(name: str, url: str, existing: set[str]) -> str:
    # Prefer a slugified name; fall back to the URL; ensure uniqueness.
    if name:
        base = cv.slugify(name)
    elif url:
        base = cv.slugify(url)
    else:
        base = "podcast"
    candidate = base
    counter = 2
    while candidate in existing:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


class PodcastHubFeedSubentryFlowHandler(config_entries.ConfigSubentryFlow):
    """Handle subentry flow for podcast feeds."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Handle adding a podcast feed subentry."""
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
            if self._is_existing_feed_url(user_input[CONF_URL]):
                errors["base"] = "already_configured"
            else:
                # Generate a unique feed id based on name/url and existing entries.
                feed_id = _generate_feed_id(
                    user_input[CONF_NAME],
                    user_input[CONF_URL],
                    self._existing_feed_ids(),
                )
                user_input[CONF_ID] = feed_id
                user_input[CONF_REFRESH_TIMES] = refresh_times

            if not errors:
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
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.SubentryFlowResult:
        """Handle reconfiguring a podcast feed subentry."""
        config_subentry = self._get_reconfigure_subentry()
        source = config_subentry.data
        errors: dict[str, str] = {}

        if user_input is not None:
            refresh_times: list[str] = []
            try:
                cv.url(user_input[CONF_URL])
            except vol.Invalid:
                errors[CONF_URL] = "invalid_url"
            try:
                refresh_times = normalize_refresh_times(
                    _extract_refresh_times(user_input.get(CONF_REFRESH_TIMES))
                )
            except vol.Invalid:
                errors[CONF_REFRESH_TIMES] = "invalid_time"

            if not errors:
                updated = {
                    **source,
                    **user_input,
                    CONF_ID: source.get(CONF_ID),
                    CONF_REFRESH_TIMES: refresh_times,
                }
                entry = self._get_entry()
                return self.async_update_and_abort(
                    entry=entry,
                    subentry=config_subentry,
                    title=updated.get(CONF_NAME, config_subentry.title),
                    data=updated,
                )

        refresh_times = source.get(CONF_REFRESH_TIMES, [])
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
        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    def _existing_feed_ids(self) -> set[str]:
        # Combine ids from subentries and any runtime-loaded YAML feeds.
        entry = self._get_entry()
        existing = {
            subentry.data.get(CONF_ID) for subentry in entry.subentries.values()
        }
        hub = self.hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            existing.update(hub.feeds.keys())
        return {feed_id for feed_id in existing if feed_id}

    def _is_existing_feed_url(self, url: str) -> bool:
        entry = self._get_entry()
        for subentry in entry.subentries.values():
            if subentry.data.get(CONF_URL) == url:
                return True
        hub = self.hass.data.get(DOMAIN, {}).get("hub")
        if hub:
            return any(feed.url == url for feed in hub.feeds.values())
        return False


class PodcastHubOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Podcast Hub settings."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the first step of the options flow."""
        return await self.async_step_settings(user_input)

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
