"""Constants for podcast_hub."""

from __future__ import annotations

from logging import Logger, getLogger

from homeassistant.const import Platform

LOGGER: Logger = getLogger(__package__)

DOMAIN = "podcast_hub"

CONF_PODCASTS = "podcasts"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_MAX_EPISODES = "max_episodes"
CONF_ID = "id"
CONF_NAME = "name"
CONF_URL = "url"

DEFAULT_UPDATE_INTERVAL = 15
DEFAULT_MAX_EPISODES = 50
REQUEST_TIMEOUT = 20

# PLATFORMS = ["sensor", "media_source"]  # noqa: ERA001
PLATFORMS: list[Platform] = [Platform.SENSOR]
SERVICE_RELOAD = "reload_sources"

MEDIA_CONTENT_ID_PREFIX = f"{DOMAIN}://"
