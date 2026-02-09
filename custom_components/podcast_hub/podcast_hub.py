"""Models for podcast feeds and episodes."""

from __future__ import annotations

import asyncio
import calendar
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

import async_timeout
import feedparser
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import dt as dt_util

from .const import (
    DATA_DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    REQUEST_TIMEOUT,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import time

    from feedparser import FeedParserDict
    from homeassistant.core import HomeAssistant


@dataclass(slots=True)
class Episode:
    """Representation of a single podcast episode."""

    guid: str
    title: str
    published: datetime | None
    url: str
    image_url: str | None = None
    summary: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        """Return a JSON-serializable representation of the episode."""
        return {
            "guid": self.guid,
            "title": self.title,
            "published": self.published.isoformat() if self.published else None,
            "url": self.url,
            "image_url": self.image_url,
            "summary": self.summary,
        }


@dataclass(slots=True)
class PodcastFeed:
    """Configuration and state for a podcast feed."""

    feed_id: str
    name: str
    url: str
    max_episodes: int
    title: str | None = None
    image_url: str | None = None
    episodes: list[Episode] = field(default_factory=list)
    last_error: str | None = None
    update_interval: int | None = None
    refresh_times: list[time] = field(default_factory=list)
    last_update: datetime | None = None


class PodcastHub:
    """Container for configured podcast feeds."""

    def __init__(self, hass: HomeAssistant, feeds: Iterable[PodcastFeed]) -> None:
        """Initialize the hub with feeds keyed by feed_id."""
        self.hass = hass
        self.feeds: dict[str, PodcastFeed] = {feed.feed_id: feed for feed in feeds}

    def get_feed(self, feed_id: str) -> PodcastFeed | None:
        """Return a feed by ID if configured."""
        return self.feeds.get(feed_id)

    def add_feed(self, feed: PodcastFeed) -> None:
        """Add a new feed to the hub."""
        self.feeds[feed.feed_id] = feed

    def remove_feed(self, feed_id: str) -> None:
        """Remove a feed from the hub by ID."""
        self.feeds.pop(feed_id, None)

    async def fetch_all_feeds(
        self, *, force_refresh: bool = False
    ) -> dict[str, PodcastFeed]:
        """Fetch updates for all feeds concurrently."""
        tasks = [
            self.fetch_feed(feed, force_refresh=force_refresh)
            for feed in self.feeds.values()
        ]
        await asyncio.gather(*tasks)
        return self.feeds

    async def fetch_feed(
        self, feed: PodcastFeed, *, force_refresh: bool = False
    ) -> PodcastFeed:
        """Fetch updates for a single feed when refresh conditions are met."""
        now_utc = dt_util.utcnow()
        now_local = dt_util.as_local(now_utc)
        default_interval = self._get_default_interval()
        effective_interval = feed.update_interval or default_interval
        if force_refresh:
            LOGGER.info("Force refresh for %s (%s)", feed.name, feed.feed_id)
        elif not feed.last_update:
            LOGGER.info("Initial refresh for %s (%s)", feed.name, feed.feed_id)
        elif feed.refresh_times and self._is_scheduled_refresh_due(feed, now_local):
            LOGGER.info("Scheduled refresh due for %s (%s)", feed.name, feed.feed_id)
        elif now_utc - feed.last_update > timedelta(minutes=effective_interval):
            LOGGER.info(
                "Regular feed update due for %s (%s) - update interval %d minutes, last update was %s, %d minutes ago",  # noqa: E501
                feed.name,
                feed.feed_id,
                effective_interval,
                feed.last_update,
                (now_utc - feed.last_update).total_seconds() / 60,
            )
        else:
            LOGGER.debug(
                "NO feed update for %s (%s) required!",
                feed.name,
                feed.feed_id,
            )
            return feed
        try:
            LOGGER.debug(
                "Fetching feed for %s (%s) from %s",
                feed.name,
                feed.feed_id,
                feed.url,
            )
            data = await self._async_fetch(feed.url)
            LOGGER.debug(
                "Finished fetching feed for %s (%s) (%d bytes)",
                feed.name,
                feed.feed_id,
                len(data),
            )
            parsed = await self.hass.async_add_executor_job(feedparser.parse, data)
            feed.title = parsed.feed.title or feed.name  # pyright: ignore[reportAttributeAccessIssue]
            feed.image_url = self._feed_image_url(parsed)
            feed.episodes = self._build_episodes(
                parsed.entries, feed.max_episodes, feed
            )
            feed.last_error = None
        except (TimeoutError, OSError, ValueError) as err:
            feed.last_error = str(err)
            LOGGER.warning(
                "Failed to update feed %s (%s): %s", feed.name, feed.feed_id, err
            )
        finally:
            feed.last_update = now_utc
        return feed

    async def _async_fetch(self, url: str) -> bytes:
        session = async_get_clientsession(self.hass)
        async with async_timeout.timeout(REQUEST_TIMEOUT), session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()

    def _get_default_interval(self) -> int:
        """Return the default update from config."""
        return self.hass.data.get(DOMAIN, {}).get(
            DATA_DEFAULT_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

    def _build_episodes(
        self, entries: list[FeedParserDict], max_episodes: int, feed: PodcastFeed
    ) -> list[Episode]:
        """Convert feed entries into episode objects within the limit."""
        items: list[Episode] = []
        for entry in entries:
            episode = self._entry_to_episode(entry, feed)
            if episode:
                items.append(episode)
            if len(items) >= max_episodes:
                break
        return items

    def _entry_to_episode(
        self, entry: FeedParserDict, feed: PodcastFeed
    ) -> Episode | None:
        """Build an Episode from a feed entry, if it is usable."""
        guid = entry.id or entry.guid or entry.link
        if not guid:
            return None
        title = entry.title or "Untitled"
        LOGGER.debug(
            "Parsed episode for %s (%s): %s [%s]",
            feed.name,
            feed.feed_id,
            title,
            guid,
        )
        url = self._entry_audio_url(entry, feed)
        if not url:
            LOGGER.warning(
                "No audio URL found for %s (%s) episode: %s - check if this is a "
                "proper feed url",
                feed.name,
                feed.feed_id,
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

    def _entry_audio_url(self, entry: FeedParserDict, feed: PodcastFeed) -> str | None:
        """Find the best audio enclosure URL for a feed entry."""
        for enclosure in entry.enclosures or []:
            href = enclosure.href
            if href:
                return href  # pyright: ignore[reportReturnType]
        LOGGER.debug(
            "No audio enclosure found for %s (%s) entry: %s",
            feed.name,
            feed.feed_id,
            entry,
        )
        return None

    def _entry_published(self, entry: FeedParserDict) -> datetime | None:
        """Return the published datetime from an entry if available."""
        parsed = entry.published_parsed or entry.updated_parsed
        if not parsed:
            return None
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)  # pyright: ignore[reportArgumentType]

    def _feed_image_url(self, parsed: FeedParserDict) -> str | None:
        """Extract the feed-level image URL from parsed metadata."""
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
        """Extract the entry-level image URL from parsed metadata."""
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

    def _is_scheduled_refresh_due(self, feed: PodcastFeed, now_local: datetime) -> bool:
        """Check whether a scheduled refresh time is due for a feed."""
        if not feed.last_update:
            LOGGER.debug(
                "No last update for %s (%s) - scheduled refresh is due",
                feed.name,
                feed.feed_id,
            )
            return True
        last_local = dt_util.as_local(feed.last_update)
        next_refresh = self._next_scheduled_time(last_local, feed.refresh_times)
        if now_local >= next_refresh:
            LOGGER.debug(
                "Next scheduled refresh for %s (%s) at %s - now it's %s",
                feed.name,
                feed.feed_id,
                next_refresh,
                now_local,
            )
            return True
        return False

    def _next_scheduled_time(
        self, last_local: datetime, refresh_times: list[time]
    ) -> datetime:
        """Return the next scheduled refresh time after the last update."""
        for refresh_time in refresh_times:
            candidate = datetime.combine(
                last_local.date(),
                refresh_time,
                tzinfo=last_local.tzinfo,
            )
            if candidate > last_local:
                return candidate
        next_day = last_local.date() + timedelta(days=1)
        return datetime.combine(
            next_day,
            refresh_times[0],
            tzinfo=last_local.tzinfo,
        )
