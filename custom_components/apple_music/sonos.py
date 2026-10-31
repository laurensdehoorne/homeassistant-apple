"""Queue Apple Music on Sonos speakers with the household's own Apple Music account.

Home Assistant's Sonos integration plays music.apple.com links as SoCo share links,
which always name Apple Music account "0". Sonos refuses those with UPnP error 800
when the linked account has another id. This module builds the queue items itself,
with the account Sonos uses for the Apple Music favorites, the way the Sonos app does.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.media_player import (
    ATTR_GROUP_MEMBERS,
    SERVICE_JOIN,
    MediaPlayerEnqueue,
)
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .api import CatalogItem, is_library_playlist, resize_artwork
from .const import DOMAIN, SONOS_DOMAIN, Kind

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

APPLE_MUSIC_SID = 204
# Sonos identifies a music service by its sid * 256 + 7.
APPLE_MUSIC_SERVICE_TYPE = APPLE_MUSIC_SID * 256 + 7

_FAVORITE = re.compile(r"<item\b.*?</item>", re.DOTALL)
_RES = re.compile(r"<res\b[^>]*>([^<]*)</res>")
_RES_MD = re.compile(r"<r:resMD>([^<]*)</r:resMD>")
_TITLE = re.compile(r"<dc:title>([^<]*)</dc:title>")
_ART = re.compile(r"<upnp:albumArtURI>([^<]*)</upnp:albumArtURI>")
_SERIAL = re.compile(rf"[?&]sid={APPLE_MUSIC_SID}&.*\bsn=(\d+)")
_TOKEN = re.compile(rf"#Svc{APPLE_MUSIC_SERVICE_TYPE}-([^-<]+)-Token")
# Playlists of the catalog have ids like pl.77f96ce5, those of a library p.0EMR6fVX.
_PLAYLIST = re.compile(
    rf"^x-rincon-cpcontainer:1006206c(?:library)?playlist%3a(pl?\.[-.\w]+)"
    rf"\?sid={APPLE_MUSIC_SID}&",
    re.IGNORECASE,
)

# The URI, item id prefix and class Sonos uses for each kind of Apple Music item.
_ITEMS = {
    Kind.SONG: (
        "x-sonos-http:{key}.mp4?sid=204&flags=8232&sn={serial}",
        "10032020",
        "object.item.audioItem.musicTrack",
    ),
    Kind.ALBUM: (
        "x-rincon-cpcontainer:1004206c{key}?sid=204&flags=8300&sn={serial}",
        "1004206c",
        "object.container.album.musicAlbum",
    ),
    Kind.PLAYLIST: (
        "x-rincon-cpcontainer:1006206c{key}?sid=204&flags=8300&sn={serial}",
        "1006206c",
        "object.container.playlistContainer",
    ),
}

_DIDL = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
    'xmlns:r="urn:schemas-rinconnetworks-com:metadata-1-0/" '
    'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
    '<item id="{item_id}" parentID="" restricted="true">'
    "<dc:title>{title}</dc:title>{extra}<upnp:class>{item_class}</upnp:class>"
    '<desc id="cdudn" nameSpace="urn:schemas-rinconnetworks-com:metadata-1-0/">'
    "{desc}</desc></item></DIDL-Lite>"
)


@dataclass(frozen=True, slots=True)
class AppleMusicAccount:
    """The Apple Music account linked to a Sonos household."""

    serial: str
    token: str

    @property
    def desc(self) -> str:
        """Return the account descriptor Sonos expects in the item metadata."""
        return (
            f"SA_RINCON{APPLE_MUSIC_SERVICE_TYPE}_X_"
            f"#Svc{APPLE_MUSIC_SERVICE_TYPE}-{self.token}-Token"
        )


def find_account(favorites: str) -> AppleMusicAccount | None:
    """Return the Apple Music account of the Sonos favorites, as DIDL-Lite."""
    accounts = []
    for item in _FAVORITE.findall(favorites):
        if (res := _RES.search(item)) is None or (
            res_md := _RES_MD.search(item)
        ) is None:
            continue
        serial = _SERIAL.search(html.unescape(res.group(1)))
        token = _TOKEN.search(html.unescape(res_md.group(1)))
        if serial and token:
            accounts.append(AppleMusicAccount(serial.group(1), token.group(1)))
    # Sonos numbers accounts in the order they were linked. Favorites saved with an
    # account that was linked again later keep the old, often stale, account.
    return max(accounts, key=lambda account: int(account.serial), default=None)


def find_playlists(favorites: str) -> list[CatalogItem]:
    """Return the Apple Music playlists in the Sonos favorites, as DIDL-Lite."""
    playlists = []
    for item in _FAVORITE.findall(favorites):
        if (res := _RES.search(item)) is None or (
            playlist := _PLAYLIST.search(html.unescape(res.group(1)))
        ) is None:
            continue
        title = _TITLE.search(item)
        art = _ART.search(item)
        playlists.append(
            CatalogItem(
                kind=Kind.PLAYLIST,
                id=playlist.group(1),
                name=html.unescape(title.group(1)) if title else "",
                artwork_url=resize_artwork(html.unescape(art.group(1)))
                if art
                else None,
            )
        )
    return playlists


def _key(kind: Kind, item_id: str) -> str:
    """Return how Sonos names an Apple Music item, a playlist of a library apart."""
    if kind == Kind.PLAYLIST and is_library_playlist(item_id):
        return f"libraryplaylist%3a{item_id}"
    return f"{kind}%3a{item_id}"


def item_uri(account: AppleMusicAccount, kind: Kind, item_id: str) -> str:
    """Return the URI Sonos plays an Apple Music song, album or playlist from."""
    return _ITEMS[kind][0].format(key=_key(kind, item_id), serial=account.serial)


def _metadata(account: AppleMusicAccount, item: CatalogItem) -> str:
    """Return the DIDL-Lite metadata Sonos needs to find the item at Apple Music."""
    _, prefix, item_class = _ITEMS[item.kind]
    extra = ""
    if item.artist:
        extra += f"<dc:creator>{html.escape(item.artist)}</dc:creator>"
    if item.album:
        extra += f"<upnp:album>{html.escape(item.album)}</upnp:album>"
    if item.artwork_url:
        extra += f"<upnp:albumArtURI>{html.escape(item.artwork_url)}</upnp:albumArtURI>"
    return _DIDL.format(
        item_id=f"{prefix}{_key(item.kind, item.id)}",
        title=html.escape(item.name),
        extra=extra,
        item_class=item_class,
        desc=account.desc,
    )


def _favorites(soco: Any) -> str:
    """Return the Sonos favorites of the household of a Sonos speaker."""
    result = soco.contentDirectory.Browse(
        [
            ("ObjectID", "FV:2"),
            ("BrowseFlag", "BrowseDirectChildren"),
            ("Filter", "*"),
            ("StartingIndex", 0),
            ("RequestedCount", 500),
            ("SortCriteria", ""),
        ]
    )
    favorites: str = result["Result"]
    return favorites


def _account(soco: Any) -> AppleMusicAccount:
    """Return the Apple Music account of the household of a Sonos speaker."""
    if (account := find_account(_favorites(soco))) is None:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="no_account"
        )
    return account


def _queue(soco: Any, items: list[CatalogItem], enqueue: MediaPlayerEnqueue) -> None:
    """Queue items on a group coordinator, like play_media does for Sonos."""
    account = _account(soco)
    if enqueue == MediaPlayerEnqueue.REPLACE:
        soco.clear_queue()
    # Position 0 appends, the others are 1-based track numbers.
    position = 0
    if enqueue in (MediaPlayerEnqueue.NEXT, MediaPlayerEnqueue.PLAY):
        track = soco.get_current_track_info().get("playlist_position")
        position = int(track or 0) + 1
    first: int | None = None
    for item in items:
        result = soco.avTransport.AddURIToQueue(
            [
                ("InstanceID", 0),
                ("EnqueuedURI", item_uri(account, item.kind, item.id)),
                ("EnqueuedURIMetaData", _metadata(account, item)),
                ("DesiredFirstTrackNumberEnqueued", position),
                ("EnqueueAsNext", 0),
            ]
        )
        added = int(result["FirstTrackNumberEnqueued"])
        first = first or added
        if position:
            position = added + int(result["NumTracksAdded"])
    if enqueue == MediaPlayerEnqueue.REPLACE:
        soco.play_from_queue(0)
    elif enqueue == MediaPlayerEnqueue.PLAY and first:
        soco.play_from_queue(first - 1)


def _call(func: Any, *args: Any) -> Any:
    """Run a call to a Sonos speaker, turning its errors into readable ones."""
    try:
        return func(*args)
    except HomeAssistantError:
        raise
    # SoCo, the Sonos library, raises its own exception types for UPnP errors.
    except Exception as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="sonos_error",
            translation_placeholders={"error": str(err)},
        ) from err


def _coordinator(hass: HomeAssistant, entity_id: str) -> Any:
    """Return the SoCo instance of the group coordinator of a Sonos speaker."""
    if (entry := er.async_get(hass).async_get(entity_id)) is not None:
        for config_entry in hass.config_entries.async_loaded_entries(SONOS_DOMAIN):
            mappings = config_entry.runtime_data.unique_id_speaker_mappings
            if (speaker := mappings.get(entry.unique_id)) is not None:
                return (speaker.coordinator or speaker).soco
    raise HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="speaker_unavailable",
        translation_placeholders={"entity_id": entity_id},
    )


def _coordinators(hass: HomeAssistant, entity_ids: list[str]) -> list[Any]:
    """Return the group coordinators of Sonos speakers, each once."""
    # Grouped speakers share the one queue of their coordinator.
    coordinators = {
        id(soco): soco for soco in (_coordinator(hass, e) for e in entity_ids)
    }
    return list(coordinators.values())


async def async_play(
    hass: HomeAssistant,
    entity_ids: list[str],
    items: list[CatalogItem],
    enqueue: MediaPlayerEnqueue,
) -> None:
    """Play Apple Music songs, albums or playlists on Sonos speakers."""
    await asyncio.gather(
        *(
            hass.async_add_executor_job(_call, _queue, soco, items, enqueue)
            for soco in _coordinators(hass, entity_ids)
        )
    )


def _play_radio(soco: Any, url: str, name: str) -> None:
    """Play an internet radio stream, named like a station in the Sonos app."""
    # As a radio stream with a title, Sonos shows the station and the song on air.
    soco.play_uri(url, title=name, force_radio=True)


async def async_play_radio(
    hass: HomeAssistant, entity_ids: list[str], url: str, name: str
) -> None:
    """Play an internet radio stream on Sonos speakers."""
    await asyncio.gather(
        *(
            hass.async_add_executor_job(_call, _play_radio, soco, url, name)
            for soco in _coordinators(hass, entity_ids)
        )
    )


async def async_playlists(hass: HomeAssistant, entity_id: str) -> list[CatalogItem]:
    """Return the Apple Music playlists in the Sonos favorites of a speaker."""
    soco = _coordinator(hass, entity_id)
    favorites = await hass.async_add_executor_job(_call, _favorites, soco)
    return find_playlists(favorites)


async def async_join(hass: HomeAssistant, entity_ids: list[str]) -> None:
    """Group Sonos speakers, so they play one queue together."""
    first = entity_ids[0]
    state = hass.states.get(first)
    members = (state.attributes.get(ATTR_GROUP_MEMBERS) if state else None) or [first]
    if all(e in members for e in entity_ids):
        return
    # Home Assistant first takes a speaker out of a group it does not lead, so
    # then the speakers it played with have to join again.
    leads = members[0] == first
    others = [e for e in entity_ids if e != first and not (leads and e in members)]
    await hass.services.async_call(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_JOIN,
        {ATTR_ENTITY_ID: first, ATTR_GROUP_MEMBERS: others},
        blocking=True,
    )


async def async_song_uri(hass: HomeAssistant, entity_id: str, song_id: str) -> str:
    """Return the URI a Sonos speaker plays an Apple Music song from."""
    soco = _coordinator(hass, entity_id)
    account = await hass.async_add_executor_job(_call, _account, soco)
    return item_uri(account, Kind.SONG, song_id)
