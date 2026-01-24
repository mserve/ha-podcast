"""Models for podcast feeds and episodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime


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
    last_update: datetime | None = None


class PodcastHub:
    """Container for configured podcast feeds."""

    def __init__(self, feeds: Iterable[PodcastFeed]) -> None:
        """Initialize the hub with feeds keyed by feed_id."""
        self.feeds: dict[str, PodcastFeed] = {feed.feed_id: feed for feed in feeds}

    def get_feed(self, feed_id: str) -> PodcastFeed | None:
        """Return a feed by ID if configured."""
        return self.feeds.get(feed_id)
