# Podcast Hub

Podcast Hub is a Home Assistant custom integration that lets you manage podcast
feeds (RSS/Atom) from `configuration.yaml`. It exposes each feed as a sensor,
provides a Media Source browser for playback, and offers a reload service for
manual refreshes.

## Why this exists

- Centralize podcast feed definitions in Home Assistant
- Browse episodes via Media Source and play them on media players
- Use sensor attributes in automations (latest episode, episode list, etc.)

## Configuration

Add the integration to your `configuration.yaml`:

```yaml
podcast_hub:
  update_interval: 15  # minutes, optional
  podcasts:
    - id: lage_der_nation
      name: Lage der Nation
      url: https://example.com/feed.xml
      max_episodes: 50
```

### Options

- `update_interval` (int, minutes, optional): How often to refresh all feeds.
- `podcasts` (list, required): Podcast feed definitions.
  - `id` (str, required): Unique feed id (used in entity ids and media paths).
  - `name` (str, required): Friendly name shown in UI.
  - `url` (str, required): RSS/Atom feed URL.
  - `max_episodes` (int, optional): Maximum number of episodes to keep per feed.
  - `update_interval` (int, optional): Per-feed override (minutes).

## Media browsing and playback

The Media Source browser lists your feeds and episodes. When you play an episode,
Home Assistant resolves the URL from the feed and sends it to the selected media
player.

Important: Make sure your feed entries actually contain audio enclosures.
If a feed points to non-audio content (or no enclosure at all), playback may fail
with a wrong media type error. Check the Home Assistant log for details about
what URL and content type were resolved.

## Services

- `podcast_hub.reload_sources`: Trigger a refresh of all configured feeds.

## Entity overview

- One sensor per feed: `sensor.podcast_<feed_id>`
  - State: number of episodes
  - Attributes: feed metadata and episode list (limited by `max_episodes`)
