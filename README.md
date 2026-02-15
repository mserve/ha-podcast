# Podcast Hub

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories/)
[![Validate](https://github.com/mserve/ha-podcast/actions/workflows/validate.yml/badge.svg)](https://github.com/mserve/ha-podcast/actions/workflows/validate.yml)
[![Lint](https://github.com/mserve/ha-podcast/actions/workflows/lint.yml/badge.svg)](https://github.com/mserve/ha-podcast/actions/workflows/lint.yml)
[![Release](https://img.shields.io/github/v/release/mserve/ha-podcast)](https://github.com/mserve/ha-podcast/releases)
[![Downloads](https://img.shields.io/github/downloads/mserve/ha-podcast/total)](https://github.com/mserve/ha-podcast/releases)
[![License](https://img.shields.io/github/license/mserve/ha-podcast)](LICENSE)

Podcast Hub is a Home Assistant custom integration that lets you manage podcast
feeds (RSS/Atom) via the UI or `configuration.yaml`. It exposes each feed as a
sensor, provides a Media Source browser for playback, and offers a reload
service for manual refreshes.

## Why this exists

- Centralize podcast feed definitions in Home Assistant
- Browse episodes via Media Source and play them on media players
- Use sensor attributes in automations (latest episode, episode list, etc.)

## Installation (HACS)

1. Add `mserve/ha-podcast` as a custom repository in HACS (category: Integration).
2. Install **Podcast Hub** and restart Home Assistant.
3. Add the integration in Settings → Devices & Services → Add Integration.

## Configuration (UI)

Use the UI to add podcast feeds. You can also create a **Settings** entry to set
a global default update interval and media type for all feeds. After creating the
Settings entry, use the integration **Options** to change these defaults later
without affecting your feed entries.

Per-feed update interval is optional; if not set, the global default is used.
You can also set **Refresh times** to fetch feeds at specific local times.

## Configuration (YAML)

Add the integration to your `configuration.yaml` if you prefer YAML:

```yaml
podcast_hub:
  update_check_interval: 5  # minutes, optional (YAML only)
  update_interval: 15  # minutes, optional
  media_type: track    # optional: track (Sonos compatible) or podcast
  podcasts:
    - id: lage_der_nation
      name: Lage der Nation
      url: https://example.com/feed.xml
      max_episodes: 50
      refresh_times:
        - "08:30"
        - "18:00"
```

### Options

- `update_check_interval` (int, minutes, optional): How often the integration checks
  if any feed has a due update or refresh. Defaults to `5` minutes and can only be configured via YAML.
  You may safely decrease this value if there are only few feed configured, the feed URL will only be
  fetched if an update or refresh is due. This only triggers the internal checks in the coordinator.
- `update_interval` (int, minutes, optional): How often to refresh all feeds.
- `media_type` (str, optional): `track` (audio/*, Sonos friendly) or `podcast`.
- `podcasts` (list, required): Podcast feed definitions.
  - `id` (str, required): Unique feed id (used in entity ids and media paths).
  - `name` (str, required): Friendly name shown in UI.
  - `url` (str, required): RSS/Atom feed URL.
  - `max_episodes` (int, optional): Maximum number of episodes to keep per feed
    (clamped to 1-500).
  - `update_interval` (int, optional): Per-feed override (minutes).
  - `refresh_times` (list, optional): Refresh at specific local times (`HH:MM`).

## Entity overview

- One sensor per feed: `sensor.podcast_<feed_id>`
  - State: number of episodes
  - Attributes: feed metadata, `feed_id`, and episode list (limited by `max_episodes`)

Tip: The included blueprints use the `feed_id` attribute so renamed entities
keep working without string parsing.

## Media browsing and playback

The Media Source browser lists your feeds and episodes. When you play an episode,
Home Assistant resolves the URL from the feed and sends it to the selected media
player.

Important: Make sure your feed entries actually contain audio enclosures.
If a feed points to non-audio content (or no enclosure at all), playback may fail
with a wrong media type error. Check the Home Assistant log for details about
what URL and content type were resolved.

## Media source alias for latest episode

You can use the immutable `latest` media source alias to always play the newest
episode. This is especially useful for scripts and automations because the URL
does not change between episodes.

Example Lovelace button using the alias:

```yaml
type: button
name: Play latest episode
icon: mdi:podcast
tap_action:
  action: call-service
  service: media_player.play_media
  target:
    entity_id: media_player.living_room
  data:
    media_content_id: media-source://podcast_hub/lage_der_nation/latest
    media_content_type: podcast
```

## Services

- `podcast_hub.reload_sources`: Trigger a refresh of all configured feeds.

## Blueprints

This integration ships blueprints for common automations and scripts.

```
blueprints/automation/podcast_hub/refresh_and_play_latest.yaml
blueprints/automation/podcast_hub/notify_on_new_episode.yaml
```

Script blueprint (takes a feed sensor and media player):

```
blueprints/script/podcast_hub/play_latest_episode.yaml
```

Note: HACS does not install blueprints automatically. Import the blueprint in
Home Assistant or copy it into your `config/blueprints/automation/` or
`config/blueprints/script/` folder.

## UI example: Button to play latest episode (GUID)

Example Lovelace button that plays the latest episode of a feed when pressed:

```yaml
type: button
name: Play latest episode
icon: mdi:podcast
tap_action:
  action: call-service
  service: media_player.play_media
  target:
    entity_id: media_player.living_room
  data:
    media_content_id: >-
      {% set episodes = state_attr('sensor.podcast_lage_der_nation', 'episodes') or [] %}
      {% if episodes %}
        media-source://podcast_hub/lage_der_nation/{{ episodes[0].guid | urlencode }}
      {% else %}
        media-source://podcast_hub/lage_der_nation/none
      {% endif %}
    media_content_type: podcast
```

Note: You can use the immutable alias `media-source://podcast_hub/<feed_id>/latest`
to always play the newest episode without looking up GUIDs. This works well in
scripts and automations.

## UI example: Button to refresh feeds

Example Lovelace button that triggers a refresh of all configured feeds:

```yaml
type: button
name: Refresh podcasts
icon: mdi:refresh
tap_action:
  action: call-service
  service: podcast_hub.reload_sources
```

## Development

- Lint and format:

```
ruff check .
ruff format .
```

- Run tests:

```
pytest -q
```

- Optional: install pre-commit hooks:

```
pip install prek
prek install
```
