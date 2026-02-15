"""YAML setup for Podcast Hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import discovery

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_MEDIA_TYPE,
    CONF_NAME,
    CONF_PODCASTS,
    CONF_REFRESH_TIMES,
    CONF_UPDATE_CHECK_INTERVAL,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DATA_DEFAULT_UPDATE_INTERVAL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_CHECK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_MAX_EPISODES,
    PLATFORMS,
    SERVICE_RELOAD,
)
from .init_common import (
    coerce_max_episodes,
    coerce_update_interval,
    ensure_hub_and_coordinator,
)
from .podcast_hub import PodcastFeed
from .time_utils import normalize_refresh_times, parse_refresh_times

if TYPE_CHECKING:
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
    Set up the Podcast Hub integration from YAML configuration.

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

    update_interval = coerce_update_interval(
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
        max_episodes = coerce_max_episodes(
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
    data["yaml_update_check_interval"] = conf.get(
        CONF_UPDATE_CHECK_INTERVAL, DEFAULT_UPDATE_CHECK_INTERVAL
    )
    data[DATA_DEFAULT_UPDATE_INTERVAL] = update_interval
    data["media_type"] = media_type
    data["yaml_feed_ids"] = {feed.feed_id for feed in feeds}
    if feeds:
        hub, coordinator = ensure_hub_and_coordinator(
            hass, conf.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )
        hub.merge_feeds(feeds)
        await coordinator.async_refresh()

    async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
        try:
            LOGGER.debug("Manual reload requested; refreshing podcast feeds now")
            await coordinator.async_force_refresh()
            LOGGER.debug("Manual reload completed")
        except (TimeoutError, aiohttp.ClientError) as err:
            LOGGER.exception("Failed to reload podcast feeds: %s", err)

    if not data.get("service_registered"):
        LOGGER.debug("Registering reload service")
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)
        data["service_registered"] = True

    if feeds:
        for platform in PLATFORMS:
            await discovery.async_load_platform(hass, platform, DOMAIN, {}, config)

    return True
