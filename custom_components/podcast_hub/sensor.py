"""Sensor platform for podcast_hub."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription

from .const import DOMAIN
from .entity import PodcastHubEntity

if TYPE_CHECKING:
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import PodcastHubCoordinator
    from .podcast_hub import Episode, PodcastFeed

ENTITY_DESCRIPTIONS = (
    SensorEntityDescription(
        key="podcast_hub",
        name="Integration Sensor",
        icon="mdi:format-quote-close",
    ),
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],  # noqa: ARG001
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,  # noqa: ANN001, ARG001
) -> None:
    """
    Set up the Podcast Hub sensor platform.

    Parameters
    ----------
    hass : HomeAssistant
        Home Assistant instance.
    config : dict
        Platform configuration.
    async_add_entities : AddEntitiesCallback
        Callback to add entities to Home Assistant.
    discovery_info
        Discovery information (unused).

    """
    data = hass.data.get(DOMAIN)
    if not data:
        return
    coordinator = data["coordinator"]
    hub = data["hub"]
    entities = [
        PodcastFeedSensor(coordinator, feed.feed_id) for feed in hub.feeds.values()
    ]
    async_add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,  # noqa: ANN001
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Podcast Hub sensors from a config entry."""
    data = hass.data.get(DOMAIN)
    if not data:
        return
    coordinator = data["coordinator"]
    feed_id = entry.data.get("id")
    if not feed_id:
        return
    async_add_entities([PodcastFeedSensor(coordinator, feed_id)])


class PodcastFeedSensor(PodcastHubEntity, SensorEntity):
    """
    Sensor entity for a podcast feed.

    Displays the episode count as state and provides feed metadata and episode
    list in attributes.
    """

    def __init__(self, coordinator: PodcastHubCoordinator, feed_id: str) -> None:
        """
        Initialize a podcast feed sensor.

        Parameters
        ----------
        coordinator : PodcastHubCoordinator
            The data coordinator.
        feed_id : str
            The feed identifier.

        """
        super().__init__(coordinator)
        self._feed_id = feed_id
        feed = self._get_feed()
        self._attr_name = feed.name if feed else feed_id
        self._attr_unique_id = f"{DOMAIN}_{feed_id}"
        self._attr_icon = "mdi:podcast"
        self.entity_id = f"sensor.podcast_{feed_id}"

    def _get_feed(self) -> PodcastFeed | None:
        return self.coordinator.hub.get_feed(self._feed_id)

    @property
    def state(self) -> int:
        """
        Return the number of episodes in the feed.

        Returns
        -------
        int
            The episode count for this feed, or 0 if feed is not found.

        """
        feed = self._get_feed()
        return len(feed.episodes) if feed else 0

    @property
    def extra_state_attributes(self) -> dict:
        """
        Return extra state attributes for the sensor.

        Returns
        -------
        dict
            A dictionary containing feed metadata, episode list, and any errors.

        """
        feed = self._get_feed()
        if not feed:
            return {}

        latest = feed.episodes[0] if feed.episodes else None
        attrs = {
            "feed_id": feed.feed_id,
            "title": feed.title or feed.name,
            "feed_url": feed.url,
            "image_url": feed.image_url,
            "latest_episode_title": latest.title if latest else None,
            "latest_episode_guid": latest.guid if latest else None,
            "latest_episode_published": (
                _format_dt(latest.published) if latest else None
            ),
            "latest_episode_url": latest.url if latest else None,
            "last_update": _format_dt(feed.last_update),
            "episodes": [_episode_to_dict(ep) for ep in feed.episodes],
        }
        if feed.last_error:
            attrs["last_error"] = feed.last_error
        return attrs


def _format_dt(value: datetime | None) -> str | None:
    if not value:
        return None
    return value.isoformat()


def _episode_to_dict(episode: Episode) -> dict:
    return episode.as_dict()
