"""PodcastHubEntity class."""

from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import PodcastHubCoordinator


class PodcastHubEntity(CoordinatorEntity[PodcastHubCoordinator]):
    """PodcastHubEntity class."""

    def __init__(self, coordinator: PodcastHubCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
