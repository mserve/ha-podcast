"""DataUpdateCoordinator for podcast_hub."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import async_timeout
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import EVENT_NEW_EPISODE, LOGGER
from .podcast_hub import PodcastFeed, PodcastHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class PodcastHubCoordinator(DataUpdateCoordinator[PodcastHub]):
    """
    Coordinator for managing podcast feeds.

    This class handles the updating of podcast feeds and their episodes.

    Attributes
    ----------
    hub : PodcastHub
        The main hub for managing podcast feeds.

    Methods
    -------
    _async_update_data() -> PodcastHub
        Updates all podcast feeds asynchronously.
    _async_update_feed(feed: PodcastFeed) -> None
        Updates a single podcast feed.
    _async_fetch(url: str) -> bytes
        Fetches data from the given URL.
    _build_episodes(entries: list[FeedParserDict], max_episodes: int) -> list[Episode]
        Builds a list of episodes from feed entries.
    _entry_to_episode(entry: FeedParserDict) -> Episode | None
        Converts a feed entry to an Episode object.
    _entry_audio_url(entry: FeedParserDict) -> str | None
        Extracts the audio URL from a feed entry.
    _entry_published(entry: FeedParserDict) -> datetime | None
        Parses the published date from a feed entry.

    """

    def __init__(
        self, hass: HomeAssistant, hub: PodcastHub, update_interval: int = 5
    ) -> None:
        """
        Initialize the PodcastHubCoordinator.

        Initialies with Home Assistant instance, hub,
        and update interval.

        Parameters
        ----------
        hass : HomeAssistant
            The Home Assistant instance.
        hub : PodcastHub
            The podcast hub containing feeds.
        update_interval : int
            The update interval in minutes.

        """
        super().__init__(
            hass,
            LOGGER,
            name="podcast_hub",
            update_interval=timedelta(minutes=update_interval),
            always_update=True,
        )
        self.hub = hub
        self._known_guids: dict[str, set[str]] = {}
        self._force_refresh = False

    async def _async_update_data(self) -> dict[str, PodcastFeed]:
        """
        Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        LOGGER.debug(
            "Starting podcast feed refresh check for %d feeds", len(self.hub.feeds)
        )
        try:
            # handled by the data update coordinator.
            async with async_timeout.timeout(60):
                # This will run updates concurrently but is not Home Assistant parallel
                # safe
                return await self.hub.fetch_all_feeds(force_refresh=self._force_refresh)
        except Exception as err:
            msg = f"Error fetching podcast feeds: {err}"
            raise UpdateFailed(msg) from err

    async def async_force_refresh(self) -> None:
        """Force a refresh of all feeds regardless of schedule."""
        self._force_refresh = True
        try:
            await self.async_refresh()
        finally:
            self._force_refresh = False

    def _async_refresh_finished(self) -> None:
        """Handle post-refresh tasks."""
        super()._async_refresh_finished()
        LOGGER.debug("Finished refreshing podcast feeds; checking for new episodes")
        for feed in self.hub.feeds.values():
            self._fire_new_episode_events(feed)

    def _fire_new_episode_events(self, feed: PodcastFeed) -> None:
        current_guids = {episode.guid for episode in feed.episodes}
        previous_guids = self._known_guids.get(feed.feed_id)
        self._known_guids[feed.feed_id] = current_guids
        if previous_guids is None:
            return
        new_guids = current_guids - previous_guids
        if not new_guids:
            return
        feed_title = feed.title or feed.name
        for episode in feed.episodes:
            if episode.guid not in new_guids:
                continue
            LOGGER.debug(
                "Firing new episode event for %s (%s): %s",
                feed.name,
                feed.feed_id,
                episode.guid,
            )
            self.hass.bus.async_fire(
                EVENT_NEW_EPISODE,
                {
                    "feed_id": feed.feed_id,
                    "feed_title": feed_title,
                    "episode": episode.as_dict(),
                },
            )
