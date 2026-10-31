# Apple Music for Home Assistant

Search Apple Music and play it on your Sonos speakers from Home Assistant: from
a dashboard card, the media browser, automations and scripts, or by voice through
Assist.

Sonos streams the music itself, with the Apple Music account linked in the Sonos
app. Home Assistant only tells the speakers what to play, so you get the same
quality as in the Sonos app, lossless included.

The integration finds that account in your Sonos favorites and queues music the
way the Sonos app does. Home Assistant's own Sonos integration plays Apple Music
links with a fixed account id, which Sonos refuses with UPnP error 800 or 804
when your account has another id.

## What you get

- **An Apple Music dashboard card**: your playlists, search, the charts, albums
  and artists, the speaker or Sonos group that plays, shuffle, grouping, volume and
  a button to ask Assist, in one card.
- **Voice commands**: say "speel Oasis in de woonkamer" or "play Parachutes in the
  kitchen" to Assist. AI conversation agents get a tool to play music too.
- **Apple Music in the Sonos media browser**: the top songs and albums of your
  country, albums, artists, and a search box. Songs play right away, albums open
  to their songs.
- **`apple_music.play`**: play the best match for a song, an album or the top songs
  of an artist, or any Apple Music song, album, artist or playlist link. Replace the
  queue, play now, play next or add to the queue.
- **`apple_music.search`**: search the catalog and get the matches back, for
  scripts and AI voice assistants.

## Requirements

- Home Assistant 2026.10 or newer with the [Sonos integration](https://www.home-assistant.io/integrations/sonos/).
- An Apple Music subscription, linked to your Sonos system in the Sonos app
  (**Settings → Services & Voice**).
- At least one Apple Music song, album or playlist in your Sonos favorites. The
  integration reads the account to play with from it.

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

### Dashboard card

The integration adds the card to every dashboard, there is no resource to add.
Add a card, pick **Apple Music**, or add it in YAML:

```yaml
type: custom:apple-music-card
# Optional: the Sonos speakers to choose from, all of them by default.
entities:
  - media_player.keuken
  - media_player.woonkamer
# Optional: how high the list of songs and albums gets, 520px by default.
height: 640px
# Optional: groups to make with one tap.
groups:
  - name: Keuken + woonkamer
    entities:
      - media_player.keuken
      - media_player.woonkamer
```

The card shows what plays on the chosen speaker, with buttons to shuffle, pause and
skip, a search box, your playlists, and the top songs and albums. Tap a song to play it right away, or ⋮ to play it next,
add it to the queue or replace the queue. Playlists, albums and artists open, with
buttons to play them. Searching finds playlists too. The card remembers the speaker
per browser.

**Playlists** are the Apple Music playlists in your Sonos favorites. To add one,
give it a heart in the Sonos app: the card reads the favorites every time. The
button next to the tabs shows them as tiles or as a list, which the card remembers
per browser.

**Sonos groups** are one choice in the speaker list, like "Era 300 + Era 100", since
grouped speakers play one queue. The volume slider and the − and + buttons then
move every speaker in the group by as much. The group button next to the speaker
list groups speakers: tick the speakers to play together, or tap a preset group.
The presets are the `groups` of the card and your media player groups in Home
Assistant (**Settings → Devices & services → Helpers → Group → Media player
group**) whose speakers the card all shows. Presets of the same speakers show once,
a group of the card before a group of Home Assistant, and a Sonos group of those
speakers goes by that name.

**The microphone** opens Assist and listens right away, so you can say "speel Oasis
in de keuken". Browsers only let Assist use the microphone over HTTPS, in the
Home Assistant app it always works. Without it you type to Assist instead.

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

Play a song, album, artist or playlist link, from **Share → Copy Link** in the
Music app. An artist link plays the top songs of the artist:

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
`media_content_id`. Pass the `url` to `apple_music.play`, or the
`media_content_id` of a song to `media_player.play_media` on a Sonos speaker.

### Voice

Expose your Sonos speakers to Assist (**Settings → Voice assistants → Expose**) and
tell Assist what to play and where:

| Dutch | English | Plays |
| --- | --- | --- |
| speel Oasis in de woonkamer | play Oasis in the living room | the best match |
| speel het album Parachutes op de Era 100 | play the album Parachutes on the Era 100 | an album |
| speel het nummer Wonderwall van Oasis in de keuken | play the song Wonderwall by Oasis in the kitchen | a song |
| speel muziek van Stromae in de keuken | play music by Stromae in the kitchen | the top songs of an artist |
| speel de afspeellijst Koffietentje in de keuken | play the playlist Koffietentje in the kitchen | a playlist from your Sonos favorites |

Name a speaker, or an area to play on all its exposed Sonos speakers, grouped. The
names and aliases of speakers and areas all work, so add an alias like "Woonkamer"
to an area to call it that. Without a type the integration looks for a playlist in
your Sonos favorites with that name first, then for an artist, album or song with
that exact name, then for the best matching song.

The sentences work with every Assist pipeline, also with an AI conversation agent:
Home Assistant answers them before the agent. An AI agent that may control Home
Assistant also gets a tool to play music, for requests in other words, like
"put on something by Oasis in the kitchen". Speakers you do not expose are left
alone, by the sentences and by the tool.

## Limitations

- Only Sonos speakers play Apple Music. Other speakers are refused with an error.
- The media browser plays songs only. Sonos needs metadata to queue a whole album
  or playlist, which `media_player.play_media` cannot pass, so play those with
  `apple_music.play`.
- Without an Apple Developer account there is no access to your library, so
  searching finds songs, albums and artists, not playlists. Save your playlists as
  Sonos favorites to find them in the card and by voice, or play them by link. The
  card does not show the songs of a playlist.
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
