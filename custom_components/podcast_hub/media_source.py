"""
Media source integration for Podcast Hub.

This module provides functionality to browse and resolve media
for podcast feeds, including handling episodes and their metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import unquote

import async_timeout
from homeassistant.components.media_player.const import MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceError,
    MediaSourceItem,
    PlayMedia,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, LOGGER, MEDIA_CONTENT_ID_PREFIX, REQUEST_TIMEOUT

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import PodcastHubCoordinator
    from .podcast_hub import Episode, PodcastFeed, PodcastHub


PODCASTS_ROOT = "feeds"
LATEST_KEY = "latest"
ALL_KEY = "all"
EPISODE_PATH_PARTS = 2


async def async_get_media_source(hass: HomeAssistant) -> PodcastHubMediaSource:
    """Return the Podcast Hub media source instance."""
    data = hass.data[DOMAIN]
    return PodcastHubMediaSource(hass, data["hub"], data["coordinator"])


@dataclass(slots=True)
class ParsedContentId:
    """Parsed components of a media_content_id."""

    feed_id: str | None
    item_id: str | None


class PodcastHubMediaSource(MediaSource):
    """Media Source implementation for podcast browsing and playback."""

    name = "Podcast Hub"

    def __init__(
        self, hass: HomeAssistant, hub: PodcastHub, coordinator: PodcastHubCoordinator
    ) -> None:
        """Initialize the media source with hub data and coordinator."""
        super().__init__(DOMAIN)
        self.hass = hass
        self.hub = hub
        self.coordinator = coordinator

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Return a browse tree for the requested media content."""
        path = _strip_prefix(item.media_content_id)
        if not path or path == "/":
            return self._browse_root()

        parts = [part for part in path.split("/") if part]
        if parts == [PODCASTS_ROOT]:
            return self._browse_podcasts()

        if len(parts) == 1:
            return self._browse_podcast(parts[0])

        if len(parts) == EPISODE_PATH_PARTS and parts[1] in (LATEST_KEY, ALL_KEY):
            return self._browse_episode_list(parts[0], parts[1])

        msg = f"Unknown media path: {path}"
        raise MediaSourceError(msg)

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a media_content_id into a playable URL."""
        if item.media_content_id is None:
            msg = "No media content id provided"
            raise MediaSourceError(msg)
        parsed = _parse_episode_id(item.media_content_id)
        if not parsed.feed_id or not parsed.item_id:
            msg = "Invalid media content id"
            raise MediaSourceError(msg)

        feed = self.hub.get_feed(parsed.feed_id)
        if not feed:
            msg = "Podcast feed not found"
            raise MediaSourceError(msg)
        episode = _find_episode(feed, parsed.item_id)
        if not episode:
            msg = "Podcast episode not found"
            raise MediaSourceError(msg)

        session = async_get_clientsession(self.hass)
        try:
            async with (
                async_timeout.timeout(REQUEST_TIMEOUT),
                session.get(episode.url, allow_redirects=True) as resp,
            ):
                resp.raise_for_status()
                final_url = str(resp.url)
                content_type = resp.headers.get("Content-Type", "audio/mpeg")
                mime_type = content_type.split(";")[0]
        except Exception as err:
            LOGGER.warning("Failed to resolve media for %s: %s", episode.guid, err)
            msg = "Unable to resolve media"
            raise MediaSourceError(msg) from err

        return PlayMedia(final_url, mime_type)

    def _browse_root(self) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            media_class=MediaClass.DIRECTORY,
            media_content_id=MEDIA_CONTENT_ID_PREFIX,
            media_content_type=MediaType.EPISODE,
            title="Podcast Hub",
            can_play=False,
            can_expand=True,
            identifier=None,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_join_path(PODCASTS_ROOT),
                    media_content_type=MediaType.EPISODE,
                    title="Podcasts",
                    can_play=False,
                    can_expand=True,
                    identifier=None,
                )
            ],
        )

    def _browse_podcasts(self) -> BrowseMediaSource:
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                media_class=MediaClass.DIRECTORY,
                media_content_id=_join_path(feed.feed_id),
                title=feed.title or feed.name,
                can_play=False,
                can_expand=True,
                identifier=None,
            )
            for feed in self.hub.feeds.values()
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            media_class=MediaClass.DIRECTORY,
            media_content_id=_join_path(PODCASTS_ROOT),
            title="Podcasts",
            can_play=False,
            can_expand=True,
            children=children,
            identifier=None,
        )

    def _browse_podcast(self, feed_id: str) -> BrowseMediaSource:
        feed = self.hub.get_feed(feed_id)
        if not feed:
            msg = "Podcast feed not found"
            raise MediaSourceError(msg)

        return BrowseMediaSource(
            domain=DOMAIN,
            media_class=MediaClass.DIRECTORY,
            media_content_id=_join_path(feed.feed_id),
            title=feed.title or feed.name,
            can_play=False,
            can_expand=True,
            identifier=None,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_join_path(feed.feed_id, LATEST_KEY),
                    title="Latest",
                    can_play=False,
                    can_expand=True,
                    identifier=None,
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=_join_path(feed.feed_id, ALL_KEY),
                    title="All Episodes",
                    can_play=False,
                    can_expand=True,
                    identifier=None,
                ),
            ],
        )

    def _browse_episode_list(self, feed_id: str, mode: str) -> BrowseMediaSource:
        feed = self.hub.get_feed(feed_id)
        if not feed:
            msg = "Podcast feed not found"
            raise MediaSourceError(msg)

        episodes = feed.episodes
        if mode == LATEST_KEY:
            episodes = episodes[:1]

        children = [_episode_to_browse_item(feed, episode) for episode in episodes]
        title = "Latest" if mode == LATEST_KEY else "All Episodes"
        return BrowseMediaSource(
            domain=DOMAIN,
            media_class=MediaClass.DIRECTORY,
            media_content_id=_join_path(feed.feed_id, mode),
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            identifier=None,
        )


def _episode_to_browse_item(feed: PodcastFeed, episode: Episode) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        media_class=MediaClass.PODCAST,
        media_content_id=_join_path(feed.feed_id, episode.guid),
        media_content_type=MediaType.PODCAST,
        title=episode.title,
        can_play=True,
        can_expand=False,
        identifier=None,
    )


def _strip_prefix(content_id: str | None) -> str:
    if not content_id:
        return ""
    if content_id.startswith(MEDIA_CONTENT_ID_PREFIX):
        return unquote(content_id[len(MEDIA_CONTENT_ID_PREFIX) :])
    return unquote(content_id)


def _parse_episode_id(content_id: str) -> ParsedContentId:
    path = _strip_prefix(content_id)
    parts = [part for part in path.split("/") if part]
    if len(parts) != EPISODE_PATH_PARTS or parts[1] in (LATEST_KEY, ALL_KEY):
        return ParsedContentId(None, None)
    return ParsedContentId(parts[0], parts[1])


def _join_path(*parts: str) -> str:
    return MEDIA_CONTENT_ID_PREFIX + "/".join(parts)


def _find_episode(feed: PodcastFeed, guid: str) -> Episode | None:
    for episode in feed.episodes:
        if episode.guid == guid:
            return episode
    return None
