"""Browse the Apple Music charts and catalog from the Sonos media browser.

Songs play from the browser. Albums open to their songs: Sonos needs metadata to
queue a whole album, which play_media cannot pass, so they play with the play action.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from homeassistant.components.media_player import (
    BrowseError,
    MediaClass,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.exceptions import HomeAssistantError

from .api import AppleMusicCatalog, AppleMusicError, CatalogItem
from .const import CHART_KINDS, DOMAIN, SEARCHABLE_KINDS, Kind
from .helpers import get_catalog, is_sonos_player
from .sonos import async_song_uri

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Sonos only lists media source items with an audio/ content type.
AUDIO_CONTENT_TYPE = "audio/mp4"
CHARTS = "charts"
SEARCH_LIMIT = 10

_MEDIA_CLASSES = {
    Kind.SONG: MediaClass.TRACK,
    Kind.ALBUM: MediaClass.ALBUM,
    Kind.ARTIST: MediaClass.ARTIST,
    Kind.PLAYLIST: MediaClass.PLAYLIST,
}
_CHART_TITLES = {
    Kind.SONG: "Top songs",
    Kind.ALBUM: "Top albums",
}
_SEARCH_KINDS: dict[str, Kind] = {
    MediaClass.TRACK: Kind.SONG,
    MediaType.TRACK: Kind.SONG,
    MediaType.MUSIC: Kind.SONG,
    MediaClass.ALBUM: Kind.ALBUM,
    MediaClass.ARTIST: Kind.ARTIST,
}


async def async_get_media_source(hass: HomeAssistant) -> AppleMusicMediaSource:
    """Set up the Apple Music media source."""
    return AppleMusicMediaSource(hass)


def _browse_item(item: CatalogItem) -> BrowseMediaSource:
    """Return a song, album or artist to browse."""
    is_song = item.kind == Kind.SONG
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=item.identifier,
        media_class=_MEDIA_CLASSES[item.kind],
        media_content_type=AUDIO_CONTENT_TYPE if is_song else MediaType.MUSIC,
        title=f"{item.name} · {item.artist}" if item.artist else item.name,
        can_play=is_song,
        can_expand=not is_song,
        thumbnail=item.artwork_url,
    )


def _directory(
    identifier: str | None,
    title: str,
    children: list[BrowseMediaSource] | None = None,
    children_media_class: MediaClass = MediaClass.DIRECTORY,
) -> BrowseMediaSource:
    """Return a directory to browse."""
    return BrowseMediaSource(
        domain=DOMAIN,
        identifier=identifier,
        media_class=MediaClass.DIRECTORY,
        media_content_type="",
        title=title,
        can_play=False,
        can_expand=True,
        children=children,
        children_media_class=children_media_class,
        can_search=True,
        search_media_classes=[MediaClass.TRACK, MediaClass.ALBUM, MediaClass.ARTIST],
    )


class AppleMusicMediaSource(MediaSource):
    """Provide the Apple Music catalog as a media source."""

    name = "Apple Music"

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the Apple Music media source."""
        super().__init__(DOMAIN)
        self.hass = hass

    def _catalog(self) -> AppleMusicCatalog:
        """Return the catalog, or raise when Apple Music is not set up."""
        if (catalog := get_catalog(self.hass)) is None:
            raise BrowseError(translation_domain=DOMAIN, translation_key="not_loaded")
        return catalog

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        """Resolve a song to the URI the Sonos speaker plays it from."""
        kind, _, item_id = item.identifier.partition("/")
        if kind != Kind.SONG or not item_id:
            raise Unresolvable(
                translation_domain=DOMAIN,
                translation_key="not_playable",
                translation_placeholders={"identifier": item.identifier},
            )
        target = item.target_media_player
        if not target or not is_sonos_player(self.hass, target):
            raise Unresolvable(
                translation_domain=DOMAIN,
                translation_key="sonos_only",
                translation_placeholders={"entity_id": target or "-"},
            )
        try:
            uri = await async_song_uri(self.hass, target, item_id)
        except HomeAssistantError as err:
            raise Unresolvable(
                translation_domain=err.translation_domain,
                translation_key=err.translation_key,
                translation_placeholders=err.translation_placeholders,
            ) from err
        return PlayMedia(uri, AUDIO_CONTENT_TYPE)

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        """Browse the charts, albums and artists."""
        catalog = self._catalog()
        if not item.identifier:
            return _directory(
                None,
                self.name or DOMAIN,
                [
                    _directory(f"{CHARTS}/{kind}", _CHART_TITLES[kind])
                    for kind in CHART_KINDS
                ],
            )

        kind, _, item_id = item.identifier.partition("/")
        try:
            if kind == CHARTS and item_id in CHART_KINDS:
                chart_kind = Kind(item_id)
                items = await catalog.chart(chart_kind)
                title = _CHART_TITLES[chart_kind]
                children_class = _MEDIA_CLASSES[chart_kind]
            elif kind == Kind.ALBUM:
                items = await catalog.album_songs(item_id)
                title = (items[0].album if items else None) or "Album"
                children_class = MediaClass.TRACK
            elif kind == Kind.ARTIST:
                songs, albums = await asyncio.gather(
                    catalog.artist_songs(item_id), catalog.artist_albums(item_id)
                )
                items = [*songs, *albums]
                title = (songs[0].artist if songs else None) or "Artist"
                children_class = MediaClass.DIRECTORY
            else:
                raise BrowseError(
                    translation_domain=DOMAIN,
                    translation_key="unknown_item",
                    translation_placeholders={"identifier": item.identifier},
                )
        except AppleMusicError as err:
            raise BrowseError(
                translation_domain=DOMAIN,
                translation_key="request_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        return _directory(
            item.identifier, title, [_browse_item(i) for i in items], children_class
        )

    async def async_search_media(
        self,
        item: MediaSourceItem,  # noqa: ARG002
        query: SearchMediaQuery,
    ) -> SearchMedia:
        """Search the catalog for songs, albums and artists."""
        catalog = self._catalog()
        requested = [
            *(query.media_filter_classes or []),
            *([query.media_content_type] if query.media_content_type else []),
        ]
        kinds = list(
            dict.fromkeys(_SEARCH_KINDS[c] for c in requested if c in _SEARCH_KINDS)
        ) or list(SEARCHABLE_KINDS)
        try:
            results = await asyncio.gather(
                *(
                    catalog.search(query.search_query, kind, SEARCH_LIMIT)
                    for kind in kinds
                )
            )
        except AppleMusicError as err:
            raise BrowseError(
                translation_domain=DOMAIN,
                translation_key="request_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return SearchMedia(result=[_browse_item(i) for found in results for i in found])
