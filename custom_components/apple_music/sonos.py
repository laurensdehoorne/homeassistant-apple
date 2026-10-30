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

from homeassistant.components.media_player import MediaPlayerEnqueue
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, SONOS_DOMAIN, Kind

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import CatalogItem

APPLE_MUSIC_SID = 204
# Sonos identifies a music service by its sid * 256 + 7.
APPLE_MUSIC_SERVICE_TYPE = APPLE_MUSIC_SID * 256 + 7

_FAVORITE = re.compile(r"<item\b.*?</item>", re.DOTALL)
_RES = re.compile(r"<res\b[^>]*>([^<]*)</res>")
_RES_MD = re.compile(r"<r:resMD>([^<]*)</r:resMD>")
_SERIAL = re.compile(rf"[?&]sid={APPLE_MUSIC_SID}&.*\bsn=(\d+)")
_TOKEN = re.compile(rf"#Svc{APPLE_MUSIC_SERVICE_TYPE}-([^-<]+)-Token")

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


def item_uri(account: AppleMusicAccount, kind: Kind, item_id: str) -> str:
    """Return the URI Sonos plays an Apple Music song, album or playlist from."""
    return _ITEMS[kind][0].format(key=f"{kind}%3a{item_id}", serial=account.serial)


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
        item_id=f"{prefix}{item.kind}%3a{item.id}",
        title=html.escape(item.name),
        extra=extra,
        item_class=item_class,
        desc=account.desc,
    )


def _account(soco: Any) -> AppleMusicAccount:
    """Return the Apple Music account of the household of a Sonos speaker."""
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
    if (account := find_account(result["Result"])) is None:
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


async def async_play(
    hass: HomeAssistant,
    entity_ids: list[str],
    items: list[CatalogItem],
    enqueue: MediaPlayerEnqueue,
) -> None:
    """Play Apple Music songs, albums or playlists on Sonos speakers."""
    # Grouped speakers share the one queue of their coordinator.
    coordinators = {
        id(soco): soco for soco in (_coordinator(hass, e) for e in entity_ids)
    }
    await asyncio.gather(
        *(
            hass.async_add_executor_job(_call, _queue, soco, items, enqueue)
            for soco in coordinators.values()
        )
    )


async def async_song_uri(hass: HomeAssistant, entity_id: str, song_id: str) -> str:
    """Return the URI a Sonos speaker plays an Apple Music song from."""
    soco = _coordinator(hass, entity_id)
    account = await hass.async_add_executor_job(_call, _account, soco)
    return item_uri(account, Kind.SONG, song_id)
