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
    CONF_REFRESH_TIMES,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_MAX_EPISODES,
    PLATFORMS,
    SERVICE_RELOAD,
)
from .coordinator import PodcastHubCoordinator
from .podcast_hub import PodcastFeed, PodcastHub
from .time_utils import normalize_refresh_times, parse_refresh_times

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

PODCAST_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ID): cv.slug,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_URL): cv.url,
        vol.Optional(CONF_MAX_EPISODES, default=DEFAULT_MAX_EPISODES): vol.All(
            vol.Coerce(int), vol.Clamp(min=1, max=MAX_MAX_EPISODES)
        ),
        vol.Optional(CONF_REFRESH_TIMES, default=[]): vol.All(
            cv.ensure_list, normalize_refresh_times
        ),
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

    update_interval = _coerce_update_interval(
        conf.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    )
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
        max_episodes = _coerce_max_episodes(
            item.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES)
        )
        feed_update_interval = item.get(CONF_UPDATE_INTERVAL, None)
        refresh_times = parse_refresh_times(item.get(CONF_REFRESH_TIMES))
        feeds.append(
            PodcastFeed(
                feed_id=feed_id,
                name=name,
                url=url,
                max_episodes=max_episodes,
                update_interval=feed_update_interval,
                refresh_times=refresh_times,
            )
        )

    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN]
    data["has_yaml"] = True
    data["yaml_update_interval"] = update_interval
    data["media_type"] = media_type
    hub, coordinator = _ensure_hub_and_coordinator(hass, update_interval)
    _merge_feeds(hub, feeds)
    await coordinator.async_refresh()

    async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
        try:
            LOGGER.debug("Manual reload requested; refreshing podcast feeds now")
            await coordinator.async_refresh()
            LOGGER.debug("Manual reload completed")
        except (TimeoutError, aiohttp.ClientError) as err:
            LOGGER.exception("Failed to reload podcast feeds: %s", err)

    if not data.get("service_registered"):
        LOGGER.debug("Registering reload service")
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
        settings = entry.options or entry.data
        _update_coordinator_interval(hass, settings.get(CONF_UPDATE_INTERVAL))
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        return True

    global_interval = _get_global_update_interval(hass)
    hub, coordinator = _ensure_hub_and_coordinator(hass, global_interval)

    source = entry.options or entry.data
    feed = PodcastFeed(
        feed_id=entry.data[CONF_ID],
        name=source.get(CONF_NAME, entry.data[CONF_NAME]),
        url=source.get(CONF_URL, entry.data[CONF_URL]),
        max_episodes=_coerce_max_episodes(
            source.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES)
        ),
        update_interval=source.get(CONF_UPDATE_INTERVAL),
        refresh_times=parse_refresh_times(source.get(CONF_REFRESH_TIMES)),
    )
    hub.feeds[feed.feed_id] = feed
    LOGGER.debug("New feed added; refreshing podcast feeds now")
    await coordinator.async_refresh()
    LOGGER.debug("Feed addition refresh completed")

    if not data.get("service_registered"):

        async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
            try:
                LOGGER.debug("Manual reload requested; refreshing podcast feeds now")
                await coordinator.async_refresh()
                LOGGER.debug("Manual reload completed")
            except (TimeoutError, aiohttp.ClientError) as err:
                LOGGER.exception("Failed to reload podcast feeds: %s", err)

        LOGGER.debug("Registering reload service")
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)
        data["service_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Podcast Hub config entry."""
    data = hass.data.get(DOMAIN)
    if not data:
        return True

    if entry.unique_id == "settings":
        data.pop("settings_entry", None)
        _update_coordinator_interval(hass, _get_global_update_interval(hass))
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
        source = settings.options or settings.data
        return source.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    yaml_interval = data.get("yaml_update_interval")
    if yaml_interval:
        return yaml_interval
    return DEFAULT_UPDATE_INTERVAL


def _update_coordinator_interval(hass: HomeAssistant, interval: int | None) -> None:
    data = hass.data.get(DOMAIN, {})
    coordinator: PodcastHubCoordinator | None = data.get("coordinator")
    if not coordinator:
        return
    minutes = _coerce_update_interval(interval)
    base_interval = timedelta(minutes=minutes)
    coordinator.base_update_interval = base_interval
    coordinator.update_interval = base_interval


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.unique_id == "settings":
        settings = entry.options or entry.data
        _update_coordinator_interval(hass, settings.get(CONF_UPDATE_INTERVAL))
    else:
        source = entry.options or entry.data
        new_title = source.get(CONF_NAME)
        if new_title and entry.title != new_title:
            hass.config_entries.async_update_entry(entry, title=new_title)
    await hass.config_entries.async_reload(entry.entry_id)


def _coerce_max_episodes(value: int | None) -> int:
    try:
        coerced = int(value) if value is not None else DEFAULT_MAX_EPISODES
    except (TypeError, ValueError):
        coerced = DEFAULT_MAX_EPISODES
    return max(1, min(coerced, MAX_MAX_EPISODES))


def _coerce_update_interval(value: int | None) -> int:
    minutes = _safe_interval(value)
    return minutes if minutes is not None else DEFAULT_UPDATE_INTERVAL


def _safe_interval(value: int | None) -> int | None:
    try:
        minutes = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return minutes if minutes and minutes > 0 else None
