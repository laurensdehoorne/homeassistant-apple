# Apple Music for Home Assistant

Search Apple Music and play it on your Sonos speakers from Home Assistant: from
the media browser, from automations and scripts, or by voice through Assist.

Sonos streams the music itself, with the Apple Music account linked in the Sonos
app. Home Assistant only tells the speakers what to play, so you get the same
quality as in the Sonos app, lossless included.

## What you get

- **Apple Music in the Sonos media browser**: the top songs, albums and playlists
  of your country, albums, artists, and a search box.
- **`apple_music.play`**: play the best match for a song, an album or the top songs
  of an artist, or any Apple Music song, album or playlist link. Replace the
  queue, play now, play next or add to the queue.
- **`apple_music.search`**: search the catalog and get the matches back, for
  scripts and AI voice assistants.

## Requirements

- Home Assistant 2026.10 or newer with the [Sonos integration](https://www.home-assistant.io/integrations/sonos/).
- An Apple Music subscription, linked to your Sonos system in the Sonos app
  (**Settings → Services & Voice**).

No Apple Developer account or password is needed. Searching uses Apple's public
iTunes Search API, the charts come from Apple's public RSS feeds.

## Installation

### HACS

1. In HACS, open the menu → **Custom repositories**, add
   `https://github.com/laurensdehoorne/homeassistant-apple` as an **Integration**.
2. Download **Apple Music** and restart Home Assistant.

### Manually

Copy `custom_components/apple_music` to the `custom_components` folder of your
Home Assistant configuration and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Apple Music**, and pick the
country of your Apple Music account. The country decides the catalog and charts.

## Usage

### Media browser

Open a Sonos speaker's media browser, or **Media** in the sidebar with a Sonos
speaker selected, and choose **Apple Music**.

### Actions

Play a song, replacing the queue:

```yaml
action: apple_music.play
target:
  entity_id: media_player.keuken
data:
  query: Yellow Coldplay
```

Play the 20 most popular songs of an artist:

```yaml
action: apple_music.play
target:
  area_id: woonkamer
data:
  query: Stromae
  media_type: artist
  limit: 20
```

Add an album to the end of the queue:

```yaml
action: apple_music.play
target:
  entity_id: media_player.keuken
data:
  query: Parachutes
  media_type: album
  enqueue: add
```

Play a playlist, from **Share → Copy link** in the Music app. Your own playlists
work once you share them:

```yaml
action: apple_music.play
target:
  entity_id: media_player.keuken
data:
  url: https://music.apple.com/be/playlist/todays-hits/pl.f4d106fed2bd41149aaacabb233eb5eb
```

Search:

```yaml
action: apple_music.search
data:
  query: Stromae
  media_type: album
  limit: 5
response_variable: results
```

Every match has a `name`, `artist`, `album`, `url`, `artwork_url` and a
`media_content_id` you can pass to `media_player.play_media` on a Sonos speaker.

### Voice

Expose this script to Assist to let an AI conversation agent play music:

```yaml
alias: Play Apple Music
description: >-
  Plays a song, an album or the most popular songs of an artist from Apple Music
  on a Sonos speaker.
fields:
  query:
    description: The song, album or artist to play.
    required: true
    selector:
      text:
  media_type:
    description: song, album or artist.
    selector:
      select:
        options: [song, album, artist]
  speaker:
    description: The Sonos speaker to play on.
    required: true
    selector:
      entity:
        integration: sonos
        domain: media_player
sequence:
  - action: apple_music.play
    target:
      entity_id: "{{ speaker }}"
    data:
      query: "{{ query }}"
      media_type: "{{ media_type | default('song') }}"
```

## Limitations

- Only Sonos speakers play Apple Music links. Other speakers are refused with an
  error.
- Without an Apple Developer account there is no access to your library, so
  searching finds songs, albums and artists, not playlists. Play playlists by
  link, or save them as Sonos favorites.
- Artist radio stations are not supported, playing an artist plays their most
  popular songs.
- Apple's chart feeds go down now and then. The media browser then shows the last
  charts it loaded.

## Development

```bash
uv sync
uv run pytest
uv run ruff check . && uv run mypy custom_components tests && uv run pylint custom_components tests
```
