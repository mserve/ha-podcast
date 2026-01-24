"""DataUpdateCoordinator for podcast_hub."""

from __future__ import annotations

import asyncio
import calendar
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import async_timeout
import feedparser
from feedparser import FeedParserDict
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import EVENT_NEW_EPISODE, LOGGER, REQUEST_TIMEOUT
from .podcast_hub import Episode, PodcastFeed, PodcastHub

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
        self, hass: HomeAssistant, hub: PodcastHub, update_interval: int
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
        )
        self.hub = hub
        self._known_guids: dict[str, set[str]] = {}

    async def _async_update_data(self) -> PodcastHub:
        tasks = [self._async_update_feed(feed) for feed in self.hub.feeds.values()]
        await asyncio.gather(*tasks)
        return self.hub

    async def _async_update_feed(self, feed: PodcastFeed) -> None:
        now = datetime.now(UTC)
        if feed.update_interval and feed.last_update:
            min_interval = timedelta(minutes=feed.update_interval)
            if now - feed.last_update < min_interval:
                return
        try:
            data = await self._async_fetch(feed.url)
            parsed = await self.hass.async_add_executor_job(feedparser.parse, data)
            feed.title = parsed.feed.title or feed.name  # pyright: ignore[reportAttributeAccessIssue]
            feed.image_url = self._feed_image_url(parsed)
            feed.episodes = self._build_episodes(parsed.entries, feed.max_episodes)
            self._fire_new_episode_events(feed)
            feed.last_error = None
        except (TimeoutError, OSError, ValueError) as err:
            feed.last_error = str(err)
            LOGGER.warning("Failed to update feed %s: %s", feed.feed_id, err)
        finally:
            feed.last_update = now

    async def _async_fetch(self, url: str) -> bytes:
        session = async_get_clientsession(self.hass)
        async with async_timeout.timeout(REQUEST_TIMEOUT), session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()

    def _build_episodes(
        self, entries: list[FeedParserDict], max_episodes: int
    ) -> list[Episode]:
        items: list[Episode] = []
        for entry in entries:
            episode = self._entry_to_episode(entry)
            if episode:
                items.append(episode)
            if len(items) >= max_episodes:
                break
        return items

    def _entry_to_episode(self, entry: FeedParserDict) -> Episode | None:
        guid = entry.id or entry.guid or entry.link
        if not guid:
            return None
        title = entry.title or "Untitled"
        LOGGER.debug("Parsed episode: %s [%s]", title, guid)
        url = self._entry_audio_url(entry)
        if not url:
            LOGGER.warning(
                "No audio URL found for episode: %s - check if this is a proper "
                "feed url",
                title,
            )
            url = entry.link or ""
        if not url:
            return None
        published = self._entry_published(entry)
        summary = entry.summary or entry.description
        return Episode(
            guid=guid,  # pyright: ignore[reportArgumentType]
            title=title,  # pyright: ignore[reportArgumentType]
            published=published,
            url=url,  # pyright: ignore[reportArgumentType]
            image_url=self._entry_image_url(entry),
            summary=summary,  # pyright: ignore[reportArgumentType]
        )

    def _entry_audio_url(self, entry: FeedParserDict) -> str | None:
        for enclosure in entry.enclosures or []:
            href = enclosure.href
            if href:
                return href  # pyright: ignore[reportReturnType]
        LOGGER.debug("No audio enclosure found for entry: %s", entry)
        return None

    def _entry_published(self, entry: FeedParserDict) -> datetime | None:
        parsed = entry.published_parsed or entry.updated_parsed
        if not parsed:
            return None
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)  # pyright: ignore[reportArgumentType]

    def _feed_image_url(self, parsed: FeedParserDict) -> str | None:
        image = parsed.feed.get("image", {}) if parsed.feed else {}
        if isinstance(image, dict):
            href = image.get("href") or image.get("url")
            if href:
                return href
        itunes_image = parsed.feed.get("itunes_image") if parsed.feed else None
        if isinstance(itunes_image, dict):
            href = itunes_image.get("href")
            if href:
                return href
        return None

    def _entry_image_url(self, entry: FeedParserDict) -> str | None:
        image = entry.get("image")
        if isinstance(image, dict):
            href = image.get("href") or image.get("url")
            if href:
                return href
        itunes_image = entry.get("itunes_image")
        if isinstance(itunes_image, dict):
            href = itunes_image.get("href")
            if href:
                return href
        media_thumbnail = entry.get("media_thumbnail")
        if isinstance(media_thumbnail, list) and media_thumbnail:
            url = media_thumbnail[0].get("url")
            if url:
                return url
        return None

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
            self.hass.bus.async_fire(
                EVENT_NEW_EPISODE,
                {
                    "feed_id": feed.feed_id,
                    "feed_title": feed_title,
                    "episode": episode.as_dict(),
                },
            )
