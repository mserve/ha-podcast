"""
Custom integration to integrate podcast_hub with Home Assistant.

For more details about this integration, please refer to
https://github.com/mserve/ha-podcast
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import aiohttp
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_PODCASTS,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_RELOAD,
)
from .coordinator import PodcastHubCoordinator
from .podcast_hub import PodcastFeed, PodcastHub

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

PODCAST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ID): cv.slug,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_URL): cv.url,
        vol.Optional(CONF_MAX_EPISODES, default=DEFAULT_MAX_EPISODES): vol.Coerce(int),
        vol.Optional(CONF_UPDATE_INTERVAL): vol.Coerce(int),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.Coerce(int),
                vol.Optional(CONF_MEDIA_TYPE, default="track"): vol.In(
                    ["track", "podcast"]
                ),
                vol.Optional(CONF_PODCASTS, default=[]): vol.All(
                    cv.ensure_list, [PODCAST_SCHEMA]
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """
    Set up the Podcast Hub integration.

    Parameters
    ----------
    hass : HomeAssistant
        The Home Assistant instance.
    config : dict[str, Any]
        The configuration for the integration.

    Returns
    -------
    bool
        True if setup was successful, False otherwise.

    """
    conf = config.get(DOMAIN)
    if not conf:
        return True

    update_interval = conf.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    try:
        update_interval = int(update_interval)
    except (TypeError, ValueError):
        update_interval = DEFAULT_UPDATE_INTERVAL
    media_type = conf.get(CONF_MEDIA_TYPE, "track")
    if media_type not in {"track", "podcast"}:
        media_type = "track"

    podcasts = conf.get(CONF_PODCASTS, [])
    feeds: list[PodcastFeed] = []
    for item in podcasts:
        feed_id = item.get(CONF_ID)
        name = item.get(CONF_NAME)
        url = item.get(CONF_URL)
        if not feed_id or not name or not url:
            LOGGER.warning("Skipping invalid podcast config: %s", item)
            continue
        max_episodes = item.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES)
        feed_update_interval = item.get(CONF_UPDATE_INTERVAL, None)
        feeds.append(
            PodcastFeed(
                feed_id=feed_id,
                name=name,
                url=url,
                max_episodes=max_episodes,
                update_interval=feed_update_interval,
            )
        )

    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN]
    data["has_yaml"] = True
    data["media_type"] = media_type
    hub, coordinator = _ensure_hub_and_coordinator(hass, update_interval)
    _merge_feeds(hub, feeds)
    await coordinator.async_refresh()

    async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
        try:
            await coordinator.async_request_refresh()
        except (TimeoutError, aiohttp.ClientError) as err:
            LOGGER.exception("Failed to reload podcast feeds: %s", err)

    if not data.get("service_registered"):
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)
        data["service_registered"] = True

    for platform in PLATFORMS:
        await discovery.async_load_platform(hass, platform, DOMAIN, {}, config)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Podcast Hub from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN]
    if entry.unique_id == "settings":
        hass.data[DOMAIN]["settings_entry"] = entry
        _update_coordinator_interval(hass, entry.data.get(CONF_UPDATE_INTERVAL))
        return True

    global_interval = _get_global_update_interval(hass)
    hub, coordinator = _ensure_hub_and_coordinator(hass, global_interval)

    feed = PodcastFeed(
        feed_id=entry.data[CONF_ID],
        name=entry.data[CONF_NAME],
        url=entry.data[CONF_URL],
        max_episodes=entry.data.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES),
        update_interval=entry.data.get(CONF_UPDATE_INTERVAL),
    )
    hub.feeds[feed.feed_id] = feed
    await coordinator.async_request_refresh()

    if not data.get("service_registered"):

        async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
            try:
                await coordinator.async_request_refresh()
            except (TimeoutError, aiohttp.ClientError) as err:
                LOGGER.exception("Failed to reload podcast feeds: %s", err)

        hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)
        data["service_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Podcast Hub config entry."""
    data = hass.data.get(DOMAIN)
    if not data:
        return True

    if entry.unique_id == "settings":
        data.pop("settings_entry", None)
        _update_coordinator_interval(hass, DEFAULT_UPDATE_INTERVAL)
        return True

    hub: PodcastHub | None = data.get("hub")
    if hub and hub.feeds:
        feed_id = entry.data.get(CONF_ID)
        if feed_id:
            hub.feeds.pop(feed_id, None)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    if not data.get("has_yaml") and hub and not hub.feeds:
        data.pop("hub", None)
        data.pop("coordinator", None)
    return True


def _ensure_hub_and_coordinator(
    hass: HomeAssistant, update_interval: int
) -> tuple[PodcastHub, PodcastHubCoordinator]:
    data = hass.data.setdefault(DOMAIN, {})
    hub = data.get("hub")
    coordinator = data.get("coordinator")
    if hub and coordinator:
        return hub, coordinator
    hub = PodcastHub([])
    coordinator = PodcastHubCoordinator(hass, hub, update_interval)
    data["hub"] = hub
    data["coordinator"] = coordinator
    return hub, coordinator


def _merge_feeds(hub: PodcastHub, feeds: list[PodcastFeed]) -> None:
    for feed in feeds:
        hub.feeds[feed.feed_id] = feed


def _get_global_update_interval(hass: HomeAssistant) -> int:
    data = hass.data.get(DOMAIN, {})
    settings = data.get("settings_entry")
    if settings:
        return settings.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    return DEFAULT_UPDATE_INTERVAL


def _update_coordinator_interval(hass: HomeAssistant, interval: int | None) -> None:
    data = hass.data.get(DOMAIN, {})
    coordinator: PodcastHubCoordinator | None = data.get("coordinator")
    if not coordinator:
        return
    minutes = interval or DEFAULT_UPDATE_INTERVAL
    coordinator.update_interval = timedelta(minutes=minutes)
