"""Media source integration for Podcast Hub."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote

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

from .const import (
    CONF_MEDIA_TYPE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    REQUEST_TIMEOUT,
)
from .coordinator import PodcastHubCoordinator
from .podcast_hub import PodcastHub

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .podcast_hub import Episode, PodcastFeed


PODCASTS_ROOT = "feeds"
LATEST_KEY = "latest"
ALL_KEY = "all"
EPISODE_PATH_PARTS = 2
_ICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<circle cx='32' cy='32' r='30' fill='%2303a9f4'/>"
    "<rect x='26' y='18' width='12' height='22' rx='6' fill='white'/>"
    "<path d='M20 30v4a12 12 0 0 0 24 0v-4' "
    "fill='none' stroke='white' stroke-width='4' stroke-linecap='round'/>"
    "<path d='M32 46v6' stroke='white' stroke-width='4' stroke-linecap='round'/>"
    "<path d='M24 54h16' stroke='white' stroke-width='4' "
    "stroke-linecap='round'/>"
    "</svg>"
)
MEDIA_SOURCE_ICON = f"data:image/svg+xml;utf8,{quote(_ICON_SVG)}"


async def async_get_media_source(hass: HomeAssistant) -> PodcastHubMediaSource:
    """Return the Podcast Hub media source instance."""
    data = hass.data.setdefault(DOMAIN, {})
    hub = data.get("hub")
    coordinator = data.get("coordinator")
    if not hub or not coordinator:
        hub = PodcastHub([])
        coordinator = PodcastHubCoordinator(hass, hub, DEFAULT_UPDATE_INTERVAL)
        data["hub"] = hub
        data["coordinator"] = coordinator
    return PodcastHubMediaSource(hass, hub, coordinator)


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
        path = _normalize_identifier(item.identifier)
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
        if not item.identifier:
            msg = "No media content identifier provided"
            raise MediaSourceError(msg)
        parsed = _parse_episode_id(item.identifier)
        if not parsed.feed_id or not parsed.item_id:
            msg = f"Invalid media content id {item.media_content_id}"
            raise MediaSourceError(msg)

        feed = self.hub.get_feed(parsed.feed_id)
        if not feed:
            msg = "Podcast feed not found"
            raise MediaSourceError(msg)
        if parsed.item_id == LATEST_KEY:
            episode = feed.episodes[0] if feed.episodes else None
        else:
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

        return PlayMedia(url=final_url, mime_type=mime_type)

    def _browse_root(self) -> BrowseMediaSource:
        return self._browse_podcasts()

    def _browse_podcasts(self) -> BrowseMediaSource:
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=_join_identifier(feed.feed_id),
                media_class=MediaClass.DIRECTORY,
                media_content_type="directory",
                title=feed.title or feed.name,
                can_play=False,
                can_expand=True,
                thumbnail=feed.image_url,
            )
            for feed in self.hub.feeds.values()
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type="directory",
            title="Podcast Hub",
            can_play=False,
            can_expand=True,
            thumbnail=MEDIA_SOURCE_ICON,
            children=children,
        )

    def _browse_podcast(self, feed_id: str) -> BrowseMediaSource:
        feed = self.hub.get_feed(feed_id)
        if not feed:
            msg = "Podcast feed not found"
            raise MediaSourceError(msg)

        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join_identifier(feed.feed_id),
            media_class=MediaClass.DIRECTORY,
            media_content_type="directory",
            title=feed.title or feed.name,
            can_play=False,
            can_expand=True,
            thumbnail=feed.image_url,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_join_identifier(feed.feed_id, LATEST_KEY),
                    media_class=MediaClass.DIRECTORY,
                    media_content_type="directory",
                    title="Latest",
                    can_play=False,
                    can_expand=True,
                    thumbnail=feed.image_url,
                ),
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_join_identifier(feed.feed_id, ALL_KEY),
                    media_class=MediaClass.DIRECTORY,
                    media_content_type="directory",
                    title="All Episodes",
                    can_play=False,
                    can_expand=True,
                    thumbnail=feed.image_url,
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

        media_type = self._episode_media_type()
        if mode == LATEST_KEY and episodes:
            children = [_latest_to_browse_item(feed, episodes[0], media_type)]
        else:
            children = [
                _episode_to_browse_item(feed, episode, media_type)
                for episode in episodes
            ]
        title = "Latest" if mode == LATEST_KEY else "All Episodes"
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join_identifier(feed.feed_id, mode),
            media_class=MediaClass.DIRECTORY,
            media_content_type="directory",
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
        )

    def _episode_media_type(self) -> str:
        settings = self.hass.data.get(DOMAIN, {}).get("settings_entry")
        configured = None
        if settings:
            source = settings.options or settings.data
            configured = source.get(CONF_MEDIA_TYPE)
        if not configured:
            configured = self.hass.data.get(DOMAIN, {}).get("media_type")
        if configured == "podcast":
            return MediaType.PODCAST
        return "audio/mpeg"


def _episode_to_browse_item(
    feed: PodcastFeed, episode: Episode, media_type: str
) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=_join_identifier(feed.feed_id, episode.guid),
        media_class=MediaClass.PODCAST,
        media_content_type=media_type,
        title=episode.title,
        can_play=True,
        can_expand=False,
        thumbnail=episode.image_url or feed.image_url,
    )


def _latest_to_browse_item(
    feed: PodcastFeed, episode: Episode, media_type: str
) -> BrowseMediaSource:
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=_join_identifier(feed.feed_id, LATEST_KEY),
        media_class=MediaClass.PODCAST,
        media_content_type=media_type,
        title=episode.title,
        can_play=True,
        can_expand=False,
        thumbnail=episode.image_url or feed.image_url,
    )


def _normalize_identifier(identifier: str | None) -> str:
    """Return a normalized identifier path for media source handling."""
    return identifier or ""


def _parse_episode_id(identifier: str) -> ParsedContentId:
    path = _normalize_identifier(identifier)
    parts = [part for part in path.split("/") if part]
    if len(parts) == EPISODE_PATH_PARTS:
        feed_id, item_id = parts
    elif len(parts) == EPISODE_PATH_PARTS + 1 and parts[0] == PODCASTS_ROOT:
        feed_id, item_id = parts[1], parts[2]
    else:
        return ParsedContentId(None, None)
    feed_id = unquote(feed_id)
    item_id = unquote(item_id)
    return ParsedContentId(feed_id, item_id)


def _join_identifier(*parts: str) -> str:
    return "/".join(quote(part, safe="") for part in parts)


def _find_episode(feed: PodcastFeed, guid: str) -> Episode | None:
    for episode in feed.episodes:
        if episode.guid == guid:
            return episode
    return None
