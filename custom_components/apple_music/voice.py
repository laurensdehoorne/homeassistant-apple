"""Play Apple Music on Sonos speakers by voice, through Assist.

Home Assistant's own "play ... in ..." sentences search the media player, which
Sonos speakers cannot. Sentence triggers answer before any conversation agent, so
for each exposed Sonos speaker and area a trigger plays the best Apple Music match.
The triggers name the speakers and areas, so sentences for other players still
reach Home Assistant.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.conversation.agent_manager import get_agent_manager
from homeassistant.components.homeassistant.exposed_entities import (
    async_listen_entity_updates,
    async_should_expose,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.components.media_player import MediaPlayerEnqueue
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_added_domain
from homeassistant.helpers.start import async_at_started

from . import sonos
from .api import AppleMusicCatalog, AppleMusicError, CatalogItem
from .const import SEARCHABLE_KINDS, SONOS_DOMAIN, Kind

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hassil.recognize import RecognizeResult
    from homeassistant.components.conversation import ConversationInput

_LOGGER = logging.getLogger(__name__)

ASSIST = "conversation"
SEARCH_LIMIT = 5
ARTIST_SONGS = 20

# A kind of music named before the query, like "het album Parachutes".
_KINDS = tuple(
    (kind, re.compile(rf"^{words} (.+)$", re.IGNORECASE))
    for kind, words in (
        (Kind.PLAYLIST, r"(?:de |the |mijn |my )?(?:afspeellijst|playlist)"),
        (Kind.ALBUM, r"(?:het |the )?album"),
        (Kind.SONG, r"(?:het |the )?(?:nummer|liedje|song|track)"),
        (
            Kind.ARTIST,
            (
                r"(?:(?:de )?artiest|(?:the )?artist"
                r"|(?:muziek|nummers|liedjes|music|songs) (?:van|by))"
            ),
        ),
    )
)
# A song or album and its artist, like "Wonderwall van Oasis".
_BY = re.compile(r"^(.+?) (?:van|by) (.+)$", re.IGNORECASE)
# The characters that mean something in a sentence template.
_TEMPLATE_SYNTAX = re.compile(r"[^\w\s']")


class NothingFoundError(HomeAssistantError):
    """Raised when Apple Music has nothing that matches what was asked for."""


def normalize(text: str) -> str:
    """Return text as it is compared, without case, accents and punctuation."""
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^\w\s]", " ", text.casefold()).split())


@dataclass(frozen=True, slots=True)
class Target:
    """Sonos speakers to play on, called by the name of a speaker or an area."""

    name: str
    area: bool
    entity_ids: tuple[str, ...]
    names: tuple[str, ...]

    def matches(self, name: str) -> bool:
        """Return whether the target is called name."""
        return normalize(name) in {normalize(own) for own in self.names}


@callback
def _async_names(
    hass: HomeAssistant, assistant: str
) -> Iterator[tuple[list[str], str, bool, str]]:
    """Yield the names of the exposed Sonos speakers and of their areas.

    Each comes with its display name, whether it names an area, and the speaker.
    """
    devices = dr.async_get(hass)
    areas = ar.async_get(hass)
    for entry in er.async_get(hass).entities.values():
        if (
            entry.domain != MEDIA_PLAYER_DOMAIN
            or entry.platform != SONOS_DOMAIN
            or entry.disabled
            or not async_should_expose(hass, assistant, entry.entity_id)
        ):
            continue
        names = er.async_get_entity_aliases(hass, entry, allow_empty=False)
        yield names, names[0], False, entry.entity_id
        area_id = entry.area_id
        if area_id is None and entry.device_id is not None:
            device = devices.async_get(entry.device_id)
            area_id = device.area_id if device else None
        if area_id is not None and (area := areas.async_get_area(area_id)):
            yield [area.name, *area.aliases], area.name, True, entry.entity_id


@callback
def async_get_targets(hass: HomeAssistant, assistant: str) -> list[Target]:
    """Return the Sonos speakers exposed to an assistant, by speaker and by area."""
    # Each name as it is compared → its display name, whether it names an area,
    # its speakers and how it is written. The first speaker or area keeps a name.
    found: dict[str, tuple[str, bool, set[str], set[str]]] = {}
    for names, display, area, entity_id in _async_names(hass, assistant):
        for name in names:
            if key := normalize(name):
                found.setdefault(key, (display, area, set(), set()))
                found[key][2].add(entity_id)
                found[key][3].add(name)

    # The names of a speaker, or of an area, call the same target.
    targets: dict[tuple[str, bool, frozenset[str]], set[str]] = {}
    for display, is_area, entity_ids, spellings in found.values():
        group = (display, is_area, frozenset(entity_ids))
        targets.setdefault(group, set()).update(spellings)
    return sorted(
        (
            Target(
                display, is_area, tuple(sorted(entity_ids)), tuple(sorted(spellings))
            )
            for (display, is_area, entity_ids), spellings in targets.items()
        ),
        key=lambda target: target.name.casefold(),
    )


@dataclass(frozen=True, slots=True)
class Music:
    """What to play for a query: a song, an album, an artist or a playlist."""

    kind: Kind
    name: str
    artist: str | None
    items: list[CatalogItem]

    def describe(self, language: str) -> str:
        """Return what plays, to say it in a sentence."""
        dutch = language.startswith("nl")
        if self.kind == Kind.PLAYLIST:
            return (
                f"de afspeellijst {self.name}" if dutch else f"the playlist {self.name}"
            )
        if self.kind == Kind.ARTIST:
            return f"nummers van {self.name}" if dutch else f"songs by {self.name}"
        if self.artist:
            return (
                f"{self.name} van {self.artist}"
                if dutch
                else f"{self.name} by {self.artist}"
            )
        return self.name


def _parse(query: str) -> tuple[Kind | None, str]:
    """Return the kind of music named in a query, if any, and what to look for."""
    query = " ".join(query.split())
    for kind, pattern in _KINDS:
        if match := pattern.match(query):
            return kind, match.group(1)
    return None, query


def _named(items: list[CatalogItem], name: str) -> CatalogItem | None:
    """Return the first item that is called name."""
    name = normalize(name)
    return next((item for item in items if normalize(item.name) == name), None)


def _playlist(playlists: list[CatalogItem], name: str) -> CatalogItem | None:
    """Return the playlist called name, or else the first one whose name has it."""
    key = normalize(name)
    return _named(playlists, name) or next(
        (item for item in playlists if key in normalize(item.name)), None
    )


async def _async_artist(catalog: AppleMusicCatalog, artist: CatalogItem) -> Music:
    """Return the most popular songs of an artist."""
    if not (songs := await catalog.artist_songs(artist.id, ARTIST_SONGS)):
        raise NothingFoundError
    return Music(Kind.ARTIST, artist.name, None, songs)


async def _async_music(
    catalog: AppleMusicCatalog, kind: Kind, item: CatalogItem
) -> Music:
    """Return what plays for a song, an album or an artist."""
    if kind == Kind.ARTIST:
        return await _async_artist(catalog, item)
    return Music(kind, item.name, item.artist, [item])


def _split_by(term: str) -> tuple[str, str | None]:
    """Return the title and the artist of "Wonderwall van Oasis"."""
    return (by.group(1), by.group(2)) if (by := _BY.match(term)) else (term, None)


async def _async_search_kind(
    catalog: AppleMusicCatalog, kind: Kind, term: str
) -> Music:
    """Return the best catalog match of one kind for a term."""
    title, artist = _split_by(term)
    items = await catalog.search(term, kind, SEARCH_LIMIT)
    if not items and artist and kind != Kind.ARTIST:
        items = await catalog.search(f"{title} {artist}", kind, SEARCH_LIMIT)
    if not items:
        raise NothingFoundError
    best = _named(items, term) or _named(items, title) or items[0]
    return await _async_music(catalog, kind, best)


async def _async_search_any(catalog: AppleMusicCatalog, term: str) -> Music:
    """Return the best catalog match of any kind for a term."""
    songs, albums, artists = await asyncio.gather(
        *(catalog.search(term, kind, SEARCH_LIMIT) for kind in SEARCHABLE_KINDS)
    )
    # A name said in full wins, the artist first: "Oasis" plays Oasis.
    named = [(Kind.ARTIST, artists, term), (Kind.ALBUM, albums, term)]
    named.append((Kind.SONG, songs, term))
    title, artist = _split_by(term)
    if artist and not any(_named(items, name) for _, items, name in named):
        # "Wonderwall van Oasis": Apple finds it by its title and artist.
        songs_by, albums_by = await asyncio.gather(
            catalog.search(f"{title} {artist}", Kind.SONG, SEARCH_LIMIT),
            catalog.search(f"{title} {artist}", Kind.ALBUM, SEARCH_LIMIT),
        )
        named = [(Kind.SONG, songs_by, title), (Kind.ALBUM, albums_by, title)]
        songs, albums = songs or songs_by, albums or albums_by
    for kind, items, name in named:
        if found := _named(items, name):
            return await _async_music(catalog, kind, found)
    for kind, items in (
        (Kind.SONG, songs),
        (Kind.ALBUM, albums),
        (Kind.ARTIST, artists),
    ):
        if items:
            return await _async_music(catalog, kind, items[0])
    raise NothingFoundError


async def async_find_music(
    hass: HomeAssistant,
    catalog: AppleMusicCatalog,
    query: str,
    entity_id: str,
    kind: Kind | None = None,
) -> Music:
    """Return the best match for a query, among the playlists and the catalog.

    The playlists are the Apple Music playlists in the Sonos favorites of the
    household of entity_id. A kind named in the query wins over the kind passed.
    """
    named, term = _parse(query)
    kind = named or kind
    if kind in (None, Kind.PLAYLIST):
        playlists = await sonos.async_playlists(hass, entity_id)
        found = _playlist(playlists, term) if kind else _named(playlists, term)
        if found:
            return Music(Kind.PLAYLIST, found.name, None, [found])
        if kind == Kind.PLAYLIST:
            raise NothingFoundError
    try:
        if kind is None:
            return await _async_search_any(catalog, term)
        return await _async_search_kind(catalog, kind, term)
    except AppleMusicError as err:
        raise HomeAssistantError(str(err)) from err


async def async_play_music(hass: HomeAssistant, target: Target, music: Music) -> None:
    """Play music on the speakers of a target, grouped so they play together."""
    entity_ids = list(target.entity_ids)
    await sonos.async_join(hass, entity_ids)
    await sonos.async_play(hass, entity_ids, music.items, MediaPlayerEnqueue.REPLACE)


def _sentences(target: Target) -> list[str]:
    """Return the sentences that play music on a target."""
    names = "|".join(
        sorted(
            {" ".join(_TEMPLATE_SYNTAX.sub(" ", name).split()) for name in target.names}
            - {""}
        )
    )
    return [
        f"speel {{query}} (in|op) [de|het] ({names}) [af]",
        f"play {{query}} (in|on) [the] ({names})",
    ]


class VoiceCommands:
    """Sentence triggers that play Apple Music on the exposed Sonos speakers."""

    def __init__(self, hass: HomeAssistant, catalog: AppleMusicCatalog) -> None:
        """Initialize the voice commands."""
        self._hass = hass
        self._catalog = catalog
        self._registered: dict[Target, CALLBACK_TYPE] = {}
        self._debouncer = Debouncer(
            hass, _LOGGER, cooldown=1, immediate=False, function=self._async_update
        )

    @callback
    def async_setup(self) -> CALLBACK_TYPE:
        """Register the triggers, and update them when speakers or areas change."""
        schedule = self._debouncer.async_schedule_call

        @callback
        def changed(_event: Event[Any] | None = None) -> None:
            schedule()

        @callback
        def started(_hass: HomeAssistant) -> None:
            # Sonos adds its speakers while Home Assistant starts.
            self._async_update()

        unsubscribe = [
            async_at_started(self._hass, started),
            async_listen_entity_updates(self._hass, ASSIST, changed),
            async_track_state_added_domain(self._hass, MEDIA_PLAYER_DOMAIN, changed),
            self._hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, changed),
            self._hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, changed),
            self._hass.bus.async_listen(ar.EVENT_AREA_REGISTRY_UPDATED, changed),
        ]

        @callback
        def unload() -> None:
            for unsub in unsubscribe:
                unsub()
            self._debouncer.async_shutdown()
            for unregister in self._registered.values():
                unregister()
            self._registered.clear()

        return unload

    @callback
    def _async_update(self) -> None:
        """Register a trigger for each exposed speaker and area."""
        targets = set(async_get_targets(self._hass, ASSIST))
        for target in set(self._registered) - targets:
            self._registered.pop(target)()
        manager = get_agent_manager(self._hass)
        for target in targets - set(self._registered):
            self._registered[target] = manager.register_trigger(
                _sentences(target), partial(self._async_handle, target)
            )

    async def _async_handle(
        self, target: Target, user_input: ConversationInput, result: RecognizeResult
    ) -> str:
        """Play what was asked for and say what plays."""
        query = str(result.entities["query"].value).strip()
        # "Speel Oasis af in de keuken" leaves the "af" in the query.
        query = re.sub(r"\s+af$", "", query, flags=re.IGNORECASE)
        dutch = user_input.language.startswith("nl")
        try:
            music = await async_find_music(
                self._hass, self._catalog, query, target.entity_ids[0]
            )
            await async_play_music(self._hass, target, music)
        except NothingFoundError:
            if dutch:
                return f"Ik vond niets op Apple Music voor {query}."
            return f"I found nothing on Apple Music for {query}."
        except HomeAssistantError as err:
            _LOGGER.warning("Could not play %s on %s: %s", query, target.name, err)
            return f"Dat lukte niet: {err}" if dutch else f"That did not work: {err}"
        what = music.describe(user_input.language)
        if dutch:
            return f"Ik speel {what} {'in' if target.area else 'op'} {target.name}."
        return f"Playing {what} {'in' if target.area else 'on'} {target.name}."


@callback
def async_setup_voice(hass: HomeAssistant, catalog: AppleMusicCatalog) -> CALLBACK_TYPE:
    """Play Apple Music on the Sonos speakers exposed to Assist by voice."""
    return VoiceCommands(hass, catalog).async_setup()
