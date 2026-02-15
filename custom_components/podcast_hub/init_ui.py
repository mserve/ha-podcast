"""Config entry setup for Podcast Hub."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp

from .const import (
    CONF_ID,
    CONF_MAX_EPISODES,
    CONF_NAME,
    CONF_REFRESH_TIMES,
    CONF_UPDATE_INTERVAL,
    CONF_URL,
    DATA_DEFAULT_UPDATE_INTERVAL,
    DEFAULT_MAX_EPISODES,
    DEFAULT_UPDATE_CHECK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    PLATFORMS,
    SERVICE_RELOAD,
)
from .init_common import coerce_max_episodes, ensure_hub_and_coordinator
from .podcast_hub import PodcastFeed, PodcastHub
from .time_utils import parse_refresh_times

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Set up Podcast Hub from a config entry.

    Parameters
    ----------
    hass : HomeAssistant
        The Home Assistant instance.
    entry : ConfigEntry
        The configuration entry to set up.

    """
    hass.data.setdefault(DOMAIN, {})
    data = hass.data[DOMAIN]
    update_check_interval = data.get(
        "yaml_update_check_interval", DEFAULT_UPDATE_CHECK_INTERVAL
    )
    data[DATA_DEFAULT_UPDATE_INTERVAL] = entry.options.get(
        CONF_UPDATE_INTERVAL,
        entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )

    hub, coordinator = ensure_hub_and_coordinator(hass, update_check_interval)

    hass.data[DOMAIN]["config_entry"] = entry
    yaml_feed_ids = set(data.get("yaml_feed_ids", set()))
    desired_ids: set[str] = set()
    for subentry in entry.subentries.values():
        source = subentry.data
        feed_id = source.get(CONF_ID)
        name = source.get(CONF_NAME)
        url = source.get(CONF_URL)
        if not feed_id or not name or not url:
            LOGGER.warning(
                "Skipping invalid podcast subentry config: %s",
                source,
            )
            continue
        feed = PodcastFeed(
            feed_id=feed_id,
            name=name,
            url=url,
            max_episodes=coerce_max_episodes(
                source.get(CONF_MAX_EPISODES, DEFAULT_MAX_EPISODES)
            ),
            update_interval=source.get(CONF_UPDATE_INTERVAL),
            refresh_times=parse_refresh_times(source.get(CONF_REFRESH_TIMES)),
        )
        hub.add_feed(feed)
        desired_ids.add(feed.feed_id)
    protected_ids = set(yaml_feed_ids)
    protected_ids.update(desired_ids)
    for feed_id in list(hub.feeds.keys()):
        if feed_id not in protected_ids:
            hub.remove_feed(feed_id)
    LOGGER.debug("Subentry feeds loaded; refreshing podcast feeds now")
    await coordinator.async_refresh()
    LOGGER.debug("Subentry refresh completed")

    if not data.get("service_registered"):

        async def _async_handle_reload(call: ServiceCall) -> None:  # noqa: ARG001
            try:
                LOGGER.debug("Manual reload requested; scheduling refreshing podcast")
                await coordinator.async_force_refresh()
                LOGGER.debug("Manual reload completed")
            except (TimeoutError, aiohttp.ClientError) as err:
                LOGGER.exception("Failed to reload podcast feeds: %s", err)

        LOGGER.debug("Registering reload service")
        hass.services.async_register(DOMAIN, SERVICE_RELOAD, _async_handle_reload)
        data["service_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Podcast Hub config entry."""
    data = hass.data.get(DOMAIN)
    if not data:
        return True

    hub: PodcastHub | None = data.get("hub")
    if data.get("config_entry") == entry:
        data.pop("config_entry", None)
    if hub and hub.feeds:
        for subentry in entry.subentries.values():
            feed_id = subentry.data.get(CONF_ID)
            if feed_id:
                hub.remove_feed(feed_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    # Clean up hub and coordinator if no feeds remain and no YAML config
    if not data.get("has_yaml") and hub and not hub.feeds:
        data.pop("hub", None)
        data.pop("coordinator", None)
    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """
    Handle options update for a config entry.

    :param hass: The Home Assistant instance.
    :type hass: HomeAssistant
    :param entry: The configuration entry being updated.
    :type entry: ConfigEntry
    """
    hass.config_entries.async_schedule_reload(entry.entry_id)
