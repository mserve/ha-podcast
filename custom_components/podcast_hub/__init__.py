"""
Custom integration to integrate podcast_hub with Home Assistant.

For more details about this integration, please refer to
https://github.com/mserve/podcast_hub
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
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
    from homeassistant.core import HomeAssistant, ServiceCall


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
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

    if not feeds:
        LOGGER.warning("No valid podcast feeds configured")
        return True

    hub = PodcastHub(feeds)
    coordinator = PodcastHubCoordinator(hass, hub, update_interval)
    await coordinator.async_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["hub"] = hub
    hass.data[DOMAIN]["coordinator"] = coordinator

    async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
        try:
            await coordinator.async_request_refresh()
        except (TimeoutError, aiohttp.ClientError) as err:
            LOGGER.exception("Failed to reload podcast feeds: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)

    for platform in PLATFORMS:
        await discovery.async_load_platform(hass, platform, DOMAIN, {}, config)

    return True
