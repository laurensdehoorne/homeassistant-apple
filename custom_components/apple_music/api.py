"""Client for the public Apple Music catalog.

Searching uses the iTunes Search API and the charts use Apple's RSS feeds. Neither
needs an Apple Developer account. Playback happens on Sonos, which plays Apple Music
links natively with the Apple Music account linked in the Sonos app.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import aiohttp

from .const import (
    CHART_CACHE_SECONDS,
    CHART_LIMIT,
    CHARTS_URL,
    DOMAIN,
    LOOKUP_URL,
    REQUEST_TIMEOUT,
    SEARCH_URL,
    Kind,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

ARTWORK_SIZE = "600x600"
# The last part of an artwork link names its size, like 400x400cc.jpeg.
_ARTWORK_SIZE = re.compile(r"/\d+x\d+(?=[^/]*$)")

_SEARCH_ENTITIES = {
    Kind.SONG: "song",
    Kind.ALBUM: "album",
    Kind.ARTIST: "musicArtist",
}
_CHART_FEEDS = {
    Kind.SONG: "songs",
    Kind.ALBUM: "albums",
    Kind.PLAYLIST: "playlists",
}

# The links that play, in the order to try them: a song on an album page first.
_LINKS = (
    (Kind.SONG, re.compile(r"https://music\.apple\.com/\w+/album/[^/?]+/\d+\?i=(\d+)")),
    (Kind.SONG, re.compile(r"https://music\.apple\.com/\w+/song/(?:[^/?]+/)?(\d+)")),
    (Kind.ALBUM, re.compile(r"https://music\.apple\.com/\w+/album/(?:[^/?]+/)?(\d+)")),
    (
        Kind.ARTIST,
        re.compile(r"https://music\.apple\.com/\w+/artist/(?:[^/?]+/)?(\d+)"),
    ),
    (
        Kind.PLAYLIST,
        re.compile(
            r"https://music\.apple\.com/\w+/playlist/(?:[^/?]+/)?(pl\.[-a-zA-Z0-9]+)"
        ),
    ),
    (
        Kind.PLAYLIST,
        re.compile(r"https://music\.apple\.com/library/playlist/(p\.[-a-zA-Z0-9]+)"),
    ),
)


class AppleMusicError(Exception):
    """Raised when the Apple Music catalog cannot be reached."""


def parse_url(url: str) -> tuple[Kind, str] | None:
    """Return the kind and id of an Apple Music song, album, artist or playlist link."""
    for kind, pattern in _LINKS:
        if match := pattern.match(url):
            return kind, match.group(1)
    return None


def is_library_playlist(item_id: str) -> bool:
    """Return whether a playlist id is of a playlist in someone's library."""
    return item_id.startswith("p.")


def share_url(storefront: str, kind: Kind, item_id: str) -> str:
    """Return the music.apple.com link of a catalog item."""
    if kind == Kind.PLAYLIST and is_library_playlist(item_id):
        # Only its owner opens it, but the link plays like any other.
        return f"https://music.apple.com/library/playlist/{item_id}"
    # Apple redirects any slug to the canonical one.
    return f"https://music.apple.com/{storefront}/{kind}/-/{item_id}"


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """A song, album, artist or playlist in the Apple Music catalog."""

    kind: Kind
    id: str
    name: str
    artist: str | None = None
    album: str | None = None
    artwork_url: str | None = None

    @property
    def identifier(self) -> str:
        """Return the media source identifier of this item."""
        return f"{self.kind}/{self.id}"

    def url(self, storefront: str) -> str:
        """Return the music.apple.com link of this item."""
        return share_url(storefront, self.kind, self.id)

    def as_dict(self, storefront: str) -> dict[str, Any]:
        """Return the item as a service response."""
        return {
            "media_type": self.kind,
            "id": self.id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "url": self.url(storefront),
            "media_content_id": f"media-source://{DOMAIN}/{self.identifier}",
            "artwork_url": self.artwork_url,
        }


def resize_artwork(url: str) -> str:
    """Return the artwork of an Apple Music artwork link at ARTWORK_SIZE."""
    return _ARTWORK_SIZE.sub(f"/{ARTWORK_SIZE}", url)


def _artwork(url: str | None) -> str | None:
    """Return a larger version of the 100x100 artwork Apple returns."""
    return url.replace("100x100", ARTWORK_SIZE) if url else None


def _parse_lookup_item(data: Mapping[str, Any]) -> CatalogItem | None:
    """Parse an iTunes Search API result."""
    match data.get("wrapperType"), data.get("kind"):
        case "track", "song":
            return CatalogItem(
                kind=Kind.SONG,
                id=str(data["trackId"]),
                name=data["trackName"],
                artist=data.get("artistName"),
                album=data.get("collectionName"),
                artwork_url=_artwork(data.get("artworkUrl100")),
            )
        case "collection", _:
            return CatalogItem(
                kind=Kind.ALBUM,
                id=str(data["collectionId"]),
                name=data["collectionName"],
                artist=data.get("artistName"),
                artwork_url=_artwork(data.get("artworkUrl100")),
            )
        case "artist", _:
            return CatalogItem(
                kind=Kind.ARTIST,
                id=str(data["artistId"]),
                name=data["artistName"],
            )
    return None


def _parse_chart_item(kind: Kind, data: Mapping[str, Any]) -> CatalogItem:
    """Parse an Apple Music RSS chart entry."""
    return CatalogItem(
        kind=kind,
        id=str(data["id"]),
        name=data["name"],
        artist=data.get("artistName"),
        artwork_url=_artwork(data.get("artworkUrl100")),
    )


class AppleMusicCatalog:
    """Search and browse the Apple Music catalog of one storefront."""

    def __init__(self, session: aiohttp.ClientSession, storefront: str) -> None:
        """Initialize the client for a storefront, a two letter country code."""
        self._session = session
        self.storefront = storefront.lower()
        self._charts: dict[Kind, tuple[float, list[CatalogItem]]] = {}

    async def _get(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        """Return the JSON at url."""
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(url, params=params) as response,
            ):
                response.raise_for_status()
                # The iTunes Search API answers with text/javascript.
                return await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            msg = f"Apple Music request failed: {err}"
            raise AppleMusicError(msg) from err

    async def _lookup(self, item_id: str, kind: Kind, limit: int) -> list[CatalogItem]:
        """Return the songs or albums that belong to an album or artist."""
        data = await self._get(
            LOOKUP_URL,
            {
                "id": item_id,
                "entity": _SEARCH_ENTITIES[kind],
                "limit": str(limit),
                "country": self.storefront,
            },
        )
        items = (_parse_lookup_item(result) for result in data.get("results", []))
        # The results start with the album or artist that was looked up.
        return [item for item in items if item is not None and item.kind == kind]

    async def search(self, term: str, kind: Kind, limit: int = 10) -> list[CatalogItem]:
        """Search the catalog for songs, albums or artists."""
        if (entity := _SEARCH_ENTITIES.get(kind)) is None:
            msg = f"Searching for {kind} is not supported"
            raise ValueError(msg)
        data = await self._get(
            SEARCH_URL,
            {
                "term": term,
                "media": "music",
                "entity": entity,
                "limit": str(limit),
                "country": self.storefront,
            },
        )
        items = (_parse_lookup_item(result) for result in data.get("results", []))
        return [item for item in items if item is not None and item.kind == kind]

    async def song(self, song_id: str) -> CatalogItem | None:
        """Return a song by its id."""
        data = await self._get(LOOKUP_URL, {"id": song_id, "country": self.storefront})
        items = (_parse_lookup_item(result) for result in data.get("results", []))
        return next((item for item in items if item and item.kind == Kind.SONG), None)

    async def album_songs(self, album_id: str) -> list[CatalogItem]:
        """Return the songs on an album, in album order."""
        return await self._lookup(album_id, Kind.SONG, 200)

    async def artist_songs(self, artist_id: str, limit: int = 25) -> list[CatalogItem]:
        """Return the most popular songs of an artist."""
        return await self._lookup(artist_id, Kind.SONG, limit)

    async def artist_albums(self, artist_id: str, limit: int = 50) -> list[CatalogItem]:
        """Return the albums of an artist, most popular first."""
        return await self._lookup(artist_id, Kind.ALBUM, limit)

    async def chart(self, kind: Kind) -> list[CatalogItem]:
        """Return the most played songs, albums or playlists of the storefront."""
        cached = self._charts.get(kind)
        if cached is not None and time.monotonic() - cached[0] < CHART_CACHE_SECONDS:
            return cached[1]
        try:
            data = await self._get(
                CHARTS_URL.format(
                    storefront=self.storefront,
                    limit=CHART_LIMIT,
                    feed=_CHART_FEEDS[kind],
                )
            )
        except AppleMusicError:
            # The chart feeds regularly answer 502, an older chart beats none.
            if cached is not None:
                return cached[1]
            raise
        entries = data.get("feed", {}).get("results", [])
        items = [_parse_chart_item(kind, entry) for entry in entries]
        self._charts[kind] = (time.monotonic(), items)
        return items
