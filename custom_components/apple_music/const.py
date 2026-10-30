"""Constants for the Apple Music integration."""

from enum import StrEnum
from typing import Final

DOMAIN: Final = "apple_music"

CONF_STOREFRONT: Final = "storefront"

SEARCH_URL: Final = "https://itunes.apple.com/search"
LOOKUP_URL: Final = "https://itunes.apple.com/lookup"
CHARTS_URL: Final = (
    "https://rss.marketingtools.apple.com/api/v2/{storefront}/music/most-played/"
    "{limit}/{feed}.json"
)

CHART_LIMIT: Final = 50
CHART_CACHE_SECONDS: Final = 3600
REQUEST_TIMEOUT: Final = 15

ATTR_QUERY: Final = "query"
ATTR_URL: Final = "url"
ATTR_KIND: Final = "media_type"
ATTR_LIMIT: Final = "limit"

SERVICE_PLAY: Final = "play"
SERVICE_SEARCH: Final = "search"

SONOS_DOMAIN: Final = "sonos"


class Kind(StrEnum):
    """Apple Music catalog item kinds, named after their music.apple.com path."""

    SONG = "song"
    ALBUM = "album"
    ARTIST = "artist"
    PLAYLIST = "playlist"


SEARCHABLE_KINDS: Final = (Kind.SONG, Kind.ALBUM, Kind.ARTIST)
# Playlists are left out, Sonos can only play them through the play action.
CHART_KINDS: Final = (Kind.SONG, Kind.ALBUM)
